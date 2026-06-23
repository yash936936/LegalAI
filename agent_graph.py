import os
import json
import re
import time
from typing import TypedDict, Annotated, List, Literal
from operator import add
from functools import wraps

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
    google_api_key=google_api_key,
    temperature=0.1,
    max_output_tokens=2048,
    max_retries=3
)

# Only use LLM grader when absolutely necessary - commented out to save API calls
# llm_grader = ChatGoogleGenerativeAI(
#     model="gemini-3.5-flash",
#     google_api_key=google_api_key,
#     temperature=0.0,
#     max_output_tokens=20,
#     max_retries=3
# )

# ── Helper: Token Estimation & Safe Invoke with Retry ─────────────────────────
def estimate_tokens(messages: List) -> int:
    """Estimates token count from message content (rough approximation)."""
    total_chars = sum(len(str(m.content)) for m in messages)
    return total_chars // 4

def retry_with_backoff(max_attempts=3, base_delay=10):
    """Decorator to retry API calls with exponential backoff."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    error_str = str(e)
                    # Handle both 429 (rate limit) and 503 (service unavailable)
                    if "429" in error_str or "503" in error_str or "RESOURCE_EXHAUSTED" in error_str or "UNAVAILABLE" in error_str:
                        if attempt < max_attempts - 1:
                            delay = base_delay * (2 ** attempt)
                            print(f"⏳ API rate limit hit. Retrying in {delay} seconds... (Attempt {attempt + 1}/{max_attempts})")
                            print(f"📊 Current usage: {api_rate_limiter.get_status()}")
                            time.sleep(delay)
                            continue
                        else:
                            raise Exception(
                                "API rate limit exceeded after retries. "
                                "Free tier limits: 5 RPM, 20 RPD, 250K TPM. "
                                "Please wait a few minutes or check usage at: "
                                "https://aistudio.google.com/app/rate-limit"
                            )
                    raise
            raise Exception("Max retry attempts exceeded")
        return wrapper
    return decorator

@retry_with_backoff(max_attempts=3, base_delay=10)
def safe_invoke(llm, messages: List, output_buffer: int = 1000):
    """Safely invoke LLM with rate limiting and retry logic."""
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

# ── Node: Supervisor (RULE-BASED, NO API CALL) ────────────────────────────────
def supervisor_node(state: AgentState):
    """
    Routes the user query using RULE-BASED logic (NO API CALL).
    This saves 1 API call per request!
    """
    last_msg = state["messages"][-1]["content"].lower()
    
    # Check if mode is explicitly set to contract
    if state.get("mode") == "contract":
        print("📋 Routing to Contract Analyzer (mode selected)")
        return {"next": "contract_analyzer", "raw_query": state["messages"][-1]["content"]}
    
    # Rule-based routing keywords
    contract_keywords = [
        "contract", "agreement", "clause", "terms and conditions", 
        "analyze this contract", "review contract", "legal document",
        "nda", "non-disclosure", "service agreement", "employment contract"
    ]
    
    # Check if query contains contract-related keywords
    for keyword in contract_keywords:
        if keyword in last_msg:
            print(f"📋 Routing to Contract Analyzer (keyword: '{keyword}')")
            return {"next": "contract_analyzer", "raw_query": state["messages"][-1]["content"]}
    
    # Default to legal advisor
    print("⚖️ Routing to Legal Advisor (default)")
    return {"next": "legal_advisor", "raw_query": state["messages"][-1]["content"]}

# ── Node: RAG Retriever ───────────────────────────────────────────────────────
def rag_retriever_node(state: AgentState):
    """Retrieves relevant documents using hybrid search."""
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

# ── Node: Legal Advisor ───────────────────────────────────────────────────────
def legal_advisor_node(state: AgentState):
    """Generates legal advice using RAG context or fallback mode."""
    query = state.get("raw_query", "")
    context = state.get("rag_context", "")
    tier = state.get("rag_tier", "fallback")

    # Choose system prompt based on retrieval tier
    if tier == "fallback" or "No relevant" in context:
        system_prompt = FALLBACK_SYSTEM
        user_content = query
        print("⚠️ Using FALLBACK mode (no RAG context)")
    else:
        system_prompt = LEGAL_ADVISOR_SYSTEM.format(context=context)
        user_content = query
        print("📚 Using RAG context for legal advice")

    # Build message history (only last 3 messages to save tokens)
    history = []
    recent_messages = state["messages"][-4:-1]  # Last 3 messages max
    for msg in recent_messages:
        if msg["role"] == "user":
            history.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            history.append(AIMessage(content=msg["content"]))

    messages = [SystemMessage(content=system_prompt)] + history + [HumanMessage(content=user_content)]

    try:
        print("🔄 Calling Gemini API for legal advice...")
        response = safe_invoke(llm_primary, messages, output_buffer=1500)
        answer = response.content

        # Add retrieval tier label
        tier_label = {
            "cache": "⚡ Semantic Cache",
            "hybrid": "🔍 Hybrid RAG (Dense + BM25 + RRF)",
            "fallback": "⚠️ Fallback Mode (No RAG context)"
        }.get(tier, tier)
        answer += f"\n---\n*Retrieval: {tier_label}*"
        
        print("✅ Legal advice generated successfully")
        print(f"📊 Rate limiter status: {api_rate_limiter.get_status()}")
    except RateLimitError:
        raise
    except Exception as e:
        answer = f"Legal advisor encountered an error: {str(e)}. Please retry."

    return {"messages": [{"role": "assistant", "content": answer}]}

# ── Node: Contract Analyzer ───────────────────────────────────────────────────
def contract_analyzer_node(state: AgentState):
    """Analyzes contract text and returns structured JSON risk assessment."""
    contract_text = state.get("raw_query", "")
    system_prompt = CONTRACT_ANALYZER_SYSTEM

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Analyze this contract:\n\n{contract_text}"),
    ]

    try:
        print("🔄 Calling Gemini API for contract analysis...")
        response = safe_invoke(llm_primary, messages, output_buffer=2000)
        raw = response.content.strip()
        
        # Clean up markdown code blocks if present
        raw = re.sub(r"```json|```", "", raw).strip()
        parsed = json.loads(raw)
        
        print("✅ Contract analysis completed")
        print(f"📊 Rate limiter status: {api_rate_limiter.get_status()}")
        
        return {
            "contract_result": parsed,
            "messages": [{"role": "assistant", "content": raw}]
        }
    except RateLimitError:
        raise
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
        return {
            "contract_result": json.loads(error_response),
            "messages": [{"role": "assistant", "content": error_response}]
        }
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
        return {
            "contract_result": json.loads(error_response),
            "messages": [{"role": "assistant", "content": error_response}]
        }

# ── Routing Function ──────────────────────────────────────────────────────────
def route_after_supervisor(state: AgentState) -> Literal["rag_retriever", "contract_analyzer"]:
    """Determines the next node based on supervisor's decision."""
    if state.get("next") == "contract_analyzer":
        return "contract_analyzer"
    return "rag_retriever"

# ── Build Graph ───────────────────────────────────────────────────────────────
def build_agent_graph() -> StateGraph:
    """Constructs and compiles the multi-agent workflow graph."""
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("rag_retriever", rag_retriever_node)
    workflow.add_node("legal_advisor", legal_advisor_node)
    workflow.add_node("contract_analyzer", contract_analyzer_node)

    # Set entry point
    workflow.set_entry_point("supervisor")
    
    # Add conditional routing from supervisor
    workflow.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        {
            "rag_retriever": "rag_retriever",
            "contract_analyzer": "contract_analyzer",
        },
    )
    
    # Add edges to END
    workflow.add_edge("rag_retriever", "legal_advisor")
    workflow.add_edge("legal_advisor", END)
    workflow.add_edge("contract_analyzer", END)

    return workflow.compile()

# Initialize the agent graph
agent = build_agent_graph()