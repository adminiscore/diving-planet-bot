-- =============================================================================
-- Initialize databases for Diving Planet Bot + Chatwoot
-- =============================================================================

-- Database for Chatwoot (separate from our app)
-- Run: docker exec dp-postgres psql -U postgres -c "CREATE DATABASE chatwoot_production;"

-- Enable pgvector extension for our app database (diving_planet)
-- Run: docker exec dp-postgres psql -U postgres -d diving_planet -f /docker-entrypoint-initdb.d/init-db.sql
CREATE EXTENSION IF NOT EXISTS vector;

-- Knowledge base documents table for RAG
CREATE TABLE IF NOT EXISTS kb_documents (
    id SERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    embedding vector(1536),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Index for fast similarity search
CREATE INDEX IF NOT EXISTS kb_documents_embedding_idx
    ON kb_documents USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 10);
