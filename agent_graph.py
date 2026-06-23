import os
import json
import re
from typing import TypedDict, Annotated, List, Literal
from operator import add

from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from prompts import (
    SUPERVISOR_SYSTEM,
    LEGAL_ADVISOR_SYSTEM,
    CONTRACT_ANALYZER_SYSTEM,
    FALLBACK_SYSTEM,
)
from rag_vectorstore import retriever
from rate_limiter import api_rate_limiter, RateLimitError

google_api_key = os.getenv("GOOGLE_API_KEY")

# ── LLM Clients ──────────────────────────────────────────────────────────────
llm_primary = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash",
    temperature=0.1,
    max_output_tokens=2048,
    max_retries=3  
)

llm_grader = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash",
    temperature=0.0,
    max_output_tokens=20,
    max_retries=3
)

# ── Helper: Token Estimation & Safe Invoke ────────────────────────────────────
def estimate_tokens(messages: List) -> int:
    """Rough token estimate: 1 token ≈ 4 characters for English/Latin text."""
    total_chars = sum(len(str(m.content)) for m in messages)
    return total_chars // 4

def safe_invoke(llm, messages: List, output_buffer: int = 1000):
    """Rate-limit check -> Invoke -> Return response"""
    input_tokens = estimate_tokens(messages)
    api_rate_limiter.acquire(input_tokens, output_buffer)
    return llm.invoke(messages)

# ── Agent State ───────────────────────────────────────────────────────────────
class AgentState(TypedDict):
    messages: Annotated[List[dict], add]
    mode: str
    next: str
    rag_context: str
    rag_tier: str
    raw_query: str
    contract_result: dict

# ── Node: Supervisor ──────────────────────────────────────────────────────────
def supervisor_node(state: AgentState):
    last_msg = state["messages"][-1]["content"]
    
    if state.get("mode") == "contract":
        return {"next": "contract_analyzer", "raw_query": last_msg}

    prompt = SUPERVISOR_SYSTEM.format(message=last_msg)
    messages = [HumanMessage(content=prompt)]
    
    try:
        response = safe_invoke(llm_grader, messages, output_buffer=50)
        route = response.content.strip().lower()
        if "contract" in route:
            return {"next": "contract_analyzer", "raw_query": last_msg}
        return {"next": "legal_advisor", "raw_query": last_msg}
    except RateLimitError:
        raise
    except Exception:
        return {"next": "legal_advisor", "raw_query": last_msg}

# ── Node: RAG Retriever ───────────────────────────────────────────────────────
def rag_retriever_node(state: AgentState):
    query = state.get("raw_query", "")
    try:
        docs, tier = retriever.retrieve(query, top_k=5)
        context = retriever.format_context(docs)
    except Exception as e:
        context = "Retrieval error — operating in fallback mode."
        tier = "fallback"

    return {"rag_context": context, "rag_tier": tier}

# ── Node: Legal Advisor ───────────────────────────────────────────────────────
def legal_advisor_node(state: AgentState):
    query = state.get("raw_query", "")
    context = state.get("rag_context", "")
    tier = state.get("rag_tier", "fallback")

    if tier == "fallback" or "No relevant" in context:
        system_prompt = FALLBACK_SYSTEM
        user_content = query
    else:
        system_prompt = LEGAL_ADVISOR_SYSTEM.format(context=context)
        user_content = query

    history = []
    for msg in state["messages"][:-1]:
        if msg["role"] == "user":
            history.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            history.append(AIMessage(content=msg["content"]))

    messages = [SystemMessage(content=system_prompt)] + history + [HumanMessage(content=user_content)]

    try:
        response = safe_invoke(llm_primary, messages, output_buffer=1500)
        answer = response.content

        tier_label = {
            "cache": "⚡ Semantic Cache", 
            "hybrid": "🔍 Hybrid RAG (Dense + BM25 + RRF)", 
            "fallback": "⚠️ Fallback Mode (No RAG context)"
        }.get(tier, tier)
        answer += f"\n\n---\n*Retrieval: {tier_label}*"
    except RateLimitError:
        raise
    except Exception as e:
        answer = f"Legal advisor encountered an error: {str(e)}. Please retry."

    return {"messages": [{"role": "assistant", "content": answer}]}

# ── Node: Contract Analyzer ───────────────────────────────────────────────────
def contract_analyzer_node(state: AgentState):
    contract_text = state.get("raw_query", "")
    system_prompt = CONTRACT_ANALYZER_SYSTEM

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Analyze this contract:\n\n{contract_text}"),
    ]

    try:
        response = safe_invoke(llm_primary, messages, output_buffer=2000)
        raw = response.content.strip()
        raw = re.sub(r"```json|```", "", raw).strip()
        parsed = json.loads(raw)
        return {
            "contract_result": parsed,
            "messages": [{"role": "assistant", "content": raw}]
        }
    except RateLimitError:
        raise
    except json.JSONDecodeError as e:
        error_response = json.dumps({
            "overall_risk_score": 0, "risk_level": "ERROR",
            "summary": f"Failed to parse contract analysis. JSON error: {str(e)}",
            "issues": [], "positive_clauses": [], "missing_clauses": [],
            "recommendations": ["Re-paste the contract text and retry."],
        })
        return {
            "contract_result": json.loads(error_response),
            "messages": [{"role": "assistant", "content": error_response}]
        }
    except Exception as e:
        error_response = json.dumps({
            "overall_risk_score": 0, "risk_level": "ERROR",
            "summary": f"Agent error: {str(e)}",
            "issues": [], "positive_clauses": [], "missing_clauses": [],
            "recommendations": ["Check API connectivity and retry."],
        })
        return {
            "contract_result": json.loads(error_response),
            "messages": [{"role": "assistant", "content": error_response}]
        }

# ── Routing Function ──────────────────────────────────────────────────────────
def route_after_supervisor(state: AgentState) -> Literal["rag_retriever", "contract_analyzer"]:
    if state.get("next") == "contract_analyzer":
        return "contract_analyzer"
    return "rag_retriever"

# ── Build Graph ───────────────────────────────────────────────────────────────
def build_agent_graph() -> StateGraph:
    workflow = StateGraph(AgentState)
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("rag_retriever", rag_retriever_node)
    workflow.add_node("legal_advisor", legal_advisor_node)
    workflow.add_node("contract_analyzer", contract_analyzer_node)

    workflow.set_entry_point("supervisor")
    workflow.add_conditional_edges(
        "supervisor", route_after_supervisor,
        {"rag_retriever": "rag_retriever", "contract_analyzer": "contract_analyzer"},
    )
    workflow.add_edge("rag_retriever", "legal_advisor")
    workflow.add_edge("legal_advisor", END)
    workflow.add_edge("contract_analyzer", END)

    return workflow.compile()

agent = build_agent_graph()