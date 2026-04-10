"""
RAG Agent for knowledge base retrieval.

Phase 2: Uses pgvector embeddings to answer questions about
Diving Planet services, policies, and FAQs that fall outside
the predefined decision tree.

Knowledge sources:
- Service catalog (data/knowledge_base/services.json)
- FAQs (data/knowledge_base/faqs.json)
- Policies (data/knowledge_base/policies.json)
- Website content (scraped and chunked)
"""

# TODO: Implement with:
# - OpenAI text-embedding-3-small for embeddings
# - pgvector (Supabase) for vector storage
# - Hybrid search (semantic + keyword) for better recall
# - Redis cache for frequent queries
