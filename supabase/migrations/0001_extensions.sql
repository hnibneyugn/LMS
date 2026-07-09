-- 0001_extensions.sql
-- Enable pgvector for RAG embeddings. Must run before any table uses the `vector` type.

create extension if not exists vector;
