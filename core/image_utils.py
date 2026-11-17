from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image, ImageOps


def decode_image_bytes(data: bytes) -> np.ndarray | None:
    """Bytes -> BGR numpy image. Bozuk/HTML yanıtlarında None döner."""
    if not data or len(data) < 64:
        return None
    try:
        with Image.open(io.BytesIO(data)) as pil_image:
            pil_image = ImageOps.exif_transpose(pil_image)
            rgb = pil_image.convert("RGB")
            return cv2.cvtColor(np.asarray(rgb), cv2.COLOR_RGB2BGR)
    except Exception:
        return None


def bgr_to_rgb(image: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


def encode_jpeg_bytes(image: np.ndarray, quality: int = 92) -> bytes:
    """BGR numpy görselini JPEG baytlarına dönüştürür."""
    ok, buffer = cv2.imencode(
        ".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)]
    )
    if not ok:
        return b""
    return buffer.tobytes()


def resize_max_side(image: np.ndarray, max_side: int) -> tuple[np.ndarray, float]:
    h, w = image.shape[:2]
    longest = max(h, w)
    if longest <= max_side:
        return image, 1.0
    scale = max_side / float(longest)
    resized = cv2.resize(
        image,
        (max(1, int(round(w * scale))), max(1, int(round(h * scale)))),
        interpolation=cv2.INTER_AREA,
    )
    return resized, scale


def draw_label_box(
    image: np.ndarray,
    x: int,
    y: int,
    w: int,
    h: int,
    label: str,
    color: tuple[int, int, int] = (10, 10, 10),
    thickness: int | None = None,
    text_color: tuple[int, int, int] = (255, 255, 255),
) -> None:
    """Görselin üzerine kutu ve etiket çizer (in-place)."""
    ih, iw = image.shape[:2]
    x = max(0, min(x, iw - 1))
    y = max(0, min(y, ih - 1))
    w = max(1, min(w, iw - x))
    h = max(1, min(h, ih - y))
    line = thickness or max(2, int(round(max(iw, ih) / 420)))

    cv2.rectangle(image, (x, y), (x + w, y + h), color, line)

    font_scale = max(0.45, min(1.0, iw / 1400))
    text_thickness = max(1, line - 1)
    (tw, th), baseline = cv2.getTextSize(
        label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, text_thickness
    )
    top = max(0, y - th - baseline - 10)
    cv2.rectangle(image, (x, top), (x + tw + 12, top + th + baseline + 10), color, -1)
    cv2.putText(
        image,
        label,
        (x + 6, top + th + 5),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        text_color,
        text_thickness,
        cv2.LINE_AA,
    )


def crop_face(
    image: np.ndarray,
    bbox: tuple[float, float, float, float],
    margin: float = 0.30,
) -> np.ndarray | None:
    h, w = image.shape[:2]
    x, y, fw, fh = bbox
    mx = fw * margin
    my = fh * margin
    x0 = max(0, int(x - mx))
    y0 = max(0, int(y - my))
    x1 = min(w, int(x + fw + mx))
    y1 = min(h, int(y + fh + my))
    if x1 <= x0 or y1 <= y0:
        return None
    return image[y0:y1, x0:x1].copy()
