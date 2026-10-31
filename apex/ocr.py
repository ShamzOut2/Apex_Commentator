"""Reading the text in an image (a league's calendar graphic), with positions.

On Windows 10 and 11 this uses Windows' own text recognition
(``Windows.Media.Ocr``), run through PowerShell, so nothing extra needs
installing. Elsewhere, or if that isn't available, Tesseract is used when it's
installed. ``read`` returns pieces of text with where they are
(``{"text", "x", "y", "w", "h"}``): a line, split where there's a wide gap so
columns of a table stay apart.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TIMEOUT_S = 90

# Windows PowerShell 5.1 can use Windows Runtime types directly.
WINDOWS_SCRIPT = r"""
param([string]$ImagePath, [string]$OutPath)
$ErrorActionPreference = 'Stop'
function Done($obj) {
  $json = ConvertTo-Json -InputObject $obj -Depth 6 -Compress
  [IO.File]::WriteAllText($OutPath, $json, (New-Object System.Text.UTF8Encoding $false))
}
try {
  Add-Type -AssemblyName System.Runtime.WindowsRuntime
  [void][Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
  [void][Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime]
  [void][Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
  [void][Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
  $asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
  function Await($op, [Type]$type) {
    $task = $asTask.MakeGenericMethod($type).Invoke($null, @($op))
    [void]$task.Wait(-1)
    $task.Result
  }
  $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
  if ($null -eq $engine) { Done @{ error = 'no-language' }; exit 0 }
  $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($ImagePath)) ([Windows.Storage.StorageFile])
  $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
  $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
  $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
  $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
  $lines = @()
  foreach ($line in $result.Lines) {
    $words = @()
    foreach ($w in $line.Words) {
      $r = $w.BoundingRect
      $words += @{ t = $w.Text; x = $r.X; y = $r.Y; w = $r.Width; h = $r.Height }
    }
    $lines += @{ words = $words }
  }
  Done @{ lines = $lines }
} catch {
  Done @{ error = $_.Exception.Message }
}
"""


class OcrError(Exception):
    pass


def _powershell():
    if sys.platform != "win32":
        return None
    path = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    return str(path) if path.exists() else shutil.which("powershell")


def available():
    """Which reader would be used: "windows", "tesseract" or None."""
    if _powershell():
        return "windows"
    if shutil.which("tesseract"):
        return "tesseract"
    return None


def read(image_bytes):
    """Pieces of text in a PNG/JPEG image, with positions. Raises OcrError."""
    engine = available()
    if engine is None:
        raise OcrError("Reading text from an image needs Windows 10 or later (or Tesseract installed). "
                       "Paste the calendar's text instead.")
    with tempfile.TemporaryDirectory(prefix="apex-ocr-") as tmp:
        image = Path(tmp) / "calendar.png"
        image.write_bytes(image_bytes)
        lines = _windows(image, Path(tmp)) if engine == "windows" else _tesseract(image)
    return pieces(lines)


def _run(args):
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        return subprocess.run(args, capture_output=True, timeout=TIMEOUT_S, creationflags=flags)
    except subprocess.TimeoutExpired as e:
        raise OcrError("Reading the image took too long.") from e
    except OSError as e:
        raise OcrError(f"Couldn't start the text reader: {e}") from e


def _windows(image, tmp):
    script, out = tmp / "ocr.ps1", tmp / "ocr.json"
    script.write_text(WINDOWS_SCRIPT, encoding="utf-8-sig")
    proc = _run([_powershell(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-File", str(script), str(image), str(out)])
    try:
        data = json.loads(out.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        detail = proc.stderr.decode("utf-8", "replace").strip()[:300]
        raise OcrError(f"Windows couldn't read the image. {detail}".strip()) from e
    if data.get("error") == "no-language":
        raise OcrError("Windows has no text recognition language installed. Add one in Settings > Time & language > "
                       "Language (e.g. English, with its optional features), or paste the calendar's text instead.")
    if data.get("error"):
        raise OcrError(f"Windows couldn't read the image: {data['error']}")
    lines = data.get("lines") or []
    lines = [lines] if isinstance(lines, dict) else lines
    out_lines = []
    for line in lines:
        words = line.get("words") or [] if isinstance(line, dict) else []
        words = [words] if isinstance(words, dict) else words
        out_lines.append([{"text": str(w.get("t", "")), "x": float(w.get("x", 0)), "y": float(w.get("y", 0)),
                           "w": float(w.get("w", 0)), "h": float(w.get("h", 0))} for w in words if isinstance(w, dict)])
    return out_lines


def _tesseract(image):
    proc = _run(["tesseract", str(image), "stdout", "tsv"])
    if proc.returncode != 0:
        raise OcrError("Tesseract couldn't read the image: " + proc.stderr.decode("utf-8", "replace").strip()[:300])
    lines = {}
    for row in proc.stdout.decode("utf-8", "replace").splitlines()[1:]:
        cols = row.split("\t")
        if len(cols) < 12 or cols[0] != "5" or not cols[11].strip():
            continue
        key = (cols[1], cols[2], cols[3], cols[4])  # page, block, paragraph, line
        lines.setdefault(key, []).append({"text": cols[11].strip(), "x": float(cols[6]), "y": float(cols[7]),
                                          "w": float(cols[8]), "h": float(cols[9])})
    return list(lines.values())


def pieces(lines):
    """Lines of words -> pieces: each line split where words are far apart
    (more than about two letters' height), so table columns stay separate."""
    out = []
    for words in lines:
        words = sorted((w for w in words if w["text"].strip()), key=lambda w: w["x"])
        group = []
        for w in words:
            if group:
                last = group[-1]
                height = max(last["h"], w["h"], 1.0)
                if w["x"] - (last["x"] + last["w"]) > 1.8 * height:
                    out.append(_join(group))
                    group = []
            group.append(w)
        if group:
            out.append(_join(group))
    return out


def _join(words):
    x0 = min(w["x"] for w in words)
    y0 = min(w["y"] for w in words)
    x1 = max(w["x"] + w["w"] for w in words)
    y1 = max(w["y"] + w["h"] for w in words)
    return {"text": " ".join(w["text"] for w in words), "x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}
