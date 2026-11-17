from __future__ import annotations

import base64
import gc
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

import numpy as np

from .config import EMBEDDING_SIZE
from .drive import DriveClient, DriveItem
from .face_engine import FaceEngine
from .pg_index_store import PgIndexStore


@dataclass(slots=True)
class IndexOptions:
    include_subfolders: bool = True
    thumb_size: int = 768
    det_threshold: float = 0.60
    min_face: int = 40
    max_faces: int = 8
    max_images: int = 0
    force: bool = False
    workers: int = 4
    sync_batch: int = 100


def encode_row(
    file_id: str,
    name: str,
    path: str,
    width: int,
    height: int,
    status: str,
    error: str | None,
    faces: list[dict],
) -> dict:
    payload: list[dict] = []
    for face in faces or []:
        embedding = face.get("embedding")
        if embedding is None:
            continue
        array = np.asarray(embedding, dtype=np.float32).reshape(-1)
        if array.size != EMBEDDING_SIZE:
            continue
        bbox = face.get("bbox") or (0, 0, 0, 0)
        payload.append(
            {
                "x": float(bbox[0]),
                "y": float(bbox[1]),
                "w": float(bbox[2]),
                "h": float(bbox[3]),
                "score": float(face.get("det_score") or 0.0),
                "emb": base64.b64encode(
                    array.astype(np.float32).tobytes()
                ).decode("ascii"),
            }
        )

    return {
        "file_id": file_id,
        "name": name,
        "path": path,
        "width": int(width),
        "height": int(height),
        "status": status,
        "error": error,
        "faces": payload,
    }


def build_index(
    client: DriveClient,
    engine: FaceEngine,
    store: PgIndexStore,
    folder_id: str,
    resource_key: str | None,
    options: IndexOptions,
    *,
    on_status: Callable[[str], None] | None = None,
    on_progress: Callable[[int, int, int, dict], None] | None = None,
    on_batch: Callable[[list[dict]], None] | None = None,
    load_cached: Callable[[list[str]], list[dict]] | None = None,
    on_folder: Callable[[str], None] | None = None,
) -> dict:
    if on_status:
        on_status("Klasör okunuyor...")

    items: list[DriveItem] = []
    seen: set[str] = set()
    for item in client.walk_images(
        folder_id,
        include_subfolders=options.include_subfolders,
        resource_key=resource_key,
        on_folder=on_folder,
    ):
        if item.id in seen:
            continue
        seen.add(item.id)
        items.append(item)
        if options.max_images and len(items) >= int(options.max_images):
            break

    total_found = len(items)
    if on_status:
        on_status(f"{total_found} fotoğraf bulundu.")

    done_ids = set() if options.force else store.done_ids()
    todo = [item for item in items if item.id not in done_ids]
    skipped = total_found - len(todo)

    if on_status:
        on_status(
            f"{len(todo)} fotoğraf işlenecek, {skipped} fotoğraf zaten kayıtlı."
        )

    counters = {"done": 0, "no_face": 0, "error": 0, "faces": 0}
    processed = 0
    realtime_skipped = 0
    cached_skipped = 0
    batch: list[dict] = []
    sync_errors: list[str] = []
    workers = 4
    chunk_size = 16
    executor = ThreadPoolExecutor(max_workers=workers)

    def flush_batch(force: bool = False) -> None:
        nonlocal batch
        if not batch:
            return
        if not force and len(batch) < max(1, int(options.sync_batch)):
            return
        if on_batch is not None:
            try:
                on_batch(batch)
            except Exception as exc:
                sync_errors.append(str(exc)[:300])
        batch = []

    try:
        for start in range(0, len(todo), chunk_size):
            chunk = todo[start : start + chunk_size]

            if load_cached is not None:
                try:
                    cached_rows = load_cached([item.id for item in chunk])
                except Exception:
                    load_cached = None
                    cached_rows = []
                if cached_rows:
                    try:
                        store.import_rows(cached_rows)
                        cached_ids = {
                            str(row.get("file_id"))
                            for row in cached_rows
                            if row.get("file_id")
                        }
                        chunk = [
                            item for item in chunk if item.id not in cached_ids
                        ]
                        cached_skipped += len(cached_ids)
                    except Exception:
                        pass

            try:
                claimed_ids = store.claim_images(
                    [item.id for item in chunk],
                    force=options.force,
                )
            except Exception:
                claimed_ids = {item.id for item in chunk}

            realtime_skipped += len(chunk) - len(claimed_ids)
            chunk = [item for item in chunk if item.id in claimed_ids]
            if not chunk:
                continue

            future_map = {
                executor.submit(
                    client.fetch_image,
                    item.id,
                    options.thumb_size,
                    resource_key,
                ): item
                for item in chunk
            }

            for future in as_completed(future_map):
                item = future_map.pop(future)
                image = None
                error_text: str | None = None

                try:
                    image = future.result()
                except Exception as exc:
                    error_text = str(exc)[:300]
                finally:
                    del future

                if image is None:
                    error_text = (
                        error_text or "Görsel indirilemedi veya çözülemedi."
                    )
                    try:
                        store.save_error(
                            item.id, item.name, item.path, error_text
                        )
                    except Exception as exc:
                        sync_errors.append(str(exc)[:300])
                    counters["error"] += 1
                    row = encode_row(
                        item.id,
                        item.name,
                        item.path,
                        0,
                        0,
                        "error",
                        error_text,
                        [],
                    )
                else:
                    height, width = image.shape[:2]
                    try:
                        faces, _ = engine.analyze(
                            image,
                            det_threshold=options.det_threshold,
                            min_face=options.min_face,
                            max_faces=options.max_faces,
                            input_max_side=options.thumb_size,
                        )
                    except Exception as exc:
                        error_text = f"Yüz analizi hatası: {exc}"[:300]
                        try:
                            store.save_error(
                                item.id, item.name, item.path, error_text
                            )
                        except Exception as db_exc:
                            sync_errors.append(str(db_exc)[:300])
                        counters["error"] += 1
                        row = encode_row(
                            item.id,
                            item.name,
                            item.path,
                            width,
                            height,
                            "error",
                            error_text,
                            [],
                        )
                    else:
                        status = "done" if faces else "no_face"
                        try:
                            store.save_result(
                                item.id,
                                item.name,
                                item.path,
                                width,
                                height,
                                faces,
                                status,
                            )
                        except Exception as db_exc:
                            sync_errors.append(str(db_exc)[:300])
                        if faces:
                            counters["done"] += 1
                            counters["faces"] += len(faces)
                        else:
                            counters["no_face"] += 1
                        row = encode_row(
                            item.id,
                            item.name,
                            item.path,
                            width,
                            height,
                            status,
                            None,
                            faces,
                        )
                    finally:
                        del image

                batch.append(row)
                processed += 1
                if on_progress is not None:
                    on_progress(
                        processed,
                        len(todo),
                        skipped + realtime_skipped,
                        counters,
                    )
                flush_batch()

            gc.collect()
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
        flush_batch(force=True)
        gc.collect()

    skipped += realtime_skipped + cached_skipped
    try:
        store.set_meta("folder_id", folder_id)
        store.set_meta(
            "last_indexed",
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
    except Exception as exc:
        sync_errors.append(str(exc)[:300])

    return {
        "total_found": total_found,
        "processed": processed,
        "skipped": skipped,
        "skipped_realtime": realtime_skipped,
        "skipped_cached": cached_skipped,
        "counters": counters,
        "sync_errors": sync_errors,
        "warnings": list(client.warnings),
    }


def search_embeddings(
    matrix: np.ndarray,
    metas: list[dict],
    probes: list[np.ndarray],
    threshold: float = 0.50,
    max_results: int | None = None,
) -> list[dict]:
    if matrix is None or matrix.size == 0 or not probes or not metas:
        return []

    if matrix.ndim != 2 or matrix.shape[0] != len(metas):
        return []

    valid_probes = []
    for probe in probes:
        if probe is None:
            continue
        arr = np.asarray(probe, dtype=np.float32).reshape(-1)
        if arr.size == matrix.shape[1]:
            valid_probes.append(arr)

    if not valid_probes:
        return []

    probe_matrix = np.stack(valid_probes)
    norms = np.linalg.norm(probe_matrix, axis=1, keepdims=True)
    np.divide(probe_matrix, norms, out=probe_matrix, where=norms > 1e-8)

    similarities = matrix @ probe_matrix.T
    best_scores = similarities.max(axis=1)
    best_probes = similarities.argmax(axis=1)

    candidate_indices = np.where(best_scores >= float(threshold))[0]
    best_by_file: dict[str, dict] = {}

    for raw_index in candidate_indices:
        index = int(raw_index)
        if index < 0 or index >= len(metas):
            continue
        meta = metas[index]
        file_id = meta.get("file_id")
        if not file_id:
            continue
        score = float(best_scores[index])
        current = best_by_file.get(file_id)
        if current is None or score > current["score"]:
            best_by_file[file_id] = {
                **meta,
                "score": score,
                "probe_index": int(best_probes[index]),
            }

    results = sorted(
        best_by_file.values(),
        key=lambda item: item["score"],
        reverse=True,
    )
    if max_results is None:
        return results
    return results[: max(1, int(max_results))]