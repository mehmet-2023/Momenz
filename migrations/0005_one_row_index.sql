-- Klasörün TÜM face index'i artık tek satırda. worker bu satırı 1 kez okuyup
-- bellekte patchler, 1 kez yazar; arama/listelemeler de aynı satırdan okur.
ALTER TABLE folder_matrices ADD COLUMN files BLOB;
ALTER TABLE folder_matrices ADD COLUMN images INTEGER NOT NULL DEFAULT 0;
ALTER TABLE folder_matrices ADD COLUMN done INTEGER NOT NULL DEFAULT 0;
ALTER TABLE folder_matrices ADD COLUMN no_face INTEGER NOT NULL DEFAULT 0;
ALTER TABLE folder_matrices ADD COLUMN errors INTEGER NOT NULL DEFAULT 0;
ALTER TABLE folder_matrices ADD COLUMN first_file_id TEXT;
ALTER TABLE folder_matrices ADD COLUMN meta TEXT NOT NULL DEFAULT '{}';
