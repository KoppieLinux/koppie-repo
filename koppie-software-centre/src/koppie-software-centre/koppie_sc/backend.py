"""Koppie Software Centre - backend.

Talks to pacman, yay and flatpak. No Qt code here, so it is easy to test.
"""
from __future__ import annotations

import glob
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import urlparse
from xml.parsers import expat

REPO, AUR, FLATPAK = "repo", "aur", "flatpak"
FLATHUB_URL = "https://dl.flathub.org/repo/flathub.flatpakrepo"
ENV = dict(os.environ, LC_ALL="C", LANG="C")


@dataclass
class Package:
    name: str                 # name shown to the user
    pid: str                  # pacman package name, or Flatpak app id
    source: str               # REPO, AUR or FLATPAK
    summary: str = ""
    version: str = ""
    installed: bool = False
    remote: str = ""          # Flatpak remote (e.g. flathub)
    icon: str = ""
    is_app: bool = True       # has a launcher (.desktop file)

    def key(self):
        return (self.source, self.pid)


# ---------------------------------------------------------------- helpers
def have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def run(cmd, timeout=120) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, env=ENV, stdin=subprocess.DEVNULL)
        return r.stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def terms(query: str):
    """Safe search words (no regex tricks, no leading dashes)."""
    words = re.findall(r"[A-Za-z0-9._+-]+", query)
    return [w.lstrip("-") for w in words if w.lstrip("-")][:5]


# AUR packages that ship ready-made binaries even without a "-bin" suffix
PREBUILT_NAMES = {"google-chrome", "spotify", "zoom", "slack-desktop", "dropbox"}


def is_prebuilt(name: str) -> bool:
    return name.endswith("-bin") or name in PREBUILT_NAMES


def build_pref(p: Package) -> int:
    """0 = quick to install, 1 = must be compiled on this computer (AUR only)."""
    return 1 if p.source == AUR and not is_prebuilt(p.pid) else 0


def rank(p: Package, query: str) -> int:
    q, n = query.lower().strip(), p.name.lower()
    if p.source == AUR and n.endswith("-bin"):
        n = n[:-4]
    if n == q:
        return 0
    if n.startswith(q):
        return 1
    if q in n:
        return 2
    return 3


# ---------------------------------------------------------------- search
_HEAD = re.compile(r"^(?P<repo>[^/\s]+)/(?P<name>\S+)\s+(?P<ver>\S+)(?P<rest>.*)$")


def parse_search(text: str):
    """Parse `pacman -Ss` / `yay -Ssa` output."""
    pkgs, cur = [], None
    for line in text.splitlines():
        if line.startswith((" ", "\t")):
            if cur is not None and not cur.summary:
                cur.summary = line.strip()
            continue
        m = _HEAD.match(line)
        if m:
            cur = Package(
                name=m["name"], pid=m["name"],
                source=AUR if m["repo"] == "aur" else REPO,
                version=m["ver"],
                installed="[installed" in m["rest"].lower())
            pkgs.append(cur)
        else:
            cur = None
    return pkgs


def search_repo(query: str):
    t = terms(query)
    if not t:
        return []
    return parse_search(run(["pacman", "-Ss", *t], 60))[:80]


def search_aur(query: str):
    t = terms(query)
    if not t or not have("yay"):
        return []
    pkgs = parse_search(run(["yay", "-Ssa", *t], 60))
    for p in pkgs:
        p.source = AUR
    return pkgs[:60]


def installed_flatpak_ids():
    if not have("flatpak"):
        return set()
    return set(run(["flatpak", "list", "--app", "--columns=application"]).split())


def search_flatpak(query: str):
    if not have("flatpak") or not terms(query):
        return []
    out = run(["flatpak", "search",
               "--columns=application,name,description,version,remotes",
               " ".join(terms(query))], 60)
    have_ids = installed_flatpak_ids()
    pkgs = []
    for line in out.splitlines():
        parts = line.split("\t") + [""] * 5
        app, name, desc, ver, remotes = [x.strip() for x in parts[:5]]
        if "." not in app or " " in app:
            continue
        pkgs.append(Package(
            name=name or app, pid=app, source=FLATPAK, summary=desc, version=ver,
            installed=app in have_ids,
            remote=(remotes.split(",")[0] if remotes else "flathub"), icon=app))
    return pkgs[:60]


# ------------------------------------------------------------- installed
def gui_packages():
    """Names of packages that own a launcher (.desktop file)."""
    files = glob.glob("/usr/share/applications/*.desktop")
    names = set()
    for i in range(0, len(files), 200):
        names.update(run(["pacman", "-Qoq", *files[i:i + 200]]).split())
    return names


def installed_native():
    foreign = set(run(["pacman", "-Qmq"]).split())
    gui = gui_packages()
    pkgs, cur = [], {}

    def flush():
        n = cur.get("Name")
        if n:
            pkgs.append(Package(
                name=n, pid=n, source=AUR if n in foreign else REPO,
                summary=cur.get("Description", ""), version=cur.get("Version", ""),
                installed=True, is_app=n in gui))

    for line in run(["pacman", "-Qei"]).splitlines() + [""]:
        if not line.strip():
            flush()
            cur = {}
        elif not line.startswith(" ") and ":" in line:
            k, v = line.split(":", 1)
            cur[k.strip()] = v.strip()
    return pkgs


def installed_flatpak():
    if not have("flatpak"):
        return []
    out = run(["flatpak", "list", "--app",
               "--columns=application,name,description,version"])
    pkgs = []
    for line in out.splitlines():
        parts = line.split("\t") + [""] * 4
        app, name, desc, ver = [x.strip() for x in parts[:4]]
        if "." in app:
            pkgs.append(Package(name=name or app, pid=app, source=FLATPAK,
                                summary=desc, version=ver, installed=True, icon=app))
    return pkgs


def list_installed():
    return installed_native() + installed_flatpak()


# --------------------------------------------------------------- updates
def parse_updates(text: str, source: str):
    pkgs = []
    for line in text.splitlines():
        p = line.split()
        if len(p) >= 4 and p[2] == "->":
            pkgs.append(Package(name=p[0], pid=p[0], source=source,
                                version=f"{p[1]} → {p[3]}",
                                summary="Update available", installed=True))
    return pkgs


def check_updates():
    ups = []
    cmd = ["checkupdates"] if have("checkupdates") else ["pacman", "-Qu"]
    ups += parse_updates(run(cmd, 180), REPO)
    if have("yay"):
        ups += parse_updates(run(["yay", "-Qua"], 180), AUR)
    if have("flatpak"):
        out = run(["flatpak", "remote-ls", "--updates",
                   "--columns=application,name,version"], 180)
        for line in out.splitlines():
            p = [x.strip() for x in line.split("\t")] + ["", ""]
            if "." in p[0] and " " not in p[0]:
                ups.append(Package(name=p[1] or p[0], pid=p[0], source=FLATPAK,
                                   version=p[2], summary="Update available",
                                   installed=True, icon=p[0]))
    return ups


# -------------------------------------------------------------- commands
def _yay(*args):
    # yay must not run as root, so it gets pkexec as its "sudo".
    return ["yay", "--sudo", "/usr/bin/pkexec", "--noconfirm", *args]


def missing_tool(p: Package) -> str:
    need = {REPO: ["pkexec"], AUR: ["yay", "pkexec"], FLATPAK: ["flatpak"]}[p.source]
    return next((t for t in need if not have(t)), "")


def cmd_install(p: Package):
    if p.source == REPO:   # always a full upgrade first: no partial upgrades
        return [["pkexec", "pacman", "-Syu", "--noconfirm", "--needed", p.pid]]
    if p.source == AUR:
        return [_yay("-Syu", "--needed", p.pid)]
    cmds = []
    if "flathub" not in run(["flatpak", "remotes", "--columns=name"]).split():
        cmds.append(["flatpak", "remote-add", "--if-not-exists", "--system",
                     "flathub", FLATHUB_URL])
    cmds.append(["flatpak", "install", "-y", "--noninteractive", "--system",
                 p.remote or "flathub", p.pid])
    return cmds


def cmd_uninstall(p: Package):
    if p.source == FLATPAK:
        return [["flatpak", "uninstall", "-y", "--noninteractive", p.pid],
                ["flatpak", "uninstall", "--unused", "-y", "--noninteractive"]]
    # -Rs also removes dependencies nobody else needs (clean uninstall)
    return [["pkexec", "pacman", "-Rs", "--noconfirm", p.pid]]


def cmd_update_all():
    cmds = [_yay("-Syu")] if have("yay") else [["pkexec", "pacman", "-Syu", "--noconfirm"]]
    if have("flatpak"):
        cmds.append(["flatpak", "update", "-y", "--noninteractive"])
    return cmds


# ------------------------------------------------------ output -> friendly
_STEP = re.compile(r"^\((\d+)/(\d+)\)\s+(installing|upgrading|reinstalling|downgrading|removing)")
_FP_STEP = re.compile(r"(\d+)/(\d+)")
_PCT = re.compile(r"(\d{1,3})%")


def parse_progress(line: str, is_flatpak: bool):
    """Return overall progress 0-99 for one output line, or None."""
    if not is_flatpak:
        m = _STEP.match(line.strip())
        return (int(m[1]) - 1) * 100 // int(m[2]) if m else None
    pct = _PCT.search(line)
    if not pct:
        return None
    p = min(int(pct[1]), 99)
    step = _FP_STEP.search(line)
    if step and int(step[2]) > 0:
        return min(((int(step[1]) - 1) * 100 + p) // int(step[2]), 99)
    return p


def friendly_status(line: str):
    l = line.lower()
    for key, text in (
        ("synchronizing", "Refreshing the app lists…"),
        ("resolving dependencies", "Checking what is needed…"),
        ("downloading", "Downloading…"),
        ("retrieving", "Downloading…"),
        ("==> making package", "Building the app (this can take a while)…"),
        ("building", "Building the app (this can take a while)…"),
        ("upgrading", "Updating…"),
        ("installing", "Installing…"),
        ("removing", "Removing…"),
    ):
        if key in l:
            return text
    return None


# ====================================================== v2: safety & care
LOCKFILE = "/var/lib/pacman/db.lck"


def lock_exists() -> bool:
    return os.path.exists(LOCKFILE)


def touches_pacman(cmds) -> bool:
    """True if any command uses the Arch package manager (needs the lock)."""
    for c in cmds:
        head = c[1] if c[0] == "pkexec" and len(c) > 1 else c[0]
        if head in ("pacman", "yay", "paccache", "pacman-key"):
            return True
        if head == "sh" and any("pacman" in x or "paccache" in x for x in c):
            return True
    return False


def removal_preview(pid: str):
    """What `pacman -Rs` would remove (dry run, no root needed)."""
    try:
        r = subprocess.run(["pacman", "-Rsp", "--print-format", "%n", pid],
                           capture_output=True, text=True, timeout=30,
                           env=ENV, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return {"ok": True, "names": [], "error": ""}
    if r.returncode != 0:
        err = (r.stderr or r.stdout).strip()
        # only block when other apps really need it; other errors: let pacman decide
        blocked = "breaks dependency" in err or "unable to satisfy" in err
        return {"ok": not blocked, "names": [], "error": err[:300]}
    return {"ok": True, "error": "",
            "names": [l.strip() for l in r.stdout.splitlines() if l.strip()]}


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def _dir_size(path: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
    return total


def cache_size() -> int:
    return (_dir_size("/var/cache/pacman/pkg")
            + _dir_size(os.path.expanduser("~/.cache/yay")))


def cmd_clean_cache():
    cmds = []
    if have("paccache"):   # keeps the 2 newest versions of every package
        cmds.append(["pkexec", "sh", "-c", "paccache -rk2; paccache -ruk0; true"])
    else:
        cmds.append(["pkexec", "pacman", "-Sc", "--noconfirm"])
    items = glob.glob(os.path.expanduser("~/.cache/yay/*"))
    if items:
        cmds.append(["rm", "-rf", *items])
    if have("flatpak"):
        cmds.append(["flatpak", "uninstall", "--unused", "-y", "--noninteractive"])
    return cmds


def cmd_refresh_keyring():
    return [["pkexec", "sh", "-c",
             "pacman -Sy --needed --noconfirm archlinux-keyring "
             "&& pacman-key --populate archlinux"]]


# ============================================ v2: app details (AppStream)
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
APPSTREAM_DIRS = ["/usr/share/swcatalog/xml", "/usr/share/app-info/xmls",
                  "/var/lib/swcatalog/xml", "/usr/share/app-info"]
_DETAILS_CACHE: dict = {}


def _open_xml(path):
    return gzip.open(path, "rb") if path.endswith(".gz") else open(path, "rb")


def _plain_description(el) -> str:
    """AppStream <description> (p / ul / ol) -> plain text."""
    blocks = []
    for child in el:
        if child.get(XML_LANG):
            continue
        if child.tag == "p":
            blocks.append(" ".join("".join(child.itertext()).split()))
        elif child.tag in ("ul", "ol"):
            items = ["• " + " ".join("".join(li.itertext()).split())
                     for li in child.findall("li") if not li.get(XML_LANG)]
            blocks.append("\n".join(items))
    return "\n\n".join(b for b in blocks if b)


def _screenshot_urls(comp):
    urls = []
    for shot in comp.iter("screenshot"):
        images = [i for i in shot.findall("image") if (i.text or "").strip()]
        thumbs = [i for i in images if i.get("type") == "thumbnail"]
        pick = None
        if thumbs:   # a medium-size thumbnail keeps downloads small
            pick = min(thumbs, key=lambda i: abs(int(i.get("width") or 0) - 624))
        else:
            pick = next((i for i in images if i.get("type", "source") == "source"), None)
        if pick is not None:
            urls.append(pick.text.strip())
    return urls


def _parse_component(comp):
    desc = comp.find("description")
    summary = next((e.text.strip() for e in comp.findall("summary")
                    if not e.get(XML_LANG) and e.text), "")
    return {"description": _plain_description(desc) if desc is not None else "",
            "summary": summary, "screenshots": _screenshot_urls(comp)}


def _scan_appstream(files, matcher):
    """Stream through AppStream files; stops at the first match (low RAM)."""
    for path in files:
        try:
            root = None
            for event, el in ET.iterparse(_open_xml(path), events=("start", "end")):
                if event == "start":
                    if root is None:
                        root = el
                    continue
                if el.tag == "component":
                    if matcher(el):
                        return _parse_component(el)
                    if root is not None:
                        root.clear()
        except (OSError, EOFError, ET.ParseError):
            continue
    return None


def _dedupe_xml(files):
    """Drop a *.xml.gz when the plain *.xml next to it exists (half the work)."""
    plain = {f[:-3] for f in files if f.endswith(".xml")}
    return [f for f in files if not (f.endswith(".xml.gz") and f[:-3] in plain)]


def _appstream_files():
    files = []
    for d in APPSTREAM_DIRS:
        files += sorted(glob.glob(os.path.join(d, "*.xml")))
        files += sorted(glob.glob(os.path.join(d, "*.xml.gz")))
    return _dedupe_xml(files)


def _flatpak_appstream_files(remote):
    files = []
    for base in ("/var/lib/flatpak", os.path.expanduser("~/.local/share/flatpak")):
        files += glob.glob(f"{base}/appstream/{remote}/*/active/appstream.xml*")
    return files


def _kv(text: str):
    out = {}
    for line in text.splitlines():
        m = re.match(r"^\s*([A-Za-z][A-Za-z ]*?)\s*:\s*(.*)$", line)
        if m and m[1] not in out:
            out[m[1]] = m[2].strip()
    return out


def package_details(p: Package):
    key = (p.source, p.pid)
    if key in _DETAILS_CACHE:
        return _DETAILS_CACHE[key]
    info = {"description": "", "summary": p.summary, "version": p.version,
            "download": "", "installed_size": "", "url": "", "license": "",
            "note": "", "screenshots": []}
    if p.source == FLATPAK:
        remote = p.remote or "flathub"
        f = _kv(run(["flatpak", "remote-info", remote, p.pid], 60))
        if not f:
            f = _kv(run(["flatpak", "info", p.pid], 30))
        info["version"] = f.get("Version") or p.version
        info["download"] = f.get("Download", "")
        info["installed_size"] = f.get("Installed", "")
        info["license"] = f.get("License", "")
        info["note"] = "Shared components (runtimes) may be downloaded too if you do not have them yet."
        wanted = {p.pid, p.pid + ".desktop"}
        meta = _scan_appstream(
            _flatpak_appstream_files(remote),
            lambda el: (el.findtext("id") or "").strip() in wanted)
    else:
        if p.source == REPO:
            f = _kv(run(["pacman", "-Si", p.pid]))
        else:
            f = _kv(run(["yay", "-Si", p.pid], 60)) if have("yay") else {}
        if not f and p.installed:
            f = _kv(run(["pacman", "-Qi", p.pid]))
        info["version"] = f.get("Version") or p.version
        info["url"] = f.get("URL", "")
        info["license"] = f.get("Licenses", "")
        info["installed_size"] = f.get("Installed Size", "")
        if p.source == REPO:
            info["download"] = f.get("Download Size", "")
        else:
            info["download"] = "Varies"
            info["note"] = ("Pre-built package: quick to install." if is_prebuilt(p.pid) else
                            "This app is compiled on your computer. It can take a long time on older hardware.")
        info["summary"] = f.get("Description") or p.summary
        meta = _scan_appstream(
            _appstream_files(),
            lambda el: p.pid in [(e.text or "").strip() for e in el.findall("pkgname")])
    if meta:
        info["description"] = meta["description"]
        info["summary"] = meta["summary"] or info["summary"]
        info["screenshots"] = meta["screenshots"]
    if not info["description"]:
        info["description"] = info["summary"] or "No description available."
    _DETAILS_CACHE[key] = info
    return info


def fetch_bytes(url: str, limit: int = 4_000_000):
    """Download one screenshot (small, with a size limit)."""
    if not url.startswith(("https://", "http://")):
        return None
    req = urllib.request.Request(url, headers={"User-Agent": "KoppieSoftwareCentre/0.2"})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = r.read(limit + 1)
    return data if len(data) <= limit else None


# ============================================ v3: app icons from AppStream
# Icons come from the local AppStream data first (no network, no RAM cost at
# idle): the system icon theme, then the icon files shipped with the catalogue,
# and only as a last resort a small download kept in the user's cache.
ICON_CACHE_DIR = os.path.join(os.path.expanduser("~/.cache"),
                              "koppie-software-centre", "icons")
_INDEX_FILE = os.path.join(os.path.expanduser("~/.cache"),
                           "koppie-software-centre", "icon-index.json")
_icon_index: dict | None = None
_INDEX_LOCK = threading.Lock()


def icon_source_files():
    """Local system AppStream catalogues (descriptions, stock icons, screenshots)."""
    files = []
    for d in APPSTREAM_DIRS:
        files += sorted(glob.glob(os.path.join(d, "*.xml")))
        files += sorted(glob.glob(os.path.join(d, "*.xml.gz")))
    return _dedupe_xml(files)


def _flatpak_active_dirs():
    """Where each Flatpak remote keeps its current appstream data."""
    out = []
    for base in ("/var/lib/flatpak", os.path.expanduser("~/.local/share/flatpak")):
        out += sorted(glob.glob(f"{base}/appstream/*/*/active"))
    return out


def _flatpak_icon_files(index):
    """Flatpak ships its icons as plain files named after the app id.

    Reading them straight from disk is ~200x faster than parsing the huge
    Flatpak appstream.xml (50+ MB), and the picture is the same one.
    """
    for active in _flatpak_active_dirs():
        for path in glob.glob(os.path.join(active, "icons", "**", "*"), recursive=True):
            if not os.path.isfile(path):
                continue
            stem, ext = os.path.splitext(os.path.basename(path))
            if ext.lower() not in (".png", ".svg", ".svgz", ".jpg", ".jpeg", ".webp"):
                continue
            width = _num(os.path.basename(os.path.dirname(path)).split("x")[0])
            keys = [stem]
            if stem.endswith(".desktop"):
                keys.append(stem[:-len(".desktop")])
            for key in keys:
                if not key:
                    continue
                cur = index.get(key)
                if not cur:
                    index[key] = [["file", path, width]]
                elif len(cur) == 1 and cur[0][0] == "file" and width > cur[0][2]:
                    cur[0] = ["file", path, width]      # keep the biggest size


def _num(text) -> int:
    try:
        return int(text or 0)
    except (TypeError, ValueError):
        return 0


class _IconScanner:
    """Streams one AppStream file and records id/pkgname -> icon info.

    Uses expat directly and only reacts to the few tags we need, so a big
    catalogue (tens of MB) is read in seconds and with almost no RAM.
    """

    def __init__(self, path: str, index: dict):
        self.index = index
        self.base = os.path.dirname(path)
        self.origin = ""
        self.cur = None            # {"keys": set, "icons": list} or None
        self.stack = []            # open tags, to know a tag's parent
        self.tag = ""              # tag whose text we are collecting
        self.buf = []
        self.pend_type, self.pend_w, self.pend_h = "stock", 0, 0
        parser = expat.ParserCreate()
        parser.StartElementHandler = self._start
        parser.CharacterDataHandler = self._chars
        parser.EndElementHandler = self._end
        self.parser = parser

    # -- expat callbacks ------------------------------------------------
    def _start(self, name, attrs):
        parent = self.stack[-1] if self.stack else ""
        self.stack.append(name)
        if name == "components":
            self.origin = attrs.get("origin", "")
        elif name == "component":
            self.cur = {"keys": set(), "icons": []}
        elif self.cur is None:
            return
        elif name in ("id", "pkgname") and parent == "component":
            self.tag, self.buf = name, []
        elif name == "icon" and parent == "component":
            self.tag, self.buf = name, []
            self.pend_type = attrs.get("type", "stock")
            self.pend_w = _num(attrs.get("width"))
            self.pend_h = _num(attrs.get("height"))

    def _chars(self, data):
        if self.tag:
            self.buf.append(data)

    def _end(self, name):
        if self.stack and self.stack[-1] == name:
            self.stack.pop()
        if self.cur is None:
            return
        if name == self.tag:
            text = "".join(self.buf).strip()
            self.tag, self.buf = "", []
            if name == "icon":
                icon = self._icon(text)
                if icon:
                    self.cur["icons"].append(icon)
            elif text:
                if name == "id" and text.endswith(".desktop"):
                    text = text[:-len(".desktop")]
                if text:
                    self.cur["keys"].add(text)
        elif name == "component":
            for key in self.cur["keys"]:
                # first component wins, unless it had nothing to offer
                if key not in self.index or not self.index[key]:
                    self.index[key] = self.cur["icons"]
            self.cur = None

    # -- icon entries ---------------------------------------------------
    def _icon(self, text: str):
        if not text:
            return None
        if self.pend_type == "stock":        # a name in the system icon theme
            return ["stock", text, 0]
        if self.pend_type == "remote":       # a URL (rare, downloaded on demand)
            return ["remote", text, 0] if text.startswith(("http://", "https://")) else None
        # a file shipped with the catalogue; keep it only if we can find it
        w, h = self.pend_w, self.pend_h
        guesses = [os.path.join(self.base, "icons", f"{w}x{h}", text),
                   os.path.join(self.base, f"{w}x{h}", text),
                   os.path.join(self.base, text)]
        if self.origin:
            guesses.append(os.path.join(os.path.dirname(self.base), "icons",
                                        self.origin, f"{w}x{h}", text))
        for path in guesses:
            if os.path.exists(path):
                return ["file", path, w]
        return None


def _sources_signature(files):
    sig = []
    for path in files:
        try:
            st = os.stat(path)
            sig.append([path, int(st.st_mtime), st.st_size])
        except OSError:
            sig.append([path, 0, 0])
    for active in _flatpak_active_dirs():      # a Flatpak refresh swaps this link
        try:
            sig.append([active, os.path.realpath(active)])
        except OSError:
            sig.append([active, ""])
    return sig


def index_ready() -> bool:
    """True when the icon index is already in memory (lookups are then free)."""
    return _icon_index is not None


def icon_index() -> dict:
    """id/pkgname -> icon info. Built once per run, cached on disk between runs."""
    global _icon_index
    if _icon_index is not None:
        return _icon_index
    with _INDEX_LOCK:                       # only one thread ever builds it
        if _icon_index is not None:
            return _icon_index
        files = icon_source_files()
        signature = _sources_signature(files)
        try:
            with open(_INDEX_FILE, encoding="utf-8") as fh:
                saved = json.load(fh)
            if saved.get("sources") == signature:
                _icon_index = saved.get("icons") or {}
                return _icon_index
        except (OSError, ValueError):
            pass
        index: dict = {}
        for path in files:
            try:
                scanner = _IconScanner(path, index)
                with _open_xml(path) as fh:
                    scanner.parser.ParseFile(fh)
            except (OSError, EOFError, ValueError, expat.ExpatError):
                continue
        _flatpak_icon_files(index)
        try:
            os.makedirs(os.path.dirname(_INDEX_FILE), exist_ok=True)
            with open(_INDEX_FILE, "w", encoding="utf-8") as fh:
                json.dump({"sources": signature, "icons": index}, fh)
        except OSError:
            pass                              # a read-only home is no problem
        _icon_index = index
        return index


def _order_icons(hits):
    """Theme name first (matches the KDE theme), then local files, then downloads."""
    stock, files, urls, seen = [], [], [], set()
    for hit in hits or []:
        if not isinstance(hit, (list, tuple)) or len(hit) < 2:
            continue
        kind, value = hit[0], hit[1]
        if not value or (kind, value) in seen:
            continue
        seen.add((kind, value))
        if kind == "stock":
            stock.append(("theme", value))
        elif kind == "file" and os.path.exists(value):
            files.append((_num(hit[2]) if len(hit) > 2 else 0, value))
        elif kind == "remote":
            urls.append(value)
    files.sort(reverse=True)                 # biggest picture first
    return (stock + [("file", p) for _w, p in files[:2]]
            + [("url", u) for u in urls[:2]])


def icon_candidates(pkgs):
    """{package key: [(kind, value), ...]} - ordered icon options per package."""
    index = icon_index()
    out = {}
    for p in pkgs:
        hits = index.get(p.pid) or index.get(p.name)
        if hits:
            ordered = _order_icons(hits)
            if ordered:
                out[p.key()] = ordered
    return out


def fetch_icons(urls):
    """Download the few remote icons into the user's cache (small, one by one)."""
    out = {}
    if not urls:
        return out
    try:
        os.makedirs(ICON_CACHE_DIR, exist_ok=True)
    except OSError:
        return out
    for url in dict.fromkeys(urls):          # unique, original order
        if not url.startswith(("http://", "https://")):
            continue
        ext = os.path.splitext(urlparse(url).path)[1].lower()
        if len(ext) > 5 or not ext.isalpha():
            ext = ".png"
        path = os.path.join(ICON_CACHE_DIR,
                            hashlib.sha1(url.encode()).hexdigest() + ext)
        if os.path.exists(path):
            out[url] = path
            continue
        try:
            data = fetch_bytes(url, 1_000_000)   # icons are tiny
        except Exception:
            data = None
        if data:
            try:
                with open(path, "wb") as fh:
                    fh.write(data)
                out[url] = path
            except OSError:
                pass
    return out
