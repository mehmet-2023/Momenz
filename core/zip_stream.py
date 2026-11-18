from __future__ import annotations

import zipfile
from typing import Iterator


class StreamingZip:
    """``zipfile`` için yazılabilir, parça parça okunabilir akış.

    ZIP'i ``BytesIO`` içinde biriktirmek 200 fotoğrafta 20+ MB RAM harcıyordu.
    Bu sınıf ``ZipFile``'ın yazdığı baytları küçük parçalar halinde dışarı
    verir; Response gövdesi hiçbir zaman tamamen bellekte tutulmaz.
    """

    def __init__(self, chunk_size: int = 64 * 1024) -> None:
        self._chunk_size = max(4096, int(chunk_size))
        self._buffer = bytearray()
        self.offset = 0

    def write(self, data: bytes) -> int:
        self._buffer.extend(data)
        self.offset += len(data)
        return len(data)

    def tell(self) -> int:
        return self.offset

    def flush(self) -> None:
        return None

    def seekable(self) -> bool:
        return False

    def take(self) -> bytes | None:
        if len(self._buffer) < self._chunk_size:
            return None
        chunk = bytes(self._buffer)
        self._buffer.clear()
        return chunk

    def remainder(self) -> bytes | None:
        if not self._buffer:
            return None
        chunk = bytes(self._buffer)
        self._buffer.clear()
        return chunk


def stream_zip(images: Iterator[tuple[str, bytes]], chunk_size: int = 64 * 1024) -> Iterator[bytes]:
    """(dosya_adı, JPEG baytları) üreticisinden ZIP akışı üretir."""
    stream = StreamingZip(chunk_size)
    archive = zipfile.ZipFile(stream, "w", zipfile.ZIP_STORED)
    try:
        for name, data in images:
            archive.writestr(name, data)
            chunk = stream.take()
            if chunk:
                yield chunk
    finally:
        archive.close()
    chunk = stream.remainder()
    if chunk:
        yield chunk
