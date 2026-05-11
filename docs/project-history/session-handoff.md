# Session handoff

Read this first when resuming work on the Diving Planet Bot.

## Current branch context

- Primary working branch: `feature/dev_alvaro`.
- `feature/dev_gadea` was merged into `feature/dev_alvaro` after the Chatwoot button work.
- The branch may be ahead of `origin/feature/dev_alvaro` because merged commits and local reconciliation changes may not yet be pushed.

## What changed recently

- Real Chatwoot `input_select` buttons replaced numeric menu text in the decision tree.
- Button clicks are processed by reading `submitted_values`; a poller exists because local Chatwoot may not emit incoming webhooks for clicks.
- Polling also handles missed incoming messages, with deduplication to prevent double replies.
- Gadea expanded the decision tree, knowledge base, WhatsApp import tooling, retrieval/vector-store logic, and privacy handling.
- RAG was reconciled to preserve PII handling and previous history-aware retrieval/fallback behavior.
- Raw WhatsApp exports and backups are treated as sensitive and should stay ignored/untracked.

## Before modifying code

1. Check `git status --short --branch`.
2. Check for untracked/ignored sensitive files before staging.
3. Read relevant files instead of assuming:
   - `src/channels/chatwoot.py` for webhook, polling, and button handling.
   - `src/flows/decision_tree.py` for menu state and quick replies.
   - `src/agents/supervisor.py` for routing decisions.
   - `src/agents/rag_agent.py` for RAG behavior.
   - `scripts/load_embeddings.py` and `src/knowledge/vector_store.py` for retrieval/KB updates.

## Standard validation

Run after meaningful changes:

```powershell
python -m pytest tests/test_chatwoot_buttons.py tests/test_decision_tree.py tests/test_rag_safety.py
python -m compileall src tests
```

If retrieval changes are touched, also run:

```powershell
python -m pytest tests/test_retrieval_rerank.py
```

## Manual Chatwoot checks

- Start bot locally, usually on port `8001`.
- Open the widget test page.
- Test:
  - `hola` -> language buttons only once.
  - Click `Español` -> main menu buttons.
  - Send free text from a menu -> RAG response, no duplicate answer.
  - Click button options through at least one full booking path.

## Sensitive-data rule

Never stage:

- `wasap/`
- `*_chat.txt`
- raw voice/photo/sticker/contact/PDF exports
- `data/knowledge_base/*.bak`
- `data/knowledge_base/*pre_dedup*`
- real private payment links, phone numbers, emails, documents, or customer-identifying content unless sanitized.
