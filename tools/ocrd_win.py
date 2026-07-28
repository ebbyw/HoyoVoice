#!/usr/bin/env python3
"""HoyoVoice OCR daemon (Windows) — protocol-compatible with tools/ocrd.

Reads an image path per line on stdin, emits one single-line JSON array of
{text, confidence, x, y, w, h} per line on stdout. Coordinates are
normalized 0-1 with a BOTTOM-LEFT origin (Apple Vision convention) so
classify.py works unchanged.

Engines (HOYOVOICE_OCR_ENGINE = auto | rapid | windows, default auto):
  rapid    RapidOCR (ONNX). Line boxes + real confidence scores — the
           closest match to Vision output. ~15 MB of models, pure
           onnxruntime (already a project dependency).
  windows  Windows.Media.Ocr via the winsdk package. Built into Windows
           10/11, nothing to download, but exposes no confidence (reported
           as 1.0) and only word-level rects (unioned per line).
  auto     rapid if importable, else windows.

argv[1] (optional): custom-words file. Apple Vision uses it as a
recognition lexicon; neither Windows engine supports that, so here it is
accepted for protocol compatibility and ignored (live.py's fuzzy speaker
matching and text_fixes cover the same ground downstream).
"""
import json
import os
import sys


def out(blocks):
    print(json.dumps(blocks, sort_keys=True), flush=True)


class RapidEngine:
    def __init__(self):
        from rapidocr_onnxruntime import RapidOCR
        from PIL import Image
        self.Image = Image
        self.ocr = RapidOCR()

    def recognize(self, path):
        with self.Image.open(path) as img:
            W, H = img.size
        result, _ = self.ocr(path)
        blocks = []
        for box, text, score in result or []:
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            x0, x1 = min(xs), max(xs)
            y0, y1 = min(ys), max(ys)        # pixel coords, top-left origin
            blocks.append({
                "text": text,
                "confidence": float(score),
                "x": x0 / W, "w": (x1 - x0) / W,
                "y": 1.0 - y1 / H,           # → bottom-left origin
                "h": (y1 - y0) / H,
            })
        return blocks


class WindowsEngine:
    def __init__(self):
        import asyncio
        from winsdk.windows.globalization import Language
        from winsdk.windows.graphics import imaging
        from winsdk.windows.media.ocr import OcrEngine
        from winsdk.windows.storage import FileAccessMode, StorageFile
        self.asyncio = asyncio
        self.imaging = imaging
        self.StorageFile = StorageFile
        self.FileAccessMode = FileAccessMode
        self.engine = (OcrEngine.try_create_from_language(Language("en-US"))
                       or OcrEngine.try_create_from_user_profile_languages())
        if self.engine is None:
            raise RuntimeError("no OCR language pack available "
                               "(install English in Windows language settings)")
        try:
            self.max_dim = int(OcrEngine.max_image_dimension)
        except Exception:
            self.max_dim = 2600
        self.loop = asyncio.new_event_loop()

    async def _run(self, path):
        img = self.imaging
        f = await self.StorageFile.get_file_from_path_async(os.path.abspath(path))
        stream = await f.open_async(self.FileAccessMode.READ)
        decoder = await img.BitmapDecoder.create_async(stream)
        w0, h0 = decoder.pixel_width, decoder.pixel_height
        # upscale toward the engine's size limit: Windows OCR is markedly
        # more accurate on small game fonts when the text is larger
        scale = min(2.0, (self.max_dim - 4) / max(w0, h0, 1))
        if scale > 1.05:
            transform = img.BitmapTransform()
            transform.scaled_width = int(w0 * scale)
            transform.scaled_height = int(h0 * scale)
            transform.interpolation_mode = img.BitmapInterpolationMode.CUBIC
            bmp = await decoder.get_software_bitmap_async(
                img.BitmapPixelFormat.BGRA8,
                img.BitmapAlphaMode.PREMULTIPLIED,
                transform,
                img.ExifOrientationMode.IGNORE_EXIF_ORIENTATION,
                img.ColorManagementMode.DO_NOT_COLOR_MANAGE)
        else:
            bmp = await decoder.get_software_bitmap_async()
        W, H = bmp.pixel_width, bmp.pixel_height
        result = await self.engine.recognize_async(bmp)
        blocks = []
        for line in result.lines:
            rects = [w.bounding_rect for w in line.words]
            if not rects:
                continue
            x0 = min(r.x for r in rects)
            y0 = min(r.y for r in rects)
            x1 = max(r.x + r.width for r in rects)
            y1 = max(r.y + r.height for r in rects)
            blocks.append({
                "text": line.text,
                "confidence": 1.0,           # engine exposes none
                "x": x0 / W, "w": (x1 - x0) / W,
                "y": 1.0 - y1 / H,           # → bottom-left origin
                "h": (y1 - y0) / H,
            })
        return blocks

    def recognize(self, path):
        return self.loop.run_until_complete(self._run(path))


# auto mode: rapid must OCR a full frame this fast to keep up with the
# live loop (6 fps sampling, 2-read stabilization); otherwise use the
# native engine, which is far faster on weak CPUs
AUTO_MAX_MS = 1200


def _benchmark(engine):
    """Time one warmed-up recognize() on a synthetic 1080p frame."""
    import tempfile
    import time
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (1920, 1080), "black")
    d = ImageDraw.Draw(img)
    d.text((760, 240), "Rin Tohsaka", fill="white")
    d.text((650, 300), "The informant is right here in your agency?",
           fill="white")
    path = os.path.join(tempfile.gettempdir(), "hoyovoice_ocr_bench.png")
    img.save(path)
    engine.recognize(path)              # first call pays model warm-up
    t0 = time.time()
    engine.recognize(path)
    return int((time.time() - t0) * 1000)


def make_engine():
    want = os.environ.get("HOYOVOICE_OCR_ENGINE", "auto").lower()
    errors = []
    if want in ("auto", "rapid"):
        try:
            eng = RapidEngine()
            if want == "rapid":
                print("[ocrd_win] engine: rapid", file=sys.stderr, flush=True)
                return eng
            ms = _benchmark(eng)
            if ms <= AUTO_MAX_MS:
                print(f"[ocrd_win] engine: rapid ({ms}ms/frame)",
                      file=sys.stderr, flush=True)
                return eng
            print(f"[ocrd_win] rapid too slow here ({ms}ms/frame) — "
                  "falling back to the native Windows engine",
                  file=sys.stderr, flush=True)
            errors.append(f"rapid: {ms}ms/frame > {AUTO_MAX_MS}ms")
        except Exception as e:
            errors.append(f"rapid: {e}")
            if want == "rapid":
                raise
    try:
        eng = WindowsEngine()
        print("[ocrd_win] engine: windows", file=sys.stderr, flush=True)
        return eng
    except Exception as e:
        errors.append(f"windows: {e}")
        raise RuntimeError("no OCR engine available — " + "; ".join(errors))


def main():
    engine = make_engine()
    for line in sys.stdin:
        path = line.strip()
        if not path:
            out([])
            continue
        try:
            out(engine.recognize(path))
        except Exception as e:
            print(f"[ocrd_win] {e}", file=sys.stderr, flush=True)
            out([])


if __name__ == "__main__":
    main()
