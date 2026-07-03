"""add full-text search column to kb_documents

Revision ID: 002
Revises: 001
Create Date: 2026-07-03

Adds content_tsv (generated tsvector) + GIN index for BM25 hybrid search.
Without this column the RAG pipeline falls back to vector-only retrieval.
"""

from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE kb_documents
        ADD COLUMN IF NOT EXISTS content_tsv tsvector
        GENERATED ALWAYS AS (to_tsvector('simple', coalesce(content, ''))) STORED
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS kb_documents_content_tsv_idx
        ON kb_documents USING GIN (content_tsv)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS kb_documents_content_tsv_idx")
    op.execute("ALTER TABLE kb_documents DROP COLUMN IF EXISTS content_tsv")
