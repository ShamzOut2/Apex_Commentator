"""Background removal for photo booth shots: cut the car out of the track.

Uses the IS-Net "general use" segmentation model (the same model and
preprocessing as rembg's ``isnet-general-use``) through onnxruntime. The
model (~176 MB) is downloaded on first use into the user data folder and
checked against its published MD5.

After segmentation, only the object nearest the middle of the shot is kept
(grid shots often catch a neighbouring car), the edges are tidied, and the
result is cropped to the car with a small margin.
"""

import hashlib
import io
import threading
import urllib.request
from pathlib import Path

MODEL_NAME = "isnet-general-use"
MODEL_URL = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/isnet-general-use.onnx"
MODEL_MD5 = "fc16ebd8b0c10d971d3513d564d01e29"
MODEL_INPUT = 1024
OUTPUT_MAX_WIDTH = 1400
ERODE_PX = 7  # on the 256px-wide working copy: separates cars that merely touch


class CutoutError(Exception):
    """A user-facing cut-out problem."""


def dependencies_available():
    try:
        import numpy  # noqa: F401
        import onnxruntime  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return False
    return True


class Cutout:
    def __init__(self, models_dir, opener=None):
        self.models_dir = Path(models_dir)
        self._open = opener or urllib.request.urlopen
        self._session = None
        self._lock = threading.Lock()
        self.download = {"state": "idle", "done": 0, "total": 0, "error": None}

    @property
    def model_path(self):
        return self.models_dir / f"{MODEL_NAME}.onnx"

    def model_ready(self):
        return self.model_path.is_file()

    def ensure_model(self):
        """Download and verify the model if it isn't there yet."""
        if self.model_ready():
            return self.model_path
        self.models_dir.mkdir(parents=True, exist_ok=True)
        part = self.model_path.with_suffix(".part")
        self.download.update(state="downloading", done=0, total=0, error=None)
        md5 = hashlib.md5()
        try:
            req = urllib.request.Request(MODEL_URL, headers={"User-Agent": "ApexCommentator"})
            with self._open(req, timeout=60) as resp, open(part, "wb") as out:
                self.download["total"] = int(resp.headers.get("Content-Length") or 0)
                while True:
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    out.write(chunk)
                    md5.update(chunk)
                    self.download["done"] += len(chunk)
        except OSError as e:
            part.unlink(missing_ok=True)
            self.download.update(state="error", error=f"Couldn't download the cut-out model: {e}")
            raise CutoutError(self.download["error"]) from e
        if md5.hexdigest() != MODEL_MD5:
            part.unlink(missing_ok=True)
            self.download.update(state="error", error="The cut-out model download was damaged; try again.")
            raise CutoutError(self.download["error"])
        part.replace(self.model_path)
        self.download["state"] = "done"
        return self.model_path

    def _get_session(self):
        with self._lock:
            if self._session is None:
                if not dependencies_available():
                    raise CutoutError("Background cut-out needs onnxruntime, numpy and Pillow installed.")
                import onnxruntime as ort
                self._session = ort.InferenceSession(str(self.ensure_model()), providers=["CPUExecutionProvider"])
            return self._session

    def mask(self, img):
        """Foreground probability (0-255, 'L' image) for a PIL image, IS-Net style."""
        import numpy as np
        from PIL import Image

        session = self._get_session()
        im = img.convert("RGB").resize((MODEL_INPUT, MODEL_INPUT), Image.Resampling.LANCZOS)
        ary = np.asarray(im, dtype=np.float64)
        ary = ary / max(float(ary.max()), 1e-6) - 0.5
        tensor = ary.transpose((2, 0, 1))[None].astype(np.float32)
        pred = session.run(None, {session.get_inputs()[0].name: tensor})[0][:, 0, :, :]
        lo, hi = float(pred.min()), float(pred.max())
        pred = (np.squeeze(pred) - lo) / max(hi - lo, 1e-6)
        out = Image.fromarray((pred * 255).astype("uint8"), mode="L")
        return out.resize(img.size, Image.Resampling.LANCZOS)

    def cut(self, image_bytes):
        """Screenshot bytes -> PNG bytes of the car alone on a transparent background."""
        from PIL import Image

        try:
            img = Image.open(io.BytesIO(image_bytes))
            img.load()
        except Exception as e:
            raise CutoutError("The screenshot couldn't be read as an image.") from e
        img = img.convert("RGB")
        alpha = keep_central_object(self.mask(img))
        box = alpha.point(lambda v: 255 if v > 24 else 0).getbbox()
        if box is None:
            raise CutoutError("No car was found in the shot.")
        rgba = img.convert("RGBA")
        rgba.putalpha(alpha)
        return encode_png(crop_with_margin(rgba, box))


def keep_central_object(mask):
    """Keep only the connected object nearest the image centre, with soft edges intact.

    Works on a downscaled copy for speed, then applies the selection to the
    full-resolution mask. The copy is eroded first, so a neighbouring car that
    only touches the camera car (a wheel against a bumper) separates from it;
    the chosen object is grown back afterwards.
    """
    import numpy as np
    from PIL import Image, ImageFilter

    small_w = 256
    scale = small_w / mask.width
    small = mask.resize((small_w, max(1, round(mask.height * scale))), Image.Resampling.BILINEAR)
    small = small.point(lambda v: 255 if v > 128 else 0).filter(ImageFilter.MinFilter(ERODE_PX))
    solid = np.asarray(small) > 128
    h, w = solid.shape
    labels = np.zeros((h, w), dtype=np.int32)
    best, best_score = 0, None
    cy, cx = h / 2, w / 2
    current = 0
    for y0, x0 in zip(*np.nonzero(solid)):
        if labels[y0, x0]:
            continue
        current += 1
        stack = [(y0, x0)]
        labels[y0, x0] = current
        count = 0
        sy = sx = 0
        while stack:
            y, x = stack.pop()
            count += 1
            sy += y
            sx += x
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < h and 0 <= nx < w and solid[ny, nx] and not labels[ny, nx]:
                    labels[ny, nx] = current
                    stack.append((ny, nx))
        if count < 0.002 * h * w:
            continue  # specks
        # Prefer big objects near the centre: the car the camera is on.
        dist = ((sy / count - cy) ** 2 + (sx / count - cx) ** 2) ** 0.5 / max(h, w)
        score = count * (1.0 - min(dist, 0.9))
        if best_score is None or score > best_score:
            best, best_score = current, score
    if not best:
        return mask
    keep = Image.fromarray(((labels == best) * 255).astype("uint8"), mode="L")
    # Undo the erosion, plus a touch, so soft edges at full size aren't clipped.
    keep = keep.filter(ImageFilter.MaxFilter(ERODE_PX + 4)).resize(mask.size, Image.Resampling.BILINEAR)
    full = np.asarray(mask).astype(np.float32) * (np.asarray(keep).astype(np.float32) / 255.0)
    # Firm up the interior; leave anti-aliased edges soft.
    full = np.clip((full - 20) * 255.0 / 215.0, 0, 255)
    return Image.fromarray(full.astype("uint8"), mode="L")


def crop_with_margin(img, box, margin=0.04):
    x0, y0, x1, y1 = box
    mx, my = int((x1 - x0) * margin), int((y1 - y0) * margin)
    img = img.crop((max(0, x0 - mx), max(0, y0 - my), min(img.width, x1 + mx), min(img.height, y1 + my)))
    if img.width > OUTPUT_MAX_WIDTH:
        from PIL import Image
        img = img.resize((OUTPUT_MAX_WIDTH, round(img.height * OUTPUT_MAX_WIDTH / img.width)), Image.Resampling.LANCZOS)
    return img


def encode_png(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def crop_only(image_bytes, max_width=OUTPUT_MAX_WIDTH):
    """Without cut-out: just shrink the screenshot to a sensible size."""
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    if img.width > max_width:
        img = img.resize((max_width, round(img.height * max_width / img.width)), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()
