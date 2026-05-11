# Timeline

## Initial base

- `94c6b09 Initial commit`: repository baseline.
- `d3b6735 feat: implement Phase 1 decision tree with Chatwoot integration`: initial deterministic decision tree and Chatwoot webhook/API channel.
- `201ec76 feat: implement Phase 2 - RAG agent + supervisor routing`: RAG agent and supervisor routing between decision tree, retrieval, and escalation.
- `705c25 feat(kb): add pricing/availability/discounts/escalation + real conversations; update embeddings loader`: early knowledge-base expansion and embedding loader updates.

## Multi-environment work

- `5081014 feat: multi-environment infrastructure (dev/pre/pro)`: Dockerfile, VPS compose/Caddy setup, `.env.*.example` templates, `ENV_FILE` config support, and README/TODO environment workflow.

## Chatwoot local testing and button work

- Local Chatwoot was tested at `http://localhost:3300`; widget test page uses `chatwood-test.html`.
- Bot has often run locally on `http://localhost:8001` because port `8000` was occupied.
- Chatwoot webhooks in local dev can be unreliable; outgoing `input_select` button clicks update `submitted_values` but may not emit a new incoming webhook.
- `16279ae feat: implement interactive buttons in Chatwoot decision tree` introduced real Chatwoot `input_select` buttons, preserved numeric/text fallback parsing, and added API polling/deduplication to process button clicks and missed incoming messages.

## Gadea branch merge

Merged `origin/feature/dev_gadea` into `feature/dev_alvaro`, bringing:

- `b2a3502 Update Bot`
- `fcaeb17 Upgrade decission tree`
- `3fe7671 Upgrade 🤿 2 Buceos - 1 día`

Main additions:

- Larger decision tree and Spanish option documentation.
- Expanded `data/knowledge_base/conversations.json`, FAQs, and policies.
- Scripts for importing/cleaning WhatsApp conversation exports.
- Retrieval evaluation test and vector-store/RAG updates.
- `src/privacy.py` with privacy/PII handling.

Merge reconciliation:

- Conflicts occurred in `conversations.json`, `scripts/load_embeddings.py`, and `src/agents/rag_agent.py` when reapplying local changes.
- The merged Gadea versions were kept for the knowledge base/loader conflicts.
- `rag_agent.py` was reconciled to keep privacy/PII handling plus previous improvements: history-aware retrieval query, confidence fallback via `rag_min_score`, source/score logging, and safer fallbacks.

## Sensitive-data cleanup

Raw WhatsApp exports and backup dumps from `wasap/` and `data/knowledge_base/*.bak` are not suitable for Git. They were removed from the index with `git rm --cached` and protected via `.gitignore`, while local files were kept on disk.
