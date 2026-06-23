# agent_graph.py
import os
import json
import re
import time
from typing import TypedDict, Annotated, List, Literal
from operator import add
from functools import wraps

# FIX: load .env defensively here as well — see rag_vectorstore.py for why.
from dotenv import load_dotenv
load_dotenv()

from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from prompts import (
    LEGAL_ADVISOR_SYSTEM,
    CONTRACT_ANALYZER_SYSTEM,
    FALLBACK_SYSTEM,
)
from rag_vectorstore import retriever
from rate_limiter import api_rate_limiter, RateLimitError

google_api_key = os.getenv("GOOGLE_API_KEY")
if not google_api_key:
    raise RuntimeError(
        "GOOGLE_API_KEY is not set. Create a free key at "
        "https://aistudio.google.com/app/apikey and put it in your .env file."
    )

# ── LLM Client (Gemini free tier only) ────────────────────────────────────
# gemini-2.5-flash is the current free-tier default for generation tasks.
# gemini-2.0-flash is deprecated (shutdown scheduled mid-2026) — do not use.
# Pro-tier models are no longer available on the free tier as of 2026.
llm_primary = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=google_api_key,
    temperature=0.1,
    max_output_tokens=1536,   # trimmed from 2048 — most answers don't need it
    max_retries=2,
)

# ── Helper: Token Estimation & Safe Invoke with Retry ─────────────────────
def estimate_tokens(messages: List) -> int:
    """Rough token estimate from message content (chars/4 heuristic)."""
    total_chars = sum(len(str(m.content)) for m in messages)
    return total_chars // 4


def retry_with_backoff(max_attempts=3, base_delay=10):
    """Retries on 429 / 503 / RESOURCE_EXHAUSTED / UNAVAILABLE with exponential backoff."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except RateLimitError:
                    # Daily quota is gone — retrying won't help, fail fast.
                    raise
                except Exception as e:
                    error_str = str(e)
                    if any(s in error_str for s in ("429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE")):
                        if attempt < max_attempts - 1:
                            delay = base_delay * (2 ** attempt)
                            print(f"⏳ Rate limit hit. Retrying in {delay}s "
                                  f"(attempt {attempt + 1}/{max_attempts})")
                            print(f"📊 {api_rate_limiter.get_status()}")
                            time.sleep(delay)
                            continue
                        raise Exception(
                            "Gemini free-tier rate limit exceeded after retries. "
                            "Wait a few minutes or check quota at "
                            "https://aistudio.google.com/app/rate-limit"
                        )
                    raise
            raise Exception("Max retry attempts exceeded")
        return wrapper
    return decorator


@retry_with_backoff(max_attempts=3, base_delay=10)
def safe_invoke(llm, messages: List, output_buffer: int = 1000):
    """Safely invoke the LLM with local rate-limit guarding and retry logic."""
    input_tokens = estimate_tokens(messages)
    api_rate_limiter.acquire(input_tokens, output_buffer)
    return llm.invoke(messages)


# ── Agent State ────────────────────────────────────────────────────────────
class AgentState(TypedDict):
    messages: Annotated[List[dict], add]
    mode: str
    next: str
    rag_context: str
    rag_tier: str
    raw_query: str
    contract_result: dict


# ── Node: Supervisor (RULE-BASED, NO API CALL — keep this, it's free) ─────
CONTRACT_KEYWORDS = [
    "contract", "agreement", "clause", "terms and conditions",
    "analyze this contract", "review contract", "legal document",
    "nda", "non-disclosure", "service agreement", "employment contract",
]

def supervisor_node(state: AgentState):
    """Routes the query with zero-cost rule-based logic — no API call."""
    last_msg = state["messages"][-1]["content"].lower()

    if state.get("mode") == "contract":
        print("📋 Routing to Contract Analyzer (mode selected)")
        return {"next": "contract_analyzer", "raw_query": state["messages"][-1]["content"]}

    for keyword in CONTRACT_KEYWORDS:
        if keyword in last_msg:
            print(f"📋 Routing to Contract Analyzer (keyword: '{keyword}')")
            return {"next": "contract_analyzer", "raw_query": state["messages"][-1]["content"]}

    print("⚖️ Routing to Legal Advisor (default)")
    return {"next": "legal_advisor", "raw_query": state["messages"][-1]["content"]}


# ── Node: RAG Retriever ─────────────────────────────────────────────────────
def rag_retriever_node(state: AgentState):
    """Retrieves relevant documents using the hybrid search pipeline."""
    query = state.get("raw_query", "")
    try:
        docs, tier = retriever.retrieve(query, top_k=5)
        context = retriever.format_context(docs)
        print(f"✅ Retrieved {len(docs)} documents (tier: {tier})")
    except Exception as e:
        print(f"[RAG] Error in retriever node: {e}")
        context = "Retrieval error — operating in fallback mode."
        tier = "fallback"
    return {"rag_context": context, "rag_tier": tier}


# ── Node: Legal Advisor ──────────────────────────────────────────────────────
def legal_advisor_node(state: AgentState):
    """Generates legal advice using RAG context, with real conversation history."""
    query = state.get("raw_query", "")
    context = state.get("rag_context", "")
    tier = state.get("rag_tier", "fallback")

    if tier == "fallback" or "No relevant" in context:
        system_prompt = FALLBACK_SYSTEM
        print("⚠️ Using FALLBACK mode (no RAG context)")
    else:
        system_prompt = LEGAL_ADVISOR_SYSTEM.format(context=context)
        print("📚 Using RAG context for legal advice")

    # FIX: app.py now passes real prior turns into state["messages"], so this
    # slice actually does something (previously it always sliced an empty list
    # because only the current message was ever sent in).
    # Keep only the last 3 prior turns to bound token usage — older context
    # is dropped rather than accumulating forever.
    history = []
    recent_messages = state["messages"][-7:-1]  # up to 3 user+assistant pairs, excluding current
    for msg in recent_messages:
        if msg["role"] == "user":
            history.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            # Strip the retrieval-tier footer before it goes back into context —
            # no need to pay tokens for our own UI label.
            clean = re.sub(r"\n---\n\*Retrieval:.*\*$", "", msg["content"]).strip()
            history.append(AIMessage(content=clean))

    messages = [SystemMessage(content=system_prompt)] + history + [HumanMessage(content=query)]

    try:
        print("🔄 Calling Gemini (gemini-2.5-flash) for legal advice...")
        response = safe_invoke(llm_primary, messages, output_buffer=1200)
        answer = response.content

        tier_label = {
            "cache": "⚡ Semantic Cache",
            "hybrid": "🔍 Hybrid RAG (Dense + BM25 + RRF)",
            "fallback": "⚠️ Fallback Mode (No RAG context)",
        }.get(tier, tier)
        answer += f"\n---\n*Retrieval: {tier_label}*"

        print("✅ Legal advice generated successfully")
        print(f"📊 {api_rate_limiter.get_status()}")
    except RateLimitError as e:
        answer = f"⚠️ {str(e)} Please try again after the daily quota resets."
    except Exception as e:
        answer = f"Legal advisor encountered an error: {str(e)}. Please retry."

    return {"messages": [{"role": "assistant", "content": answer}]}


# ── Node: Contract Analyzer ──────────────────────────────────────────────────
def contract_analyzer_node(state: AgentState):
    """Analyzes contract text and returns a structured JSON risk assessment."""
    contract_text = state.get("raw_query", "")
    messages = [
        SystemMessage(content=CONTRACT_ANALYZER_SYSTEM),
        HumanMessage(content=f"Analyze this contract:\n\n{contract_text}"),
    ]

    def _error_payload(msg: str, recommendation: str) -> dict:
        return {
            "overall_risk_score": 0,
            "risk_level": "ERROR",
            "summary": msg,
            "issues": [],
            "positive_clauses": [],
            "missing_clauses": [],
            "recommendations": [recommendation],
        }

    try:
        print("🔄 Calling Gemini (gemini-2.5-flash) for contract analysis...")
        response = safe_invoke(llm_primary, messages, output_buffer=1800)
        raw = response.content.strip()
        raw = re.sub(r"```json|```", "", raw).strip()
        parsed = json.loads(raw)
        print("✅ Contract analysis completed")
        print(f"📊 {api_rate_limiter.get_status()}")
        return {"contract_result": parsed, "messages": [{"role": "assistant", "content": raw}]}

    except RateLimitError as e:
        payload = _error_payload(str(e), "Try again after the daily quota resets.")
        return {"contract_result": payload, "messages": [{"role": "assistant", "content": json.dumps(payload)}]}

    except json.JSONDecodeError as e:
        payload = _error_payload(
            f"Failed to parse contract analysis. JSON error: {str(e)}",
            "Re-paste the contract text and retry.",
        )
        return {"contract_result": payload, "messages": [{"role": "assistant", "content": json.dumps(payload)}]}

    except Exception as e:
        payload = _error_payload(f"Agent error: {str(e)}", "Check API connectivity and retry.")
        return {"contract_result": payload, "messages": [{"role": "assistant", "content": json.dumps(payload)}]}


# ── Routing Function ─────────────────────────────────────────────────────────
def route_after_supervisor(state: AgentState) -> Literal["rag_retriever", "contract_analyzer"]:
    if state.get("next") == "contract_analyzer":
        return "contract_analyzer"
    return "rag_retriever"


# ── Build Graph ────────────────────────────────────────────────────────────────
def build_agent_graph() -> StateGraph:
    workflow = StateGraph(AgentState)

    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("rag_retriever", rag_retriever_node)
    workflow.add_node("legal_advisor", legal_advisor_node)
    workflow.add_node("contract_analyzer", contract_analyzer_node)

    workflow.set_entry_point("supervisor")
    workflow.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        {"rag_retriever": "rag_retriever", "contract_analyzer": "contract_analyzer"},
    )
    workflow.add_edge("rag_retriever", "legal_advisor")
    workflow.add_edge("legal_advisor", END)
    workflow.add_edge("contract_analyzer", END)

    return workflow.compile()


agent = build_agent_graph()