# app.py
# ── ChromaDB SQLite compatibility fix (must be FIRST import) ─────────────────
# On Linux/Docker, system SQLite is often < 3.35 which ChromaDB requires.
# pysqlite3-binary ships a newer version; this monkeypatch makes Python use it.
import sys
try:
    import pysqlite3
    sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
except ImportError:
    pass  # Local dev with up-to-date SQLite — no patch needed

# FIX: load_dotenv() MUST run before agent_graph (-> rag_vectorstore) is
# imported below. rag_vectorstore.py reads GOOGLE_API_KEY at import time to
# build the embeddings client, so .env has to already be loaded by then —
# previously load_dotenv() was called further down, after the import, so the
# key was always None unless it happened to already be a real OS env var.
import os
from dotenv import load_dotenv
load_dotenv()

import streamlit as st
import json
import html

from agent_graph import agent, AgentState
from utils import (
    init_db, create_thread, save_message, load_thread,
    get_all_threads, delete_thread, update_thread_title,
    get_thread_message_count, export_thread_as_markdown,
)
from evaluator import evaluate_rag, format_eval_for_display

init_db()

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Legal AI Agent",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.stApp { background: #0f1117; }
.block-container { padding-top: 1.5rem; }
.chat-meta { font-size: 0.72rem; color: #666; margin-top: 2px; }
.risk-critical { background: #3d1515; border-left: 3px solid #e05555; padding: 8px 12px; border-radius: 4px; }
.risk-high { background: #2d2010; border-left: 3px solid #d4860a; padding: 8px 12px; border-radius: 4px; }
.risk-medium { background: #0f1d2d; border-left: 3px solid #2c7be5; padding: 8px 12px; border-radius: 4px; }
.risk-low { background: #0d1f13; border-left: 3px solid #2ea44f; padding: 8px 12px; border-radius: 4px; }
div[data-testid="stSidebarContent"] { padding-top: 1rem; }
</style>
""", unsafe_allow_html=True)

# ── Session State Init ────────────────────────────────────────────────────────
if "mode" not in st.session_state:
    st.session_state.mode = "advisor"
if "current_thread" not in st.session_state:
    st.session_state.current_thread = create_thread("New Legal Query", "advisor")
if "messages" not in st.session_state:
    st.session_state.messages = []
if "show_eval" not in st.session_state:
    st.session_state.show_eval = False
if "last_eval" not in st.session_state:
    st.session_state.last_eval = None
if "last_rag_context" not in st.session_state:
    st.session_state.last_rag_context = ""

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚖️ Legal AI Agent")
    st.caption("LangGraph · Hybrid RAG · SQLite · LLM-as-Judge · Gemini Free Tier")
    st.divider()

    if st.button("➕ New Conversation", use_container_width=True, type="primary"):
        new_tid = create_thread("New Legal Query", st.session_state.mode)
        st.session_state.current_thread = new_tid
        st.session_state.messages = []
        st.session_state.last_eval = None
        st.rerun()

    st.divider()
    st.markdown("**Past Conversations**")
    threads = get_all_threads()

    if not threads:
        st.caption("No conversations yet.")
    else:
        for tid, title, tmode, ts in threads:
            is_active = tid == st.session_state.current_thread
            icon = "⚖️" if tmode == "advisor" else "📄"
            count = get_thread_message_count(tid)
            col1, col2 = st.columns([5, 1])
            with col1:
                label = f"{icon} {title[:28]}{'...' if len(title) > 28 else ''}"
                btn_type = "primary" if is_active else "secondary"
                if st.button(label, key=f"thread_{tid}", use_container_width=True, type=btn_type):
                    st.session_state.current_thread = tid
                    st.session_state.messages = load_thread(tid)
                    st.session_state.last_eval = None
                    st.rerun()
            with col2:
                if st.button("🗑", key=f"del_{tid}", help="Delete thread"):
                    delete_thread(tid)
                    if tid == st.session_state.current_thread:
                        new_tid = create_thread("New Legal Query", st.session_state.mode)
                        st.session_state.current_thread = new_tid
                        st.session_state.messages = []
                    st.rerun()

    st.divider()
    if st.session_state.messages:
        md_export = export_thread_as_markdown(st.session_state.current_thread)
        st.download_button(
            "📥 Export Thread (Markdown)",
            data=md_export,
            file_name=f"legal_thread_{st.session_state.current_thread}.md",
            mime="text/markdown",
            use_container_width=True,
        )

    st.divider()
    st.markdown("**Settings**")
    st.session_state.show_eval = st.toggle("Show RAG Quality Scores", value=st.session_state.show_eval)
    st.caption("Uses LLM-as-Judge (gemini-2.5-flash-lite)")

# ── Main Header ───────────────────────────────────────────────────────────────
col_title, col_mode = st.columns([3, 2])
with col_title:
    st.markdown("# ⚖️ Legal AI Agent")
    st.caption("Powered by LangGraph · Hybrid RAG (BM25 + ChromaDB + RRF) · Indian Law · Gemini Free Tier")
with col_mode:
    mode_display = st.radio(
        "Mode",
        ["⚖️ Legal Advisor", "📄 Contract Analyzer"],
        horizontal=True,
        label_visibility="collapsed",
    )
    new_mode = "advisor" if "Advisor" in mode_display else "contract"
    if new_mode != st.session_state.mode:
        st.session_state.mode = new_mode

st.divider()


# ── Helper: Contract Report Renderer ─────────────────────────────────────────
def _render_contract_report(data: dict):
    """
    Renders a structured contract analysis as rich Streamlit components.
    FIX: model-generated text is HTML-escaped before being interpolated into
    raw unsafe_allow_html blocks — the original code rendered the LLM's
    output (which echoes user-pasted contract text) directly as HTML, which
    is an injection risk if a pasted "contract" contains markup/script.
    """
    score = data.get("overall_risk_score", 0)
    level = data.get("risk_level", "UNKNOWN")
    risk_class = {
        "CRITICAL": "risk-critical",
        "HIGH": "risk-high",
        "MEDIUM": "risk-medium",
        "LOW": "risk-low",
    }.get(level, "risk-medium")

    safe_summary = html.escape(data.get("summary", ""))
    st.markdown(f"""
    <div class="{risk_class}">
    <strong>Overall Risk: {score}/10 — {html.escape(str(level))}</strong><br/>
    {safe_summary}
    </div>
    """, unsafe_allow_html=True)

    issues = data.get("issues", [])
    if issues:
        st.markdown(f"### 🚩 Red Flag Clauses ({len(issues)})")
        for issue in issues:
            risk_score = issue.get("risk_score", 0)
            flag = html.escape(str(issue.get("flag", "Unknown")))
            clause_type = html.escape(str(issue.get("clause_type", "")))
            with st.expander(f"**{flag}** — Risk {risk_score}/10 ({clause_type})"):
                excerpt = issue.get("excerpt", "N/A")
                st.markdown(f"**📋 Excerpt:** *\"{excerpt}\"*")  # plain markdown, not unsafe_allow_html
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**⚠️ Business Impact**")
                    st.info(issue.get("impact", "N/A"))
                with col2:
                    st.markdown("**✅ Suggested Revision**")
                    st.success(issue.get("suggested_revision", "N/A"))

    positives = data.get("positive_clauses", [])
    if positives:
        st.markdown("### ✅ Protective Clauses")
        for p in positives:
            st.markdown(f"- {p}")

    col_miss, col_rec = st.columns(2)
    missing = data.get("missing_clauses", [])
    recs = data.get("recommendations", [])
    with col_miss:
        if missing:
            st.markdown("### ⚠️ Missing Clauses")
            for m in missing:
                st.warning(m)
    with col_rec:
        if recs:
            st.markdown("### 📋 Action Items")
            for r_i, r in enumerate(recs, 1):
                st.markdown(f"{r_i}. {r}")


# ── Chat Display ──────────────────────────────────────────────────────────────
for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"], avatar="👤" if msg["role"] == "user" else "⚖️"):
        if msg["role"] == "assistant" and st.session_state.mode == "contract":
            try:
                content = msg["content"]
                clean = content.replace("```json", "").replace("```", "").strip()
                data = json.loads(clean)
                _render_contract_report(data)
            except Exception:
                st.markdown(msg["content"])
        else:
            st.markdown(msg["content"])

# ── RAG Eval Display ──────────────────────────────────────────────────────────
if st.session_state.show_eval and st.session_state.last_eval:
    with st.expander("🔍 RAG Quality Evaluation (LLM-as-Judge)", expanded=False):
        st.markdown(format_eval_for_display(st.session_state.last_eval))

# ── Chat Input ────────────────────────────────────────────────────────────────
placeholder = (
    "Ask a legal question (e.g. 'What are my rights if arrested without warrant?')"
    if st.session_state.mode == "advisor"
    else "Paste contract text here for risk analysis..."
)

if prompt := st.chat_input(placeholder):
    if not st.session_state.messages:
        title = prompt[:50] + ("..." if len(prompt) > 50 else "")
        update_thread_title(st.session_state.current_thread, title)

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)
    save_message(st.session_state.current_thread, "user", prompt)

    with st.spinner("⚡ Agentic RAG reasoning..."):
        try:
            # FIX: previously this always sent messages=[{"role":"user","content":prompt}]
            # — i.e. ONLY the current message, no prior turns. legal_advisor_node's
            # "last 3 messages" history slice was therefore always slicing an empty
            # list. We now pass the last few turns from session history so follow-up
            # questions actually have conversational context.
            history_window = st.session_state.messages[-7:-1]  # up to 3 prior exchanges

            input_state = AgentState(
                messages=history_window + [{"role": "user", "content": prompt}],
                mode=st.session_state.mode,
                next="",
                rag_context="",
                rag_tier="",
                raw_query=prompt,
                contract_result={},
            )
            result = agent.invoke(input_state)
            assistant_content = result["messages"][-1]["content"]
            rag_context = result.get("rag_context", "")
            rag_tier = result.get("rag_tier", "")
            st.session_state.last_rag_context = rag_context

            with st.chat_message("assistant", avatar="⚖️"):
                if st.session_state.mode == "contract":
                    try:
                        clean = assistant_content.replace("```json", "").replace("```", "").strip()
                        data = json.loads(clean)
                        _render_contract_report(data)
                    except Exception:
                        st.markdown(assistant_content)
                else:
                    st.markdown(assistant_content)

            st.session_state.messages.append({"role": "assistant", "content": assistant_content})
            save_message(st.session_state.current_thread, "assistant", assistant_content)

            if st.session_state.show_eval and st.session_state.mode == "advisor":
                eval_result = evaluate_rag(
                    question=prompt,
                    context=rag_context or "No context retrieved",
                    answer=assistant_content,
                )
                st.session_state.last_eval = eval_result

        except Exception as e:
            st.error(f"Agent error: {str(e)}")
            st.caption("Check your GOOGLE_API_KEY in .env and retry.")

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption("⚠️ AI-generated legal information only — not a substitute for professional legal advice from a licensed advocate.")