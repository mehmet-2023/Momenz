"""Eski D1 modülü için uyumluluk katmanı.

Uygulama artık Cloudflare D1 yerine Turso/libSQL kullanıyor. Dosya adı ve
sınıf adları korunarak mevcut içe aktarmaların bozulması önleniyor.
"""

from .turso import D1Client, D1Error, TursoClient, TursoError

__all__ = ["D1Client", "D1Error", "TursoClient", "TursoError"]
