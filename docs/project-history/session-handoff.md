# Session handoff

Read this file before changing code in the Diving Planet Bot. For a quick version overview, read `docs/HISTORY.md` first.

## Current branch and workflow

- Main collaboration branch: `feature/dev_alvaro`.
- Always start with `git status --short --branch` and check whether the branch is ahead/behind the remote.
- Use `/start-context` at the beginning of a session and `/close-work` before committing/pushing.
- `/close-work` must review this file and update it whenever architecture, workflow, risks, validation, current product context, environment details, or next-session priorities changed.
- Do not mix unrelated work in the same commit; keep decision-tree, RAG, infrastructure, and data-cleanup changes separated when possible.

## Architecture snapshot

1. Chatwoot sends webhooks to `/webhooks/chatwoot`.
2. `src/channels/chatwoot.py` extracts user input, manages in-memory `ConversationState`, routes through the supervisor, and sends replies back to Chatwoot.
3. `src/agents/supervisor.py` routes between deterministic decision tree, RAG, and escalation.
4. `src/flows/decision_tree.py` owns menu states, quick replies, booking summaries, and deterministic flows; it loads service details from `data/knowledge_base/services.json`.
5. `src/agents/rag_agent.py` answers free text using sanitized knowledge-base content through `src/knowledge/vector_store.py`.

- Real Chatwoot `input_select` buttons replaced numeric menu text in the decision tree.
- Button clicks are processed by reading `submitted_values`; a poller exists because local Chatwoot may not emit incoming webhooks for clicks.
- Polling also handles missed incoming messages, with deduplication to prevent double replies.
- Gadea expanded the decision tree, knowledge base, WhatsApp import tooling, retrieval/vector-store logic, and privacy handling.
- RAG was reconciled to preserve PII handling and previous history-aware retrieval/fallback behavior.
- Decision tree pricing (`PRICING_MENU`) and logistics (`LOGISTICS_MENU` + `ISLAND_MENU` / `ISLAND_HOTEL_MENU`) menus were refined based on real conversations: clearer options for salidas desde Cartagena vs. clientes ya en las islas, paquetes 5/7/9 buceos, y submenús de logística (punto de encuentro/horarios, alojamiento/recogida, qué incluye/no incluye y qué llevar). `docs/arbol_opciones_es.md` y `TODO.md` se actualizaron para reflejar estos cambios.
- `services.json` is now the source of truth for service names, prices, inclusions, requirements, itineraries, and booking links used by the decision tree. The tree maps base services to `*_already_on_island` variants when the user is already in the islands and now exposes PADI specialties in the guided course menu.
- Raw WhatsApp exports and backups are treated as sensitive and should stay ignored/untracked.
- Country flag emojis (🇨🇴, 🇺🇸) do not render on Windows — replaced throughout with 🌎/🌐 for cross-platform compatibility.
- `src/agents/lead_summary.py` builds structured private Chatwoot notes on escalation; `state.pending_note` holds the note until sent in `chatwoot.py`.
- Lead notes are sent for all escalation types: keyword (`humano`, `agente`...), sensitive (medical, weather, complaints), and tree-internal escalation.
- `chatwoot.py` now performs the real human handoff by calling `escalate_to_human()` after sending the private lead note; `pending_escalation_reason` is only cleared when Chatwoot confirms the status toggle, so failed handoffs can be retried on later activity.
- `.claude/commands/runtests.md` provides a `/runtests` skill to run the conversation dataset (223 tests, 21 blocks) with block-level keyword filtering.
- `chatwoot.py` auto-assigns new conversations to the owner agent (`CHATWOOT_OWNER_AGENT_ID` in `.env`) via `POST /conversations/{id}/assignments` so they appear in the "Mine" view without relying on Chatwoot UI auto-assignment. Set `CHATWOOT_OWNER_AGENT_ID=0` to disable.
- `supervisor.py` routing hardening: `_matches_escalation_keyword` uses word-boundary regex to prevent "persona" false positive; `_is_substantive_free_text` strips trailing punctuation so "hey?" routes to welcome; any bare greeting mid-flow (hola, hi, buenas…) resets state to WELCOME step.
- RAG system prompt (ES + EN) has an explicit DIVE TO HEAL exception: disability/accessibility questions about the adaptive diving program are answered with factual program info, not escalated as medical.
- `load_embeddings.py` now indexes `pricing.json` fully (8 origin × section pairs × 2 langs + 2 discount_policy docs = 441 total KB documents) and includes COP prices in `services.json` embeddings.

## Current product context

- The bot supports Spanish/English decision-tree flows and free-text RAG answers.
- Chatwoot buttons are sent as `input_select` quick replies, while numeric/text fallback still works.
- Local Chatwoot may not always emit incoming webhooks for button clicks, so the bot includes polling/deduplication logic.
- The decision tree has recently been improved for:
  - Cartagena certified 2 dives / 1 day.
  - Cartagena beginner branch: minicourse, snorkeling, private service.
  - Cartagena certified multi-day packages: 5/7/9 dives, lodging/nocturnal notes, and refresher handling.
  - Island-based certified and beginner service variants from `services.json`.
  - PADI advanced/professional courses and specialties.
- `faqs.json` has been expanded with curated educational diving content for beginners, safety, equipment, course comparisons, underwater sensations, marine-life etiquette, and Rosario Islands destination knowledge.
- Current MVP direction: inform, qualify, recommend, and prepare human-assisted conversion; do not automate live availability, payment, or final booking confirmation yet.
- Conversation-state migration from in-memory storage to Redis/PostgreSQL is intentionally deferred during dev; treat it as a last hardening step right before moving to PRE.
- Use `docs/mvp-intent-matrix.md` and `docs/kb-audit-mvp.md` before expanding tree/RAG behavior.
- `docs/infra-simple.excalidraw` contains the current minimal infrastructure scheme for team communication.
- Mixed groups, private services, pricing, booking/payment, **cancellation/change rules** (major KB gap — needs owner confirmation), and logistics constraints by hotel/island are still areas for systematic polishing.
- COP pricing is now in the KB; bot needs a restart in WSL2 to serve it after the re-index run.
- `CHATWOOT_OWNER_AGENT_ID=1` should be added to `.env` (owner agent ID confirmed via `/api/v1/profile`).
- Next session priorities: cancellation/payment policy KB completion, PRE deployment checklist, and live E2E test of COP price answers after bot restart.

## Knowledge base and privacy

- Versioned KB lives under `data/knowledge_base/` and must be curated/sanitized.
- Important KB files: `services.json`, `faqs.json`, `policies.json`, `pricing.json`, `availability.json`, `conversations.json`, `brand_tone.json`.
- Treat `faqs.json` as curated public-facing content: keep new entries bilingual, consolidated by topic, and avoid adding medical clearance, live availability, unsanitized customer details, or unverified booking/payment claims.
- Never stage raw exports or private customer data:
  - `wasap/`
  - raw `_chat.txt` exports
  - voice/photo/sticker/contact/PDF exports
  - `data/knowledge_base/*.bak`
  - `data/knowledge_base/*pre_dedup*`
  - real private payment links, IDs, phone numbers, emails, documents, or customer-identifying content unless sanitized.

## Standard validation

Run after meaningful code changes:

```powershell
python -m pytest tests/test_chatwoot_buttons.py tests/test_decision_tree.py tests/test_rag_safety.py
python -m compileall src tests
```

If retrieval, embeddings, or vector-store behavior changes, also run:

```powershell
python -m pytest tests/test_retrieval_rerank.py
```

## Dev environment notes

- Bot runs in WSL2 Ubuntu on port 8000: `python -m src.main` (with conda base active).
- Chatwoot runs in Docker on port 3300: `docker compose --profile chatwoot up -d`.
- Chatwoot webhook is configured in the DB (`chatwoot_dev.webhooks`) pointing to `http://host.docker.internal:8000/webhooks/chatwoot`.
- Webhook subscriptions must include `message_created`, `message_updated`, `conversation_created`, `conversation_status_changed`. Missing `message_updated` means button clicks are ignored.
- `host.docker.internal` from Docker resolves to `192.168.65.254` (Docker Desktop host), which reaches WSL2 bot via Docker Desktop port bridging.
- `CHATWOOT_BASE_URL=http://localhost:3300` in `.env` is correct for bot→Chatwoot API calls from WSL2.
- To verify webhook config: `docker exec dp-dev-postgres psql -U postgres -d chatwoot_dev -c 'SELECT id, url, subscriptions FROM webhooks;'`
- `chatwood-test.html` uses websiteToken `rcTJ5Awm3fZN7eAtoMnXVzVF` (Diving Planet Web inbox).

## Manual Chatwoot checks

When touching Chatwoot, buttons, routing, or conversation state:

- Start the bot: `python -m src.main` in WSL2 Ubuntu (conda base).
- Start Chatwoot: `docker compose --profile chatwoot up -d`.
- Open `chatwood-test.html` in a browser.
- Test `hola` → language buttons (🌎 Español / 🌐 English).
- Click `Español` → main menu buttons.
- Send free text from a menu → RAG response without duplicate replies.
- Click through at least one full booking path.

## Where to look first

- `docs/HISTORY.md`: version-level overview.
- `docs/mvp-intent-matrix.md`: commercial intent ownership across tree, RAG, and human handoff.
- `docs/kb-audit-mvp.md`: current KB coverage and gaps for MVP robustness.
- `docs/infra-simple.excalidraw`: simple current infrastructure diagram.
- `src/flows/decision_tree.py`: deterministic flow and service catalog.
- `tests/test_decision_tree.py`: expected decision-tree behavior.
- `src/agents/supervisor.py`: routing rules.
- `src/agents/rag_agent.py`: free-text answering and safety prompt.
- `src/channels/chatwoot.py`: webhook, polling, and message sending.
- `TODO.md`: current product backlog and branch-polishing checklist.
