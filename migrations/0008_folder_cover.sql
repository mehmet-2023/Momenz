-- Etkinlik kapağı artık klasör index'inde seçiliyor: en az 4 yüzlü (toplu)
-- fotoğraf tercih edilir. Eski satırlar ilk dosyaya düşer; backfill script'i
-- scripts/backfill_covers.py ile mevcut kayıtlar güncellenebilir.
ALTER TABLE folder_matrices ADD COLUMN cover_file_id TEXT;
