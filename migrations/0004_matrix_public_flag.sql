-- Arama sorgusu artık yalnızca folder_matrices satırını okuyor; yayın
-- durumunu da bu satırda tutuyoruz (event/is_public ile eş tutulur).
ALTER TABLE folder_matrices ADD COLUMN is_public INTEGER NOT NULL DEFAULT 0;
UPDATE folder_matrices SET is_public = EXISTS(SELECT 1 FROM events WHERE events.folder_key = folder_matrices.folder_key AND events.is_public = 1);
