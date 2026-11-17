from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
import requests

from .config import (
    MODEL_DIR,
    SFACE_FILE,
    SFACE_URLS,
    YUNET_FILE,
    YUNET_URLS,
)
from .image_utils import resize_max_side

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


class FaceEngineError(Exception):
    pass


def _download_file(
    urls: tuple[str, ...],
    destination: Path,
    min_size: int,
    progress_cb: Callable[[float], None] | None = None,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    last_error: Exception | None = None

    for url in urls:
        try:
            temporary.unlink(missing_ok=True)
            with requests.get(
                url,
                stream=True,
                timeout=(15, 120),
                headers={"User-Agent": _USER_AGENT},
            ) as response:
                response.raise_for_status()
                total = int(response.headers.get("Content-Length") or 0)
                written = 0
                with temporary.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=256 * 1024):
                        if not chunk:
                            continue
                        handle.write(chunk)
                        written += len(chunk)
                        if progress_cb and total > 0:
                            progress_cb(min(1.0, written / total))

            if not temporary.exists() or temporary.stat().st_size < min_size:
                raise FaceEngineError(
                    f"İndirilen model çok küçük: {destination.name}"
                )
            temporary.replace(destination)
            return
        except Exception as exc:
            last_error = exc
            temporary.unlink(missing_ok=True)

    raise FaceEngineError(
        f"Model indirilemedi: {destination.name}. Son hata: {last_error}"
    )


def ensure_models(
    progress_cb: Callable[[str, float], None] | None = None,
) -> tuple[Path, Path]:
    """YuNet + SFace ONNX modellerini /tmp altında hazırlar."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    yunet_path = MODEL_DIR / YUNET_FILE
    sface_path = MODEL_DIR / SFACE_FILE

    jobs = (
        ("YuNet yüz dedektörü", YUNET_URLS, yunet_path, 100_000),
        ("SFace tanıma modeli", SFACE_URLS, sface_path, 10_000_000),
    )

    for label, urls, path, min_size in jobs:
        if path.exists() and path.stat().st_size >= min_size:
            continue
        if progress_cb:
            progress_cb(f"{label} indiriliyor...", 0.0)
        _download_file(
            urls,
            path,
            min_size,
            progress_cb=(
                (lambda fraction, text=label: progress_cb(text, fraction))
                if progress_cb
                else None
            ),
        )
        if progress_cb:
            progress_cb(f"{label} hazır.", 1.0)

    return yunet_path, sface_path


class FaceEngine:
    """YuNet (tespit) + SFace (128 boyutlu embedding) tabanlı yerel yüz motoru."""

    def __init__(
        self,
        yunet_path: Path,
        sface_path: Path,
        det_score: float = 0.50,
        nms: float = 0.30,
        top_k: int = 5000,
        num_threads: int = 2,
    ) -> None:
        if not hasattr(cv2, "FaceDetectorYN") or not hasattr(cv2, "FaceRecognizerSF"):
            raise FaceEngineError(
                "OpenCV contrib yüz modülleri bulunamadı. "
                "opencv-contrib-python-headless paketini kurun."
            )

        try:
            cv2.setNumThreads(max(1, int(num_threads)))
        except Exception:
            pass

        self._lock = threading.RLock()
        try:
            self.detector = cv2.FaceDetectorYN.create(
                str(yunet_path),
                "",
                (320, 320),
                float(det_score),
                float(nms),
                int(top_k),
            )
            self.recognizer = cv2.FaceRecognizerSF.create(str(sface_path), "")
        except cv2.error as exc:
            raise FaceEngineError(f"Yüz modelleri yüklenemedi: {exc}") from exc

    def analyze(
        self,
        image_bgr: np.ndarray,
        *,
        det_threshold: float = 0.60,
        min_face: int = 40,
        max_faces: int = 8,
        input_max_side: int = 1024,
        with_embeddings: bool = True,
    ) -> tuple[list[dict], tuple[int, int]]:
        """
        Görseldeki yüzleri bulur.

        Dönen bbox koordinatları ORİJİNAL görsel koordinatlarıdır.
        """
        if image_bgr is None or image_bgr.size == 0:
            return [], (0, 0)

        original_h, original_w = image_bgr.shape[:2]
        working, scale = resize_max_side(image_bgr, int(input_max_side))
        if scale <= 0:
            scale = 1.0
        work_h, work_w = working.shape[:2]

        with self._lock:
            try:
                self.detector.setInputSize((int(work_w), int(work_h)))
                _, detected = self.detector.detect(working)
            except cv2.error:
                return [], (original_w, original_h)

        if detected is None or len(detected) == 0:
            return [], (original_w, original_h)

        faces: list[dict] = []

        for row in detected:
            score = float(row[-1])
            if score < float(det_threshold):
                continue

            x, y, box_w, box_h = (float(value) for value in row[:4])
            if min(box_w, box_h) < float(min_face):
                continue

            embedding: np.ndarray | None = None
            if with_embeddings:
                with self._lock:
                    try:
                        aligned = self.recognizer.alignCrop(working, row)
                        feature = self.recognizer.feature(aligned)
                    except cv2.error:
                        continue
                embedding = np.asarray(feature, dtype=np.float32).reshape(-1).copy()
                norm = float(np.linalg.norm(embedding))
                if norm <= 1e-8:
                    continue
                embedding /= norm

            # bbox'i orijinal görsel koordinatlarına geri ölçekle
            ox = x / scale
            oy = y / scale
            ow = box_w / scale
            oh = box_h / scale
            ox = max(0.0, min(ox, float(original_w - 1)))
            oy = max(0.0, min(oy, float(original_h - 1)))
            ow = max(1.0, min(ow, float(original_w) - ox))
            oh = max(1.0, min(oh, float(original_h) - oy))

            faces.append(
                {
                    "bbox": (ox, oy, ow, oh),
                    "det_score": score,
                    "embedding": embedding,
                }
            )

        faces.sort(
            key=lambda item: item["bbox"][2] * item["bbox"][3],
            reverse=True,
        )
        return faces[: max(1, int(max_faces))], (original_w, original_h)
