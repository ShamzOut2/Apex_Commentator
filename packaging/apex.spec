# PyInstaller recipe for the Apex Commentator app.
#   pip install -r requirements.txt -r requirements-desktop.txt pyinstaller
#   pyinstaller packaging/apex.spec --noconfirm
# produces dist/ApexCommentator/ApexCommentator(.exe), a windowed app with the
# web UI and built-in logos bundled next to it.
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH).parent
datas = [(str(root / "web"), "web")]
binaries = []
hiddenimports = ["irsdk", "yaml", "onnxruntime", "numpy", "PIL.Image"]

# The app window (pywebview) is optional: bundle it when it's installed.
try:
    import webview  # noqa: F401
    wd, wb, wh = collect_all("webview")
    datas += wd
    binaries += wb
    hiddenimports += wh
except ImportError:
    print("pywebview not installed: the app will open in the browser instead")

a = Analysis(
    [str(root / "packaging" / "launcher.py")],
    pathex=[str(root)],
    datas=datas,
    binaries=binaries,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "unittest", "pydoc_data"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ApexCommentator",
    console=False,
    icon=str(root / "assets" / "icon.ico") if sys.platform == "win32" else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="ApexCommentator")
