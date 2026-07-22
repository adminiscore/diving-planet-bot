ALTER TABLE kb_documents
ADD COLUMN IF NOT EXISTS content_tsv tsvector
GENERATED ALWAYS AS (to_tsvector('simple', coalesce(content, ''))) STORED;

CREATE INDEX IF NOT EXISTS kb_documents_content_tsv_idx
ON kb_documents USING GIN (content_tsv);
