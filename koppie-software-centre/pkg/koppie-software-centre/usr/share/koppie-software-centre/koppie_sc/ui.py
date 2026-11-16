"""Koppie Software Centre - window and widgets (PyQt6)."""
from __future__ import annotations

import html
import os
import shutil
import subprocess

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QButtonGroup, QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
    QScrollArea, QStackedWidget, QToolButton, QVBoxLayout, QWidget)

from . import backend
from .backend import AUR, FLATPAK, REPO, Package
from .catalog import APPS, CATEGORIES
from .workers import CommandWorker, FuncWorker, SearchWorker

# Official Repo = blue, AUR = amber, Flatpak = green
BADGES = {REPO: ("Official Repo", "#1d6fb8"), AUR: ("AUR", "#d97706"), FLATPAK: ("Flatpak", "#2a8a4a")}
TAB_STYLE = ("QToolButton{padding:7px 16px;border:none;border-radius:6px;font-weight:600;}"
             "QToolButton:checked{background:palette(highlight);color:palette(highlighted-text);}")
GEAR_STYLE = ("QToolButton{padding:6px 10px;border:none;border-radius:6px;font-size:16px;}"
              "QToolButton:hover{background:palette(midlight);}")
CHIP_STYLE = ("QPushButton{border:1px solid palette(mid);border-radius:13px;padding:4px 14px;}"
              "QPushButton:checked{background:palette(highlight);color:palette(highlighted-text);"
              "border-color:palette(highlight);}")
CARD_STYLE = ("#card{border:1px solid palette(mid);border-radius:8px;}"
              "#card:hover{border-color:palette(highlight);}")
HEADING = "font-size:18px;font-weight:600;"
MUTED = "color:palette(placeholder-text);"
# page numbers inside the stack
EXPLORE, RESULTS, INSTALLED, UPDATES, DETAIL = range(5)


def heading(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(HEADING)
    return label


def app_icon(pkg: Package, size: int) -> QPixmap:
    fallback = QIcon.fromTheme("package-x-generic")
    return QIcon.fromTheme(pkg.icon or pkg.pid, fallback).pixmap(size, size)


def icon_pixmap(kind: str, value, paths: dict, size: int) -> QPixmap:
    """Turn one AppStream icon option into a pixmap (null when it does not work)."""
    if kind == "theme":
        return QIcon.fromTheme(value).pixmap(size, size)
    if kind == "file":
        pm = QPixmap(value)
    elif kind == "url":
        pm = QPixmap(paths.get(value, "")) if value in paths else QPixmap()
    else:
        return QPixmap()
    if pm.isNull() or (pm.width() <= size and pm.height() <= size):
        return pm                      # never upscale a small picture
    return pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                     Qt.TransformationMode.SmoothTransformation)


def ask(parent, title, text, yes="Continue", no="Cancel", icon=QMessageBox.Icon.Question) -> bool:
    """Friendly two-button dialog. "No" is the default button (the safe one)."""
    box = QMessageBox(parent)
    box.setIcon(icon)
    box.setWindowTitle(title)
    box.setText(text)
    yes_btn = box.addButton(yes, QMessageBox.ButtonRole.AcceptRole)
    no_btn = box.addButton(no, QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(no_btn)
    box.exec()
    return box.clickedButton() is yes_btn


class Badge(QLabel):
    def __init__(self, source: str):
        text, color = BADGES[source]
        super().__init__(text)
        self.setStyleSheet(f"background:{color};color:white;border-radius:7px;"
                           "padding:1px 8px;font-size:10px;font-weight:600;")


class PackageRow(QFrame):
    clicked = pyqtSignal(object, str)     # package, "install" | "uninstall"
    opened = pyqtSignal(object)           # row clicked -> show details

    def __init__(self, pkg: Package, mode: str):
        super().__init__()
        self.pkg = pkg
        self.openable = mode != "updates"
        self.setObjectName("card")
        self.setStyleSheet(CARD_STYLE if self.openable else CARD_STYLE.replace("#card:hover{border-color:palette(highlight);}", ""))
        if self.openable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(12)

        icon = QLabel()
        pm = app_icon(pkg, 40)
        icon.setPixmap(pm)
        self.has_icon = not pm.isNull()
        icon.setFixedSize(40, 40)
        lay.addWidget(icon)
        self.icon_label = icon

        text = QVBoxLayout()
        text.setSpacing(2)
        top = QHBoxLayout()
        top.addWidget(QLabel(f"<b>{html.escape(pkg.name)}</b>"))
        top.addWidget(Badge(pkg.source))
        top.addStretch()
        text.addLayout(top)
        summary = pkg.summary or "No description available."
        summary = summary if len(summary) <= 110 else summary[:107] + "…"
        sub = QLabel(summary)
        sub.setStyleSheet(MUTED)
        text.addWidget(sub)
        lay.addLayout(text, 1)

        if mode == "updates":
            lay.addWidget(QLabel(pkg.version))
        else:
            if pkg.version:
                ver = QLabel(pkg.version[:18])
                ver.setStyleSheet(MUTED + "font-size:11px;")
                lay.addWidget(ver)
            action = "uninstall" if pkg.installed else "install"
            btn = QPushButton("Uninstall" if pkg.installed else "Install")
            btn.setMinimumWidth(100)
            btn.clicked.connect(lambda _=False: self.clicked.emit(pkg, action))
            lay.addWidget(btn)

    def set_icon(self, pm: QPixmap):
        if not pm.isNull():
            self.icon_label.setPixmap(pm)
            self.has_icon = True

    def mouseReleaseEvent(self, event):
        if (self.openable and event.button() == Qt.MouseButton.LeftButton
                and self.rect().contains(event.position().toPoint())):
            self.opened.emit(self.pkg)
        super().mouseReleaseEvent(event)


class PackageList(QScrollArea):
    action = pyqtSignal(object, str)
    opened = pyqtSignal(object)
    icons_needed = pyqtSignal(object)      # rows without an icon yet

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        holder = QWidget()
        self._lay = QVBoxLayout(holder)
        self._lay.setSpacing(8)
        self._lay.setContentsMargins(2, 2, 10, 2)
        self._lay.addStretch()
        self.setWidget(holder)

    def set_packages(self, pkgs, mode="list", empty="Nothing here yet."):
        while self._lay.count() > 1:
            item = self._lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not pkgs:
            label = QLabel(empty)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setWordWrap(True)
            label.setContentsMargins(0, 40, 0, 0)
            self._lay.insertWidget(0, label)
            return
        for i, pkg in enumerate(pkgs):
            row = PackageRow(pkg, mode)
            row.clicked.connect(self.action)
            row.opened.connect(self.opened)
            self._lay.insertWidget(i, row)
        self.icons_needed.emit(list(pkgs))

    def refresh_icons(self, cands: dict, paths: dict):
        """Put AppStream icons on the rows; returns icons still to download."""
        pending = []
        for i in range(self._lay.count()):
            row = self._lay.itemAt(i).widget()
            if not isinstance(row, PackageRow) or row.has_icon:
                continue
            for kind, value in cands.get(row.pkg.key(), ()):
                if kind == "url" and value not in paths:
                    pending.append(value)
                    continue
                pm = icon_pixmap(kind, value, paths, 40)
                if not pm.isNull():
                    row.set_icon(pm)
                    break
        return pending


class DetailPage(QScrollArea):
    """App overview: big icon, facts, description and (lazy) screenshots."""
    back = pyqtSignal()
    action = pyqtSignal(object, str)

    def __init__(self):
        super().__init__()
        self.pkg = None
        self.has_icon = False
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        self.setWidget(body)
        v = QVBoxLayout(body)
        v.setContentsMargins(16, 8, 16, 16)
        v.setSpacing(14)

        back = QPushButton("←  Back")
        back.setFlat(True)
        back.clicked.connect(lambda _=False: self.back.emit())
        v.addWidget(back, 0, Qt.AlignmentFlag.AlignLeft)

        head = QHBoxLayout()
        head.setSpacing(16)
        self.icon = QLabel()
        self.icon.setFixedSize(96, 96)
        head.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(4)
        self.name = QLabel()
        self.name.setStyleSheet("font-size:24px;font-weight:700;")
        col.addWidget(self.name)
        meta = QHBoxLayout()
        self.badge_slot = QHBoxLayout()
        meta.addLayout(self.badge_slot)
        self.version = QLabel()
        self.version.setStyleSheet(MUTED)
        meta.addWidget(self.version)
        meta.addStretch()
        col.addLayout(meta)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet(MUTED)
        col.addWidget(self.summary)
        col.addStretch()
        head.addLayout(col, 1)
        self.button = QPushButton()
        self.button.setMinimumSize(120, 36)
        self.button.clicked.connect(self._clicked)
        head.addWidget(self.button, 0, Qt.AlignmentFlag.AlignTop)
        v.addLayout(head)

        self.info = QLabel()
        self.info.setTextFormat(Qt.TextFormat.RichText)
        self.info.setOpenExternalLinks(True)
        self.info.setWordWrap(True)
        v.addWidget(self.info)

        v.addWidget(heading("About this app"))
        self.description = QLabel()
        self.description.setWordWrap(True)
        self.description.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.description.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        v.addWidget(self.description)

        self.shots_title = heading("Screenshots")
        v.addWidget(self.shots_title)
        self.shots_scroll = QScrollArea()
        self.shots_scroll.setWidgetResizable(True)
        self.shots_scroll.setFixedHeight(250)
        self.shots_scroll.setFrameShape(QFrame.Shape.NoFrame)
        shots_body = QWidget()
        self.shots_row = QHBoxLayout(shots_body)
        self.shots_row.setContentsMargins(0, 0, 0, 0)
        self.shots_row.setSpacing(10)
        self.shots_row.addStretch()
        self.shots_scroll.setWidget(shots_body)
        v.addWidget(self.shots_scroll)
        v.addStretch()
        self._set_shots_visible(False)

    def _clicked(self):
        if self.pkg:
            self.action.emit(self.pkg, "uninstall" if self.pkg.installed else "install")

    def _set_shots_visible(self, visible: bool):
        self.shots_title.setVisible(visible)
        self.shots_scroll.setVisible(visible)

    def update_button(self):
        if self.pkg:
            self.button.setText("Uninstall" if self.pkg.installed else "Install")

    def show_package(self, pkg: Package):
        self.pkg = pkg
        pm = app_icon(pkg, 96)
        self.icon.setPixmap(pm)
        self.has_icon = not pm.isNull()
        self.name.setText(pkg.name)
        self.version.setText(f"Version {pkg.version}" if pkg.version else "")
        self.summary.setText(pkg.summary)
        while self.badge_slot.count():
            item = self.badge_slot.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.badge_slot.addWidget(Badge(pkg.source))
        self.info.setText("")
        self.description.setText("Loading details…")
        self.clear_shots()
        self.update_button()

    def set_details(self, info: dict):
        if info.get("version"):
            self.version.setText(f"Version {info['version']}")
        if info.get("summary"):
            self.summary.setText(info["summary"])
        rows = []
        esc = html.escape
        if info.get("download"):
            rows.append(("Download size", esc(info["download"])))
        if info.get("installed_size"):
            rows.append(("Size on disk", esc(info["installed_size"])))
        if info.get("license"):
            rows.append(("License", esc(info["license"])))
        url = info.get("url", "")
        if url.startswith(("http://", "https://")):
            rows.append(("Website", f'<a href="{esc(url, quote=True)}">{esc(url)}</a>'))
        text = "<table cellspacing='4'>" + "".join(
            f"<tr><td style='padding-right:18px;color:gray'>{k}</td><td>{v}</td></tr>"
            for k, v in rows) + "</table>"
        if info.get("note"):
            text += f"<p><i>{esc(info['note'])}</i></p>"
        self.info.setText(text if rows or info.get("note") else "")
        self.description.setText(info.get("description") or "No description available.")

    def add_screenshot(self, pixmap: QPixmap):
        label = QLabel()
        label.setPixmap(pixmap)
        self.shots_row.insertWidget(self.shots_row.count() - 1, label)
        self._set_shots_visible(True)

    def clear_shots(self):
        while self.shots_row.count() > 1:
            item = self.shots_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._set_shots_visible(False)

    def refresh_icons(self, cands: dict, paths: dict, pkg):
        """Bigger AppStream icon for this page; returns icons still to download."""
        if pkg is None or self.has_icon:
            return []
        pending = []
        for kind, value in cands.get(pkg.key(), ()):
            if kind == "url" and value not in paths:
                pending.append(value)
                continue
            pm = icon_pixmap(kind, value, paths, 96)
            if not pm.isNull():
                self.icon.setPixmap(pm)
                self.has_icon = True
                break
        return pending


class TaskPanel(QFrame):
    """Simple progress bar; the terminal log hides behind "Show Details"."""

    def __init__(self):
        super().__init__()
        self.ok = False
        self.setObjectName("panel")
        self.setStyleSheet("#panel{border-top:1px solid palette(mid);}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 8, 16, 10)
        top = QHBoxLayout()
        self.label = QLabel()
        top.addWidget(self.label, 1)
        self.toggle = QPushButton("Show Details")
        self.toggle.setFlat(True)
        self.toggle.clicked.connect(self._toggle)
        top.addWidget(self.toggle)
        lay.addLayout(top)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        lay.addWidget(self.bar)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(3000)
        self.log.setFixedHeight(170)
        self.log.hide()
        lay.addWidget(self.log)
        self.hide()

    def _toggle(self):
        show = not self.log.isVisible()
        self.log.setVisible(show)
        self.toggle.setText("Hide Details" if show else "Show Details")

    def start(self, title: str):
        self.ok = False
        self.log.clear()
        self.label.setText(title + "…")
        self.bar.setRange(0, 0)           # busy animation until we know more
        self.show()

    def set_progress(self, value: int):
        if self.bar.maximum() == 0:
            self.bar.setRange(0, 100)
        if value > self.bar.value():
            self.bar.setValue(value)

    def finish(self, ok: bool):
        self.ok = ok
        self.bar.setRange(0, 100)
        self.bar.setValue(100 if ok else 0)


class CareDialog(QDialog):
    """System Care: simple one-click maintenance for new users."""

    def __init__(self, parent, cache_bytes: int):
        super().__init__(parent)
        self.setWindowTitle("System Care")
        self.setMinimumWidth(500)
        self.choice = ""
        v = QVBoxLayout(self)
        v.setSpacing(12)
        v.addWidget(heading("System Care"))
        used = f" Right now it uses about {backend.human(cache_bytes)}." if cache_bytes else ""
        items = (
            ("cache", "Clean Package Cache",
             "Frees up storage by removing old downloaded files, old app build files "
             "and unused Flatpak components." + used, "Clean Up…"),
            ("keyring", "Refresh Arch Keyring",
             "Fixes errors like “invalid or corrupted package” or “signature is unknown trust” "
             "by refreshing the keys Arch uses to check that apps are genuine.", "Refresh…"),
        )
        for key, title, desc, button in items:
            card = QFrame()
            card.setObjectName("card")
            card.setStyleSheet("#card{border:1px solid palette(mid);border-radius:8px;}")
            row = QHBoxLayout(card)
            row.setContentsMargins(14, 12, 14, 12)
            col = QVBoxLayout()
            col.addWidget(QLabel(f"<b>{title}</b>"))
            text = QLabel(desc)
            text.setWordWrap(True)
            text.setStyleSheet(MUTED)
            col.addWidget(text)
            row.addLayout(col, 1)
            btn = QPushButton(button)
            btn.setMinimumWidth(110)
            btn.clicked.connect(lambda _=False, k=key: self._pick(k))
            row.addWidget(btn, 0, Qt.AlignmentFlag.AlignVCenter)
            v.addWidget(card)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        v.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)

    def _pick(self, key: str):
        self.choice = key
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Koppie Software Centre")
        bundled = os.path.join(os.path.dirname(__file__), "assets", "koppie-software-centre.png")
        self.setWindowIcon(QIcon.fromTheme("koppie-software-centre", QIcon(bundled)))
        self.resize(940, 680)
        self.setMinimumSize(780, 520)

        self.installed: list[Package] = []
        self.installed_keys: set = set()
        self.installed_loaded = False
        self.updates: list[Package] = []
        self.search_results: list[Package] = []
        self.search_id = 0
        self.detail_id = 0
        self.detail_pkg = None
        self.prev_page = EXPLORE
        self.current_tab = EXPLORE
        self.category = "All"
        self.worker = None
        self.ok_message = ""
        self._threads: set = set()
        self.catalog = [Package(name=n, pid=pid, source=src, summary=s, icon=ic,
                                remote="flathub" if src == FLATPAK else "")
                        for c, n, s, src, pid, ic in APPS]
        self.catalog_cats = [a[0] for a in APPS]

        self._build()
        self.render_explore()
        QTimer.singleShot(200, self.refresh_installed)
        QTimer.singleShot(1500, self.check_updates)

    # ------------------------------------------------------------ layout
    def _build(self):
        root = QWidget()
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        bar = QHBoxLayout()
        bar.setContentsMargins(16, 12, 16, 8)
        self.tab_group = QButtonGroup(self)
        self.tab_buttons = []
        for idx, name in ((EXPLORE, "Explore"), (INSTALLED, "Installed"), (UPDATES, "Updates")):
            b = QToolButton()
            b.setText(name)
            b.setCheckable(True)
            b.setChecked(idx == EXPLORE)
            b.setStyleSheet(TAB_STYLE)
            self.tab_group.addButton(b, idx)
            self.tab_buttons.append(b)
            bar.addWidget(b)
        self.tab_group.idClicked.connect(self.show_tab)
        bar.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search apps…  (press Enter)")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(320)
        self.search.returnPressed.connect(self.do_search)
        self.search.textChanged.connect(self.on_search_text)
        bar.addWidget(self.search)
        self.btn_care = QToolButton()
        gear = QIcon.fromTheme("configure")
        if gear.isNull():
            self.btn_care.setText("⚙")
        else:
            self.btn_care.setIcon(gear)
        self.btn_care.setToolTip("System Care")
        self.btn_care.setStyleSheet(GEAR_STYLE)
        self.btn_care.clicked.connect(self.open_care)
        bar.addWidget(self.btn_care)
        v.addLayout(bar)

        self.banner = QLabel()
        self.banner.setWordWrap(True)
        self.banner.hide()
        self.toast_timer = QTimer(self)
        self.toast_timer.setSingleShot(True)
        self.toast_timer.timeout.connect(self.banner.hide)
        v.addWidget(self.banner)

        self.stack = QStackedWidget()
        v.addWidget(self.stack, 1)
        self.panel = TaskPanel()
        v.addWidget(self.panel)

        # Explore
        page, lay = self._page()
        lay.addWidget(heading("Popular apps"))
        chips = QHBoxLayout()
        self.chip_group = QButtonGroup(self)
        for cat in CATEGORIES:
            b = QPushButton(cat)
            b.setCheckable(True)
            b.setChecked(cat == "All")
            b.setStyleSheet(CHIP_STYLE)
            b.clicked.connect(lambda _=False, c=cat: self.set_category(c))
            self.chip_group.addButton(b)
            chips.addWidget(b)
        chips.addStretch()
        lay.addLayout(chips)
        self.explore_list = self._list()
        lay.addWidget(self.explore_list)
        self.stack.addWidget(page)

        # Search results
        page, lay = self._page()
        self.results_title = heading("Results")
        lay.addWidget(self.results_title)
        self.results_list = self._list()
        lay.addWidget(self.results_list)
        self.stack.addWidget(page)

        # Installed
        page, lay = self._page()
        top = QHBoxLayout()
        top.addWidget(heading("Installed apps"))
        top.addStretch()
        self.show_system = QCheckBox("Show system packages")
        self.show_system.setToolTip("Also show background tools and libraries")
        self.show_system.toggled.connect(self.render_installed)
        top.addWidget(self.show_system)
        lay.addLayout(top)
        self.installed_list = self._list()
        lay.addWidget(self.installed_list)
        self.stack.addWidget(page)

        # Updates
        page, lay = self._page()
        top = QHBoxLayout()
        self.updates_title = heading("Updates")
        top.addWidget(self.updates_title)
        top.addStretch()
        self.btn_check = QPushButton("Check Again")
        self.btn_check.clicked.connect(self.check_updates)
        top.addWidget(self.btn_check)
        self.btn_update_all = QPushButton("Update All")
        self.btn_update_all.setEnabled(False)
        self.btn_update_all.clicked.connect(self.update_all)
        top.addWidget(self.btn_update_all)
        lay.addLayout(top)
        self.updates_list = self._list()
        lay.addWidget(self.updates_list)
        self.stack.addWidget(page)

        # App details
        self.detail = DetailPage()
        self.detail.back.connect(self.close_detail)
        self.detail.action.connect(self.on_action)
        self.stack.addWidget(self.detail)

    def _page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(16, 8, 8, 8)
        lay.setSpacing(10)
        return page, lay

    def _list(self):
        lst = PackageList()
        lst.action.connect(self.on_action)
        lst.opened.connect(self.open_detail)
        lst.icons_needed.connect(self.load_icons)
        return lst

    def _keep(self, thread):
        self._threads.add(thread)
        thread.finished.connect(lambda t=thread: self._threads.discard(t))

    def _spawn(self, fn, *args, then=None):
        w = FuncWorker(fn, *args)
        if then:
            w.done.connect(then)
        self._keep(w)
        w.start()

    # -------------------------------------------------------------- icons
    def load_icons(self, pkgs):
        """Rows whose icon the theme does not know get one from AppStream.

        The first call builds the icon index in the background (a few seconds,
        once per run and cached on disk afterwards); later calls are instant.
        """
        if not pkgs:
            return
        if backend.index_ready():
            self.apply_icons(backend.icon_candidates(pkgs))
        else:
            self._spawn(backend.icon_candidates, list(pkgs), then=self.apply_icons)

    def apply_icons(self, cands, paths=None, fetch=True):
        if not cands:
            return
        paths = paths or {}
        pending = set()
        for lst in (self.explore_list, self.results_list, self.installed_list):
            pending.update(lst.refresh_icons(cands, paths))
        if self.detail_pkg is not None:
            pending.update(self.detail.refresh_icons(cands, paths, self.detail_pkg))
        if pending and fetch:               # download once, then never again
            self._spawn(backend.fetch_icons, sorted(pending),
                        then=lambda got, c=cands, p=paths:
                            self.apply_icons(c, {**p, **(got or {})}, False))

    # -------------------------------------------------------------- misc
    def toast(self, msg: str, error: bool = False):
        color = "#b3261e" if error else "#2a8a4a"
        self.banner.setStyleSheet(f"padding:8px 16px;color:white;background:{color};")
        self.banner.setText(msg)
        self.banner.show()
        self.toast_timer.start(8000)

    def notify(self, msg: str):
        if not self.isActiveWindow() and shutil.which("notify-send"):
            subprocess.Popen(["notify-send", "-i", "koppie-software-centre",
                              "Koppie Software Centre", msg])

    def flag(self, pkgs):
        if self.installed_loaded:
            for p in pkgs:
                p.installed = p.key() in self.installed_keys
        return list(pkgs)

    # -------------------------------------------------------------- tabs
    def show_tab(self, idx: int):
        self.current_tab = idx
        self._leave_detail()
        if self.search.text():
            self.search.blockSignals(True)
            self.search.clear()
            self.search.blockSignals(False)
        self.stack.setCurrentIndex(idx)

    def on_search_text(self, text: str):
        if not text.strip():
            self.search_id += 1          # ignore results that are still coming
            self._leave_detail()
            self.stack.setCurrentIndex(self.current_tab)

    # ----------------------------------------------------------- explore
    def set_category(self, cat: str):
        self.category = cat
        self.render_explore()

    def render_explore(self):
        pkgs = [p for p, c in zip(self.catalog, self.catalog_cats)
                if self.category == "All" or c == self.category]
        self.explore_list.set_packages(self.flag(pkgs), "list")

    # ------------------------------------------------------------ search
    def do_search(self):
        q = self.search.text().strip()
        if not q:
            return
        self._leave_detail()
        self.search_id += 1
        sid = self.search_id
        self.search_results = []
        self.results_title.setText(f"Searching for “{q}”…")
        self.results_list.set_packages([], empty="Searching Official Repos, AUR and Flatpak…")
        self.stack.setCurrentIndex(RESULTS)
        w = SearchWorker(q)
        w.partial.connect(lambda pk, sid=sid, q=q: self.on_partial(sid, q, pk))
        w.finished.connect(lambda sid=sid, q=q: self.on_search_done(sid, q))
        self._keep(w)
        w.start()

    def on_partial(self, sid, q, pkgs):
        if sid != self.search_id:
            return
        self.search_results += pkgs
        self.render_results(q, searching=True)

    def on_search_done(self, sid, q):
        if sid == self.search_id:
            self.render_results(q, searching=False)

    def render_results(self, q: str, searching: bool):
        order = {REPO: 0, FLATPAK: 1, AUR: 2}
        pkgs = self.flag(self.search_results)
        # ready-made AUR packages (-bin) come before ones that must be compiled
        pkgs.sort(key=lambda p: (backend.rank(p, q), order[p.source],
                                 backend.build_pref(p), p.name.lower()))
        self.results_title.setText(f"Results for “{q}”" + ("  — still searching…" if searching else ""))
        empty = ("Searching Official Repos, AUR and Flatpak…" if searching else
                 f"No apps found for “{q}”. Try a different word.")
        self.results_list.set_packages(pkgs[:120], "list", empty=empty)

    # ----------------------------------------------------------- details
    def open_detail(self, pkg: Package):
        if self.stack.currentIndex() != DETAIL:
            self.prev_page = self.stack.currentIndex()
        self.detail_id += 1
        did = self.detail_id
        self.detail_pkg = pkg
        self.flag([pkg])
        self.detail.show_package(pkg)
        self.stack.setCurrentIndex(DETAIL)
        self.load_icons([pkg])
        self._spawn(backend.package_details, pkg,
                    then=lambda info, did=did: self.on_details(did, info))

    def on_details(self, did, info):
        if did != self.detail_id or self.stack.currentIndex() != DETAIL:
            return
        if not info:
            self.detail.description.setText("Sorry, we could not load more details for this app.")
            return
        self.detail.set_details(info)
        self.load_shots(did, list(info.get("screenshots", []))[:3])

    def load_shots(self, did, urls):
        """Screenshots are fetched one at a time, only while this page is open."""
        if not urls or did != self.detail_id:
            return
        url, rest = urls[0], urls[1:]
        self._spawn(backend.fetch_bytes, url,
                    then=lambda data, did=did, rest=rest: self.on_shot(did, rest, data))

    def on_shot(self, did, rest, data):
        if did != self.detail_id or self.stack.currentIndex() != DETAIL:
            return
        if data:
            pm = QPixmap()
            if pm.loadFromData(data):
                self.detail.add_screenshot(
                    pm.scaledToHeight(220, Qt.TransformationMode.SmoothTransformation))
        self.load_shots(did, rest)

    def _leave_detail(self):
        self.detail_id += 1              # drop late results
        self.detail_pkg = None
        self.detail.clear_shots()        # free the screenshot memory

    def close_detail(self):
        self._leave_detail()
        self.stack.setCurrentIndex(self.prev_page)

    # --------------------------------------------------------- installed
    def refresh_installed(self):
        self._spawn(backend.list_installed, then=self.on_installed)

    def on_installed(self, result):
        self.installed = result or []
        self.installed_keys = {p.key() for p in self.installed}
        self.installed_loaded = True
        self.render_installed()
        self.render_explore()
        if self.stack.currentIndex() == RESULTS and self.search.text().strip():
            self.render_results(self.search.text().strip(), searching=False)
        if self.detail_pkg is not None:
            self.flag([self.detail_pkg])
            self.detail.update_button()

    def render_installed(self):
        show_all = self.show_system.isChecked()
        pkgs = [p for p in self.installed if show_all or p.is_app or p.source == FLATPAK]
        pkgs.sort(key=lambda p: p.name.lower())
        self.installed_list.set_packages(pkgs, "list", empty="No apps installed yet.")

    # ----------------------------------------------------------- updates
    def check_updates(self):
        self.updates_title.setText("Checking for updates…")
        self.btn_check.setEnabled(False)
        self._spawn(backend.check_updates, then=self.on_updates)

    def on_updates(self, result):
        self.btn_check.setEnabled(True)
        if result is None:
            self.updates_title.setText("Could not check for updates")
            return
        self.updates = result
        n = len(result)
        self.updates_title.setText(f"{n} update{'s' if n != 1 else ''} available" if n
                                   else "Everything is up to date")
        self.tab_buttons[2].setText(f"Updates ({n})" if n else "Updates")
        self.btn_update_all.setEnabled(bool(n) and self.worker is None)
        self.updates_list.set_packages(result, "updates",
                                       empty="Your system is up to date. ✓")

    def update_all(self):
        self.run_task("Updating your system and apps", backend.cmd_update_all(),
                      "All updates are installed. ✓")

    # ------------------------------------------------------------ actions
    def on_action(self, pkg: Package, act: str):
        if self.worker is not None:
            self.toast("Please wait. Another task is still running.")
            return
        if act == "install":
            tool = backend.missing_tool(pkg)
            if tool:
                self.toast(f"“{tool}” is needed for this app, but it is not installed on your system.", True)
                return
            if pkg.source == AUR and not self.confirm_aur(pkg):
                return
            self.run_task(f"Installing {pkg.name}", backend.cmd_install(pkg),
                          f"{pkg.name} is installed. ✓")
        elif pkg.source == FLATPAK:
            self.confirm_remove(pkg, [])
        else:
            self.toast("Checking what will be removed…")
            self._spawn(backend.removal_preview, pkg.pid,
                        then=lambda res, pkg=pkg: self.after_preview(pkg, res))

    def confirm_aur(self, pkg: Package) -> bool:
        trust = ("AUR apps are made by the community and are not checked by the Arch team. "
                 "Only continue if you trust this one.")
        if backend.is_prebuilt(pkg.pid):
            return ask(self, "Install from the AUR?",
                       f"“{pkg.name}” comes from the AUR.\n\n{trust}", icon=QMessageBox.Icon.Warning)
        return ask(self, "This app has to be built first",
                   f"“{pkg.name}” has to be compiled (built from its source code) on your computer.\n\n"
                   "On older computers this can take a long time, sometimes 30 minutes or more, "
                   "and it can use a lot of processor power and memory. "
                   "Your computer may feel slow while it works.\n\n"
                   "Tip: if a version ending in “-bin” exists, it is usually much faster to install.\n\n"
                   + trust, icon=QMessageBox.Icon.Warning)

    def after_preview(self, pkg: Package, res):
        res = res or {"ok": True, "names": []}
        if not res.get("ok"):
            QMessageBox.information(
                self, "This app cannot be removed yet",
                f"“{pkg.name}” is needed by other apps on your computer, so it cannot be "
                "removed right now.\n\nDetails:\n" + res.get("error", ""))
            return
        self.confirm_remove(pkg, res.get("names", []))

    def confirm_remove(self, pkg: Package, names):
        text = (f"Remove “{pkg.name}” from your computer?\n"
                "Your personal files will not be deleted.")
        extra = [n for n in names if n != pkg.pid]
        if extra:
            shown = ", ".join(extra[:12]) + (f" and {len(extra) - 12} more" if len(extra) > 12 else "")
            text += ("\n\nThese items were only needed by this app, so they will be removed too "
                     f"to free up space:\n{shown}")
        if pkg.source == FLATPAK:
            text += "\n\nShared components that nothing else uses will be cleaned up too."
        if ask(self, "Uninstall app?", text, yes="Uninstall"):
            self.run_task(f"Removing {pkg.name}", backend.cmd_uninstall(pkg),
                          f"{pkg.name} was removed. ✓")

    # ------------------------------------------------------- system care
    def open_care(self):
        if self.worker is not None:
            self.toast("Please wait. Another task is still running.")
            return
        self._spawn(backend.cache_size, then=self.show_care)

    def show_care(self, size):
        dlg = CareDialog(self, size or 0)
        dlg.exec()
        if dlg.choice == "cache":
            if ask(self, "Clean up storage?",
                   "This removes old downloaded package files (the 2 newest versions of every app "
                   "are kept), old AUR build files and unused Flatpak components.\n\n"
                   "Your apps and personal files are not touched.", yes="Clean Up"):
                self.run_task("Cleaning up storage", backend.cmd_clean_cache(),
                              "Cleanup finished. ✓")
        elif dlg.choice == "keyring":
            if ask(self, "Refresh the Arch keyring?",
                   "This updates the keys that Arch uses to check that apps are genuine. "
                   "Use it if you see errors like “invalid or corrupted package” or "
                   "“signature is unknown trust”.\n\nAfterwards, open the Updates tab and "
                   "click Update All.", yes="Refresh"):
                self.run_task("Refreshing the Arch keyring", backend.cmd_refresh_keyring(),
                              "Keyring refreshed. Now open Updates and click Update All. ✓")

    # -------------------------------------------------------------- tasks
    def run_task(self, title, cmds, ok_message):
        if self.worker is not None:
            self.toast("Please wait. Another task is still running.")
            return
        if backend.touches_pacman(cmds) and backend.lock_exists():
            QMessageBox.information(
                self, "The package manager is busy",
                "Another program is using the package manager right now. "
                "For example, an update or an installation may already be running.\n\n"
                "Please wait a few minutes and try again.\n\n"
                "If this message does not go away, restart your computer and try again.")
            return
        self.ok_message = ok_message
        w = CommandWorker(cmds)
        self.worker = w
        w.line.connect(self.panel.log.appendPlainText)
        w.status.connect(lambda s, t=title: self.panel.label.setText(f"{t}  —  {s}"))
        w.progress.connect(self.panel.set_progress)
        w.done.connect(self.on_task_done)
        self.panel.start(title)
        self.btn_update_all.setEnabled(False)
        self._keep(w)
        w.start()

    def on_task_done(self, result: str):
        self.worker = None
        ok = result == "ok"
        self.panel.finish(ok)
        if ok:
            self.toast(self.ok_message)
            self.notify(self.ok_message)
            QTimer.singleShot(2500, self._hide_panel)
        elif result == "cancelled":
            self.panel.hide()
            self.toast("Cancelled. Nothing was changed.")
        else:
            self.toast("Something went wrong. Click “Show Details” to see what happened.", True)
            self.notify("Something went wrong.")
        self.refresh_installed()
        self.check_updates()

    def _hide_panel(self):
        if self.worker is None and self.panel.ok:
            self.panel.hide()

    # -------------------------------------------------------------- close
    def closeEvent(self, event):
        if self.worker is not None:
            self.toast("Please wait for the current task to finish before closing.", True)
            event.ignore()
            return
        for t in list(self._threads):
            t.wait(2000)
        event.accept()
