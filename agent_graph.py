# agent_graph.py
import os
import json
import re
from typing import TypedDict, Annotated, List, Literal
from operator import add

from langgraph.graph import StateGraph, END
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from prompts import (
    SUPERVISOR_SYSTEM,
    LEGAL_ADVISOR_SYSTEM,
    CONTRACT_ANALYZER_SYSTEM,
    FALLBACK_SYSTEM,
)
from rag_vectorstore import retriever

# ── LLM Clients ──────────────────────────────────────────────────────────────
# Primary: Claude Sonnet for legal reasoning (high precision)
llm_primary = ChatAnthropic(
    model="claude-sonnet-4-6",
    temperature=0.1,
    max_tokens=2048,
)

# Grader: cheaper model for supervisor routing
llm_grader = ChatAnthropic(
    model="claude-haiku-4-5-20251001",
    temperature=0.0,
    max_tokens=20,
)


# ── Agent State ───────────────────────────────────────────────────────────────
class AgentState(TypedDict):
    messages: Annotated[List[dict], add]   # conversation history
    mode: str                               # "advisor" | "contract"
    next: str                               # routing target
    rag_context: str                        # retrieved context
    rag_tier: str                           # cache | hybrid | fallback
    raw_query: str                          # original user query
    contract_result: dict                   # parsed JSON for contract mode


# ── Node: Supervisor ──────────────────────────────────────────────────────────
def supervisor_node(state: AgentState) -> AgentState:
    """
    Classifies intent and routes to:
    - legal_advisor  (RAG-powered Q&A)
    - contract_analyzer (structured risk JSON)
    """
    last_msg = state["messages"][-1]["content"]
    state["raw_query"] = last_msg

    # If mode is explicitly set by UI, trust it
    if state.get("mode") == "contract":
        state["next"] = "contract_analyzer"
        return state

    # Otherwise use LLM supervisor for intent classification
    prompt = SUPERVISOR_SYSTEM.format(message=last_msg)
    try:
        response = llm_grader.invoke([HumanMessage(content=prompt)])
        route = response.content.strip().lower()
        # Validate
        if "contract" in route:
            state["next"] = "contract_analyzer"
        else:
            state["next"] = "legal_advisor"
    except Exception:
        state["next"] = "legal_advisor"

    return state


# ── Node: RAG Retriever ───────────────────────────────────────────────────────
def rag_retriever_node(state: AgentState) -> AgentState:
    """
    Hybrid RAG retrieval (Tier 1→4 waterfall).
    Populates state with context and tier label.
    """
    query = state.get("raw_query", "")
    try:
        docs, tier = retriever.retrieve(query, top_k=5)
        context = retriever.format_context(docs)
    except Exception as e:
        context = "Retrieval error — operating in fallback mode."
        tier = "fallback"

    state["rag_context"] = context
    state["rag_tier"] = tier
    return state


# ── Node: Legal Advisor ───────────────────────────────────────────────────────
def legal_advisor_node(state: AgentState) -> AgentState:
    """
    Generates structured legal advice using retrieved RAG context.
    Falls back to general knowledge if retrieval was empty.
    """
    query = state.get("raw_query", "")
    context = state.get("rag_context", "")
    tier = state.get("rag_tier", "fallback")

    # Select appropriate system prompt
    if tier == "fallback" or "No relevant" in context:
        system_prompt = FALLBACK_SYSTEM
        user_content = query
    else:
        system_prompt = LEGAL_ADVISOR_SYSTEM.format(context=context)
        user_content = query

    # Build conversation history for multi-turn context
    history = []
    for msg in state["messages"][:-1]:  # All except current
        if msg["role"] == "user":
            history.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            history.append(AIMessage(content=msg["content"]))

    messages = [SystemMessage(content=system_prompt)] + history + [HumanMessage(content=user_content)]

    try:
        response = llm_primary.invoke(messages)
        answer = response.content

        # Append retrieval tier info as a footnote
        tier_label = {"cache": "⚡ Semantic Cache", "hybrid": "🔍 Hybrid RAG (Dense + BM25 + RRF)", "fallback": "⚠️ Fallback Mode (No RAG context)"}.get(tier, tier)
        answer += f"\n\n---\n*Retrieval: {tier_label}*"

    except Exception as e:
        answer = f"Legal advisor encountered an error: {str(e)}. Please retry."

    state["messages"] = state["messages"] + [{"role": "assistant", "content": answer}]
    return state


# ── Node: Contract Analyzer ───────────────────────────────────────────────────
def contract_analyzer_node(state: AgentState) -> AgentState:
    """
    Analyzes contract text and returns structured JSON risk report.
    """
    contract_text = state.get("raw_query", "")
    system_prompt = CONTRACT_ANALYZER_SYSTEM

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Analyze this contract:\n\n{contract_text}"),
    ]

    try:
        response = llm_primary.invoke(messages)
        raw = response.content.strip()

        # Strip markdown fences if present
        raw = re.sub(r"```json|```", "", raw).strip()

        # Validate JSON
        parsed = json.loads(raw)
        state["contract_result"] = parsed
        state["messages"] = state["messages"] + [{"role": "assistant", "content": raw}]

    except json.JSONDecodeError as e:
        error_response = json.dumps({
            "overall_risk_score": 0,
            "risk_level": "ERROR",
            "summary": f"Failed to parse contract analysis. JSON error: {str(e)}",
            "issues": [],
            "positive_clauses": [],
            "missing_clauses": [],
            "recommendations": ["Re-paste the contract text and retry."],
        })
        state["contract_result"] = json.loads(error_response)
        state["messages"] = state["messages"] + [{"role": "assistant", "content": error_response}]

    except Exception as e:
        error_response = json.dumps({
            "overall_risk_score": 0,
            "risk_level": "ERROR",
            "summary": f"Agent error: {str(e)}",
            "issues": [],
            "positive_clauses": [],
            "missing_clauses": [],
            "recommendations": ["Check API connectivity and retry."],
        })
        state["contract_result"] = json.loads(error_response)
        state["messages"] = state["messages"] + [{"role": "assistant", "content": error_response}]

    return state


# ── Routing Function ──────────────────────────────────────────────────────────
def route_after_supervisor(state: AgentState) -> Literal["rag_retriever", "contract_analyzer"]:
    if state.get("next") == "contract_analyzer":
        return "contract_analyzer"
    return "rag_retriever"


# ── Build Graph ───────────────────────────────────────────────────────────────
def build_agent_graph() -> StateGraph:
    workflow = StateGraph(AgentState)

    # Register nodes
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("rag_retriever", rag_retriever_node)
    workflow.add_node("legal_advisor", legal_advisor_node)
    workflow.add_node("contract_analyzer", contract_analyzer_node)

    # Entry point
    workflow.set_entry_point("supervisor")

    # Conditional routing from supervisor
    workflow.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        {
            "rag_retriever": "rag_retriever",
            "contract_analyzer": "contract_analyzer",
        },
    )

    # RAG → Legal Advisor (always)
    workflow.add_edge("rag_retriever", "legal_advisor")

    # Terminal nodes
    workflow.add_edge("legal_advisor", END)
    workflow.add_edge("contract_analyzer", END)

    return workflow.compile()


# Compiled agent (singleton — import this in app.py)
agent = build_agent_graph()
