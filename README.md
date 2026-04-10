# 🤿 Diving Planet Bot

AI-powered customer service chatbot for **Diving Planet Cartagena** — Colombia's first PADI 5 Star Dive Center with 30 years of experience in the Rosario Islands.

## Architecture

```
Customer (WhatsApp / Web) → Chatwoot → FastAPI Webhook → Decision Tree (Phase 1)
                                                        → LangGraph Agents (Phase 2)
                                                        → Owner Dashboard
```

**Phase 1** — Predefined decision tree (no LLM, zero cost)
- Language selection (ES/EN)
- Guided flow: Tours → Experience level → Service → Location → Booking link
- Escalation to human via Chatwoot

**Phase 2** — LangGraph multi-agent system
- Supervisor agent (GPT-4o-mini) for free-text queries
- RAG agent for knowledge base (pgvector)
- Booking agent for Roverd integration
- Escalation agent with Chatwoot handoff

## Tech Stack

| Component | Technology |
|---|---|
| Agents | LangGraph + LangChain |
| LLM | GPT-4o-mini (OpenAI) |
| API | FastAPI |
| Inbox / Live Chat | Chatwoot (self-hosted) |
| Database | PostgreSQL + pgvector |
| Cache | Redis |
| Observability | LangSmith |
| Channel | WhatsApp Business API |

## Quick Start

### Prerequisites
- Python 3.11+
- Docker Desktop
- OpenAI API key
- LangSmith API key (optional, for tracing)

### Setup

```bash
# Clone and enter the project
git clone https://github.com/YOUR_USER/diving-planet-bot.git
cd diving-planet-bot

# Copy environment variables
cp .env.example .env
# Edit .env with your API keys

# Start infrastructure (Chatwoot + PostgreSQL + Redis)
docker compose up -d

# Install Python dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Start the bot API
python -m src.main
```

### Access

| Service | URL |
|---|---|
| Bot API | http://localhost:8000 |
| Health check | http://localhost:8000/health |
| API docs | http://localhost:8000/docs |
| Chatwoot | http://localhost:3000 |

## Project Structure

```
src/
├── main.py              # FastAPI entry point
├── config.py            # Environment config (pydantic-settings)
├── flows/
│   └── decision_tree.py # Phase 1: predefined guided flow
├── agents/
│   ├── supervisor.py    # Phase 2: LangGraph orchestrator
│   ├── rag_agent.py     # Phase 2: knowledge base retrieval
│   ├── booking_agent.py # Phase 2: Roverd booking integration
│   └── escalation.py    # Human handoff via Chatwoot
├── channels/
│   └── chatwoot.py      # Chatwoot webhook handler
├── knowledge/
│   └── loader.py        # Knowledge base loader
└── db/
    └── models.py        # SQLAlchemy models

data/knowledge_base/
├── services.json        # Service catalog
├── faqs.json            # Frequently asked questions
└── policies.json        # Business policies

tests/
└── test_decision_tree.py
```

## License

Private — Diving Planet Cartagena
