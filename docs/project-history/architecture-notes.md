# Architecture notes

## Main runtime flow

1. Chatwoot sends webhooks to `/webhooks/chatwoot`.
2. `src/channels/chatwoot.py` extracts user input, manages in-memory `ConversationState`, routes through `src/agents/supervisor.py`, and sends replies back to Chatwoot.
3. `src/agents/supervisor.py` decides between decision tree, RAG, and escalation.
4. `src/flows/decision_tree.py` handles deterministic menus, service selection, booking summaries, and quick replies.
5. `src/agents/rag_agent.py` answers free-text questions using `src/knowledge/vector_store.py` and OpenAI.

## Chatwoot buttons

- Decision tree options are sent as `input_select` messages with `content_attributes.items` containing `{title, value}`.
- Numeric compatibility remains: values are internal numbers (`1`, `2`, etc.), and user text matching button titles is accepted.
- Chatwoot local/self-hosted may not emit a fresh incoming webhook after a button click. The bot polls active conversations through the Chatwoot API and reads `content_attributes.submitted_values`.
- Deduplication keys prevent webhook and polling from processing the same incoming message or button click twice.

## RAG behavior

- `rag_answer()` performs PII detection before retrieval.
- Retrieval query is built from the current message plus recent user history via `build_retrieval_query()`.
- Low-confidence retrieval falls back instead of hallucinating, using `settings.rag_min_score`.
- Logs include source names and top scores to debug retrieval quality.
- Answers must use only retrieved context and should offer human advisor handoff when confidence is low.

## Knowledge base

Versioned KB should be curated/sanitized JSON under `data/knowledge_base/`.

Important files include:

- `services.json`
- `faqs.json`
- `policies.json`
- `pricing.json`
- `availability.json`
- `conversations.json`
- `brand_tone.json`

Do not version raw WhatsApp exports, media, contact cards, voice notes, PDFs, or backup dumps.

## Embeddings and vector store

- `scripts/load_embeddings.py` converts KB JSON into documents and stores embeddings in PostgreSQL/pgvector.
- `src/knowledge/vector_store.py` performs similarity search and may use metadata/reranking logic introduced by the Gadea merge.
- OpenAI embedding model is configured through `settings.openai_embedding_model`.

## Local development

- Chatwoot local URL: `http://localhost:3300`.
- Bot commonly runs on `http://localhost:8001` in local tests.
- Widget test page: `chatwood-test.html`.
- Useful validation commands:
  - `python -m pytest tests/test_chatwoot_buttons.py tests/test_decision_tree.py tests/test_rag_safety.py`
  - `python -m compileall src tests`

## Current risks

- In-memory conversation state is not persistent across bot restarts.
- Chatwoot local webhooks can be unreliable, so polling is an operational workaround.
- Raw historical exports must remain outside Git; only sanitized derived examples should be committed.
- Large decision-tree changes should be tested manually in Chatwoot and with unit tests.
