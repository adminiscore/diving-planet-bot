# 🤿 Diving Planet Bot

AI-powered customer service chatbot for **Diving Planet Cartagena** — Colombia's first PADI 5 Star Dive Center with 30 years of experience in the Rosario Islands.

## Architecture

```
Customer (WhatsApp / Web) → Chatwoot → FastAPI webhook → router (intent)
                                                       → agent node: booking · info
                                                         changes · deflection · safety
                                                       → deterministic layer (facts)
                                                       → reply + Chatwoot handoff
```

The bot is **conversational**, not a button menu: it understands free text (Spanish and
English, with typos, slang and regional phrasing), fills the booking slots it still needs,
and closes with the real booking link. Each use case is handled by its own agent node with
its own focused prompt (`src/prompts/`), on a shared state.

- **Router** — one LLM call per turn produces the routing signals; the node is chosen from
  those signals plus deterministic detectors.
- **booking** — slot-filling subgraph (setup → availability → routing → extraction →
  slot-fill/close), multi-activity carts and companions included.
- **info** — RAG over the knowledge base (pgvector + BM25) with a grounding check.
- **changes** — cancellations, date changes and availability questions.
- **deflection** — contact-details requests, AI-identity questions, off-topic.
- **safety** — PII, medical topics, complaints, broken links, "I want a human" → Chatwoot
  handoff so the team gets notified.
- **Deterministic layer** (`src/flows/`) — prices, links, eligibility and the cart. **Facts
  never come from the LLM**: that is what stops it inventing a price, a slot or a booking.

The guided decision tree of the first version was retired (see `docs/HISTORY.md` 0.21.0);
the migration of the remaining legacy cascade onto the LangGraph graph is tracked in
`docs/multi-agent-refactor-plan.md`.

## Tech Stack

| Component | Technology |
|---|---|
| Agents | LangGraph + LangChain |
| LLM | OpenAI `gpt-4o-mini` (most calls) + `gpt-4.1-mini` (RAG answer) — see "LLM models" below |
| Classifier | Jev (TypeSafe, via OpenRouter) for the router signals |
| API | FastAPI |
| Inbox / Live Chat | Chatwoot (self-hosted) |
| Database | PostgreSQL + pgvector |
| Cache | Redis |
| Observability | `[TURN_METRICS]` log lines (`scripts/turn_metrics.py`); Langfuse paused until 2026-10-16 (free plan used up). LangSmith retired. |
| Channel | WhatsApp Business API |

### LLM models (single source — verified in PRE on 2026-09-25)

The code defaults in `src/config.py` **are** the PRE models, so an environment that sets none of
these variables runs the same bot as PRE. PRE also pins them in `docker-compose.vps.yml` (which
wins over the VPS's `.env.pre`), and `tests/test_models_pinned.py` fails if the two drift apart.
Changing a model means changing both, and measuring it. (Until 2026-09-25 the defaults were
`gpt-4o` / empty and PRE overrode them from its unversioned `.env.pre`.)

| Setting | PRE | Code default | Used by | Verified |
|---|---|---|---|---|
| `OPENAI_MODEL` | `gpt-4o-mini` | same | `condense_query`, grounding judge (`is_grounded`), language detector, conversation summary; RAG answer if `RAG_ANSWER_MODEL` is empty | PRE container + `[TURN_METRICS]` snapshots |
| `RAG_ANSWER_MODEL` | `gpt-4.1-mini` | same | the RAG answer (`rag_agent._answer_with_llm`) | PRE container + snapshots |
| `EXTRACTION_MODEL` | `gpt-4o-mini` | same | router fallback (`detect_routing_signals`), `fill_gaps`, `verify_fields`, `extract_and_verify`, `detect_special_signals`, `resolve_slot_answer`, warm acknowledgement, notes | PRE container + snapshots |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | same | retrieval and `scripts/load_embeddings.py` (must match the index) | PRE container |
| `OPENAI_TRANSCRIPTION_MODEL` | `gpt-4o-mini-transcribe` | same | customer voice notes | PRE container |
| `JEV_MODEL` | `typesafe/jev-1.13` | same | router signals (`JEV_ROUTER_ENABLED`), u3-4 questions | PRE container |

Measurement tools, not the bot: the golden-set judge is `gpt-5-mini` with reasoning `medium`
(`scripts/judge_golden_set.py`); `scripts/replay_diff.py` uses `gpt-5-mini` `low`.

## Environments

The project uses **3 environments**: dev (local), pre (staging VPS), pro (production VPS).

| Environment | Where | Compose file | `.env` file |
|---|---|---|---|
| **dev** | Your PC (Windows) | `docker-compose.yml` | `.env.dev` |
| **pre** | VPS | `docker-compose.vps.yml` | `.env.pre` |
| **pro** | VPS (same server) | `docker-compose.vps.yml` | `.env.pro` |

> **Important for the team**: `.env.*` files contain secrets and are **NOT** committed to git.
> Each developer creates their own from the example templates:

```bash
# After git pull, copy the example and fill in your API keys
cp .env.dev.example .env.dev
# Edit .env.dev with your own OPENAI_API_KEY and other secrets
```

The `.example` files are tracked in git and serve as documentation for required variables.

## Quick Start (DEV — Local)

### Prerequisites
- Python 3.11+ ([download](https://www.python.org/downloads/))
- Docker Desktop ([download](https://www.docker.com/products/docker-desktop/))
- OpenAI API key
- LangSmith API key (optional, for tracing)

### Setup

```bash
# Clone and enter the project
git clone https://github.com/YOUR_USER/diving-planet-bot.git
cd diving-planet-bot

# 1. Create your environment file (this file is gitignored — never commit it!)
cp .env.dev.example .env.dev
# Edit .env.dev with your OPENAI_API_KEY and other secrets

# 2. Start infrastructure (PostgreSQL + Redis only)
docker compose up -d

# 3. (Optional) Start Chatwoot locally
docker compose --profile chatwoot up -d

# 4. Create Chatwoot database (if using Chatwoot)
docker exec dp-dev-postgres psql -U postgres -c "CREATE DATABASE chatwoot_dev;"

# 5. Install Python dependencies
pip install -e ".[dev]"

# 6. Load knowledge base embeddings
python -m scripts.load_embeddings

# 7. Run tests — ENV_FILE matters. `.env.ci` carries a dummy OpenAI key, so the
#    extraction/verification nets fail fast and the suite is deterministic (this is
#    what CI does). Plain `pytest` picks up `.env`, hits the real API, and turns a
#    ~2 min run into ~20 min of flaky, billable calls.
ENV_FILE=.env.ci pytest

# 8. Start the bot API
ENV_FILE=.env.dev python -m src.main
```

### Access (DEV)

| Service | URL |
|---|---|
| Bot API | http://localhost:8000 |
| Health check | http://localhost:8000/health |
| API docs | http://localhost:8000/docs |
| Chatwoot | http://localhost:3000 |

## Deploy (VPS — PRE + PRO)

```bash
# On the VPS, after cloning the repo:

# 1. Create environment files with strong passwords
cp .env.pre.example .env.pre
cp .env.pro.example .env.pro
# Edit both with real API keys and strong passwords

# 2. Start all services (Chatwoot has its own dedicated Postgres/Redis,
#    independent of dp-pre-* and dp-pro-*)
docker compose -f docker-compose.vps.yml up -d --build

# 3. Load embeddings (staging)
docker exec dp-pre-bot python -m scripts.load_embeddings

# 4. Load embeddings (production)
docker exec dp-pro-bot python -m scripts.load_embeddings

# 5. Verify
curl https://pre.divingplanet.org/health
curl https://api.divingplanet.org/health
```

### Access (VPS)

| Service | URL |
|---|---|
| Staging API | https://pre.divingplanet.org |
| Production API | https://api.divingplanet.org |
| Chatwoot | https://chatwoot.divingplanet.org |

## Project Structure

```
src/
├── main.py                  # FastAPI entry point
├── config.py                # Environment config (pydantic-settings) + feature flags
├── state_store.py           # Conversation state <-> Redis
├── orchestration/           # The LangGraph graph (router -> agent nodes)
│   ├── state.py             #   BotState (shared contract)
│   ├── router.py            #   intent router: which node handles this turn
│   └── graph.py             #   StateGraph: nodes + conditional edges
├── agents/                  # One node per use case (+ the LLM nets they call)
│   ├── booking_agent.py     #   booking: slot-filling subgraph (5 phases)
│   ├── info_agent.py        #   info: eligibility + RAG answers
│   ├── changes_agent.py     #   changes: cancel / reschedule / availability
│   ├── deflection_agent.py  #   deflection: contact requests, AI-identity, off-topic
│   ├── escalation_agent.py  #   safety: PII, medical, complaints, human handoff
│   ├── conversational_core.py #  the booking phases (shared by graph and cascade)
│   ├── supervisor.py        #   legacy cascade — still live behind `agent_arch` off
│   ├── rag_agent.py         #   knowledge base retrieval + answer composition
│   ├── grounding_check.py   #   answer must be grounded in retrieved context
│   ├── intent_detector.py   #   deterministic (regex) extraction, first pass
│   └── llm_extractor.py     #   LLM nets: gap-fill, turn signals, slot resolver
├── prompts/                 # Prompts as a first-class artifact, one module per node
│   ├── router.py            #   routing signals (prompt + tool schema)
│   ├── booking.py           #   language, extraction, signals, slot resolver, ack
│   ├── info.py              #   query rewrite, Coral persona + rules, grounding
│   └── memory.py            #   open facts (notes), rolling summary
├── flows/                   # DETERMINISTIC layer — prices, links, eligibility
│   ├── catalog.py           #   service catalog (the single source of prices/links)
│   ├── cart_render.py       #   cart rendering + final summary
│   ├── eligibility.py       #   age / certification rules
│   ├── state.py             #   ConversationState + Step
│   └── messages.py          #   canned copy + quick replies
├── channels/
│   ├── chatwoot.py          # Chatwoot webhook handler
│   └── audio.py             # voice-note transcription
├── knowledge/
│   ├── loader.py            # Knowledge base loader
│   └── vector_store.py      # pgvector + BM25 hybrid retrieval
└── db/
    └── models.py            # SQLAlchemy models

data/knowledge_base/
├── services.json        # Service catalog
├── faqs.json            # Frequently asked questions
└── policies.json        # Business policies
```

The bot is mid-refactor to this multi-agent graph; `docs/multi-agent-refactor-plan.md`
is the source of truth for what is done and what is next. Facts (prices, links,
availability) are **never** produced by an LLM — they come from `src/flows/`.

## License

Private — Diving Planet Cartagena
