# ⚖️ Legal AI Agent

A production-grade **Agentic RAG** system for Indian law — built on **LangGraph**, **Hybrid Search (BM25 + ChromaDB + RRF)**, and **Claude Sonnet**.

## Architecture

```
User Query
    │
    ▼
┌───────────────┐
│  Supervisor   │  Intent classification (advisor vs contract)
│  (Haiku)      │
└───────┬───────┘
        │
    ┌───┴────────────────────────────┐
    │                                │
    ▼                                ▼
┌──────────────────┐       ┌──────────────────────┐
│  RAG Retriever   │       │  Contract Analyzer    │
│  (4-Tier Water-  │       │  (Structured JSON     │
│   fall)          │       │   Risk Report)        │
│  ┌─────────────┐ │       └──────────────────────┘
│  │ Tier 1:     │ │
│  │ Semantic    │ │
│  │ Cache       │ │
│  │ Tier 2:     │ │
│  │ ChromaDB    │ │
│  │ (Dense)     │ │
│  │ Tier 3:     │ │
│  │ BM25 +      │ │
│  │ RRF Fusion  │ │
│  │ Tier 4:     │ │
│  │ Fallback    │ │
│  └─────────────┘ │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Legal Advisor   │
│  (Claude Sonnet) │
└──────────────────┘
         │
         ▼
┌──────────────────┐
│ LLM-as-Judge     │  Optional RAG quality scoring
│ (Claude Haiku)   │  Faithfulness / Relevance / Helpfulness
└──────────────────┘
```

## Project Structure

```
legal-ai-agent/
├── app.py               # Streamlit UI (threads, eval, export)
├── agent_graph.py       # LangGraph state machine
├── prompts.py           # All system prompts
├── rag_vectorstore.py   # Hybrid retrieval (BM25 + ChromaDB + RRF)
├── utils.py             # SQLite persistence + thread management
├── evaluator.py         # LLM-as-Judge quality scorer
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example         # Copy to .env and fill in your key
├── data/                # ← Add your Indian law PDFs/text here
└── chroma_db/           # Auto-created on first run
```

## Quick Start (Local)

```bash
# 1. Clone and setup
git clone <your-repo>
cd legal-ai-agent
python -m venv venv && source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# 4. Add Indian law documents (optional but recommended)
#    Place PDFs/TXTs in the data/ folder:
#    - IPC 1860.pdf
#    - CrPC 1973.pdf
#    - Constitution of India.pdf
#    - Consumer Protection Act 2019.txt
#    etc.

# 5. Run
streamlit run app.py
```

Open http://localhost:8501

## Docker Deployment

```bash
# Build and run with docker-compose (recommended)
docker-compose up --build

# Or one-liner
docker build -t legal-ai-agent .
docker run -p 8501:8501 \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/chroma_db:/app/chroma_db \
  -v $(pwd)/legal_agent.db:/app/legal_agent.db \
  legal-ai-agent
```

## Features

| Feature | Details |
|---|---|
| **Legal Advisor Mode** | Structured Q&A with IPC/CrPC/Constitution citations |
| **Contract Analyzer** | JSON risk report with per-clause scores + revision suggestions |
| **Hybrid Retrieval** | BM25 + ChromaDB semantic search + Reciprocal Rank Fusion |
| **4-Tier RAG Waterfall** | Semantic cache → Dense → Sparse+RRF → Fallback |
| **Persistent Threads** | SQLite-backed conversations with load/delete/export |
| **LLM-as-Judge** | Faithfulness, Relevance, Helpfulness scoring via Claude Haiku |
| **Thread Export** | Download any conversation as Markdown |
| **Auto Thread Titles** | Named from first user message |

## Recommended Indian Law Documents for RAG

Add these to `data/` for best retrieval quality:

- Indian Penal Code, 1860 (IPC)
- Code of Criminal Procedure, 1973 (CrPC)
- Constitution of India
- Consumer Protection Act, 2019
- Information Technology Act, 2000
- Indian Contract Act, 1872
- Transfer of Property Act, 1882
- Arbitration and Conciliation Act, 1996

Sources: [India Code](https://www.indiacode.nic.in/) | [Indian Kanoon](https://indiankanoon.org/)

## Models Used

| Role | Model | Why |
|---|---|---|
| Legal Advisor | `claude-sonnet-4-6` | High reasoning, precise citations |
| Contract Analyzer | `claude-sonnet-4-6` | Complex structured JSON output |
| Supervisor (router) | `claude-haiku-4-5-20251001` | Fast, cheap intent classification |
| LLM-as-Judge | `claude-haiku-4-5-20251001` | Cost-efficient quality scoring |

## Disclaimer

> This system provides AI-generated legal information only. It is not a substitute for professional legal advice from a licensed advocate. Always consult a qualified legal professional for your specific situation.
