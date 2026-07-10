"""Background LaTeX compilation and PDF -> PNG preview rendering."""

import os
import shutil
import subprocess
import tempfile

from PyQt6.QtCore import QObject, QThread, pyqtSignal


class CompileWorker(QObject):
    finished = pyqtSignal(bool, str, str, list)  # ok, log, pdf_path, png_pages

    def __init__(self, tex_source: str, workdir: str, dpi: int = 140,
                 base_dir: str = ""):
        super().__init__()
        self.tex_source = tex_source
        self.workdir = workdir
        self.dpi = dpi
        self.base_dir = base_dir

    def run(self):
        os.makedirs(self.workdir, exist_ok=True)
        tex = os.path.join(self.workdir, "main.tex")
        with open(tex, "w", encoding="utf-8") as f:
            f.write(self.tex_source)

        if shutil.which("pdflatex") is None:
            self.finished.emit(False,
                               "pdflatex not found. Install TeX Live "
                               "(sudo apt install texlive-latex-extra "
                               "texlive-pictures).", "", [])
            return
        env = os.environ.copy()
        if self.base_dir:
            # let \includegraphics{relative/path} resolve against the
            # folder of the opened .tex file
            env["TEXINPUTS"] = f".:{self.base_dir}//:"
        try:
            proc = subprocess.run(
                ["pdflatex", "-interaction=nonstopmode",
                 "-halt-on-error", "main.tex"],
                cwd=self.workdir, capture_output=True, text=True,
                timeout=90, env=env)
            log = proc.stdout[-6000:]
        except subprocess.TimeoutExpired:
            self.finished.emit(False, "pdflatex timed out (90 s).", "", [])
            return

        pdf = os.path.join(self.workdir, "main.pdf")
        if proc.returncode != 0 or not os.path.exists(pdf):
            self.finished.emit(False, log, "", [])
            return

        pages = []
        if shutil.which("pdftoppm"):
            try:
                subprocess.run(["pdftoppm", "-png", "-r", str(self.dpi),
                                "main.pdf", "page"],
                               cwd=self.workdir, capture_output=True,
                               timeout=60)
                pages = sorted(os.path.join(self.workdir, f)
                               for f in os.listdir(self.workdir)
                               if f.startswith("page") and f.endswith(".png"))
            except subprocess.TimeoutExpired:
                pass
        self.finished.emit(True, log, pdf, pages)


class Compiler(QObject):
    """Owns the worker thread; only one compile at a time."""
    finished = pyqtSignal(bool, str, str, list)
    started = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._thread = None
        self.base_dir = ""
        self.workdir = tempfile.mkdtemp(prefix="tikzstudio_")

    @property
    def busy(self):
        return self._thread is not None and self._thread.isRunning()

    def compile(self, tex_source: str, dpi: int = 140):
        if self.busy:
            return False
        self.started.emit()
        self._worker = CompileWorker(tex_source, self.workdir, dpi,
                                     self.base_dir)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._done)
        self._thread.start()
        return True

    def _done(self, ok, log, pdf, pages):
        self._thread.quit()
        self._thread.wait()
        self._thread = None
        self.finished.emit(ok, log, pdf, pages)
