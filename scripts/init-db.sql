-- =============================================================================
-- Initialize databases for Diving Planet Bot + Chatwoot
-- =============================================================================

-- Database for Chatwoot (separate from our app)
CREATE DATABASE chatwoot_production;

-- Enable pgvector extension for our app database (diving_planet)
\c diving_planet;
CREATE EXTENSION IF NOT EXISTS vector;
