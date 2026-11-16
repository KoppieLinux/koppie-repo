"""Background threads, so the window never freezes."""
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

from PyQt6.QtCore import QThread, pyqtSignal

from . import backend


class FuncWorker(QThread):
    done = pyqtSignal(object)

    def __init__(self, fn, *args):
        super().__init__()
        self.fn, self.args = fn, args

    def run(self):
        try:
            result = self.fn(*self.args)
        except Exception:
            result = None
        self.done.emit(result)


class SearchWorker(QThread):
    """Searches all sources at the same time; emits each one as it finishes."""
    partial = pyqtSignal(list)

    def __init__(self, query):
        super().__init__()
        self.query = query

    def run(self):
        funcs = (backend.search_repo, backend.search_flatpak, backend.search_aur)
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(f, self.query) for f in funcs]
            for fut in as_completed(futures):
                try:
                    self.partial.emit(fut.result())
                except Exception:
                    self.partial.emit([])


class CommandWorker(QThread):
    line = pyqtSignal(str)
    status = pyqtSignal(str)
    progress = pyqtSignal(int)
    done = pyqtSignal(str)          # "ok", "cancelled" or "error"

    def __init__(self, cmds):
        super().__init__()
        self.cmds = cmds

    def run(self):
        total = len(self.cmds)
        for i, cmd in enumerate(self.cmds):
            self.line.emit("$ " + " ".join(cmd))
            is_flatpak = cmd[0] == "flatpak"
            try:
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL, text=True, bufsize=1, env=backend.ENV)
            except OSError as err:
                self.line.emit(f"Could not start: {err}")
                self.done.emit("error")
                return
            for raw in proc.stdout:
                text = raw.rstrip()
                if not text:
                    continue
                self.line.emit(text)
                st = backend.friendly_status(text)
                if st:
                    self.status.emit(st)
                pct = backend.parse_progress(text, is_flatpak)
                if pct is not None:
                    self.progress.emit((i * 100 + pct) // total)
            rc = proc.wait()
            if rc != 0:
                # pkexec: 126 / 127 = password dialog closed or wrong password
                self.done.emit("cancelled" if cmd[0] == "pkexec" and rc in (126, 127) else "error")
                return
        self.done.emit("ok")
