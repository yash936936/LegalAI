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
from theme import inject_css
from icons import icon, avatar_svg, favicon_svg, write_asset

init_db()

# ── Theme state (must exist before page_config/CSS) ──────────────────────────
if "theme" not in st.session_state:
    st.session_state.theme = "light"

# ── Static assets (favicon + chat avatars), generated once per run ──────────
_ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
_FAVICON_PATH = write_asset(favicon_svg(bg="#cc785c", fg="#ffffff"), os.path.join(_ASSET_DIR, "favicon.svg"))
_AVATAR_USER_PATH = write_asset(avatar_svg("user", bg="#252523", fg="#faf9f5"), os.path.join(_ASSET_DIR, "avatar_user.svg"))
_AVATAR_AGENT_PATH = write_asset(avatar_svg("scale", bg="#cc785c", fg="#ffffff"), os.path.join(_ASSET_DIR, "avatar_agent.svg"))

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Legal AI",
    page_icon=_FAVICON_PATH,
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Theme CSS ─────────────────────────────────────────────────────────────────
st.markdown(inject_css(st.session_state.theme), unsafe_allow_html=True)
st.markdown("""
<style>
.risk-critical { background: rgba(198,69,69,0.08); border-left: 3px solid var(--critical); padding: 10px 14px; border-radius: 6px; }
.risk-high { background: rgba(232,165,90,0.10); border-left: 3px solid var(--accent-amber); padding: 10px 14px; border-radius: 6px; }
.risk-medium { background: rgba(93,184,166,0.10); border-left: 3px solid var(--accent-teal); padding: 10px 14px; border-radius: 6px; }
.risk-low { background: rgba(93,184,114,0.10); border-left: 3px solid var(--success); padding: 10px 14px; border-radius: 6px; }
.chat-meta { font-size: 0.72rem; color: var(--stone); margin-top: 2px; }
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
    st.markdown(
        f"""
        <div class="lai-brand" style="margin-bottom:4px;">
          <div class="lai-brand-mark">{icon('scale', size=18, color='#ffffff')}</div>
          <div>
            <div class="lai-brand-name" style="font-size:18px;">Legal AI</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("Hybrid RAG for Indian law")

    st.markdown('<div class="lai-theme-toggle">', unsafe_allow_html=True)
    theme_choice = st.radio(
        "Appearance", ["Light", "Dark"],
        index=0 if st.session_state.theme == "light" else 1,
        horizontal=True, label_visibility="collapsed",
    )
    st.markdown('</div>', unsafe_allow_html=True)
    new_theme = theme_choice.lower()
    if new_theme != st.session_state.theme:
        st.session_state.theme = new_theme
        st.rerun()

    st.divider()

    if st.button("New Conversation", use_container_width=True, type="primary"):
        new_tid = create_thread("New Legal Query", st.session_state.mode)
        st.session_state.current_thread = new_tid
        st.session_state.messages = []
        st.session_state.last_eval = None
        st.rerun()

    st.divider()
    st.markdown('<p class="lai-caption">PAST CONVERSATIONS</p>', unsafe_allow_html=True)
    threads = get_all_threads()

    if not threads:
        st.caption("No conversations yet.")
    else:
        for tid, title, tmode, ts in threads:
            is_active = tid == st.session_state.current_thread
            count = get_thread_message_count(tid)
            col1, col2 = st.columns([5, 1])
            with col1:
                label = f"{title[:28]}{'...' if len(title) > 28 else ''}"
                btn_type = "primary" if is_active else "secondary"
                st.markdown('<div class="lai-thread-row">', unsafe_allow_html=True)
                if st.button(label, key=f"thread_{tid}", use_container_width=True, type=btn_type):
                    st.session_state.current_thread = tid
                    st.session_state.messages = load_thread(tid)
                    st.session_state.last_eval = None
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)
            with col2:
                st.markdown('<div class="lai-icon-btn">', unsafe_allow_html=True)
                if st.button("×", key=f"del_{tid}", help="Delete thread"):
                    delete_thread(tid)
                    if tid == st.session_state.current_thread:
                        new_tid = create_thread("New Legal Query", st.session_state.mode)
                        st.session_state.current_thread = new_tid
                        st.session_state.messages = []
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

    st.divider()
    if st.session_state.messages:
        md_export = export_thread_as_markdown(st.session_state.current_thread)
        st.download_button(
            f"Export Thread",
            data=md_export,
            file_name=f"legal_thread_{st.session_state.current_thread}.md",
            mime="text/markdown",
            use_container_width=True,
        )

    st.divider()
    st.markdown('<p class="lai-caption">SETTINGS</p>', unsafe_allow_html=True)
    st.session_state.show_eval = st.toggle("Show RAG quality scores", value=st.session_state.show_eval)
    st.caption("Uses LLM-as-Judge")

# ── Main Header ───────────────────────────────────────────────────────────────
col_title, col_mode = st.columns([3, 2])
with col_title:
    st.markdown(
        f"""
        <div class="lai-brand">
          <div class="lai-brand-mark">{icon('scale', size=20, color='#ffffff')}</div>
          <div>
            <div class="lai-brand-name">Legal AI</div>
            <div class="lai-brand-sub">AI-assisted guidance on Indian law</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with col_mode:
    mode_display = st.radio(
        "Mode",
        ["Legal Advisor", "Contract Analyzer"],
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
    badge_class = {
        "CRITICAL": "critical", "HIGH": "high", "MEDIUM": "medium", "LOW": "low",
    }.get(level, "medium")

    safe_summary = html.escape(data.get("summary", ""))
    st.markdown(f"""
    <div class="{risk_class}">
    <span class="lai-badge {badge_class}">{html.escape(str(level))} · {score}/10</span><br/><br/>
    {safe_summary}
    </div>
    """, unsafe_allow_html=True)

    issues = data.get("issues", [])
    if issues:
        st.markdown(f"### Red Flag Clauses ({len(issues)})")
        for issue in issues:
            risk_score = issue.get("risk_score", 0)
            flag = html.escape(str(issue.get("flag", "Unknown")))
            clause_type = html.escape(str(issue.get("clause_type", "")))
            with st.expander(f"{flag} — Risk {risk_score}/10 ({clause_type})"):
                excerpt = issue.get("excerpt", "N/A")
                st.markdown(f"**Excerpt:** *\"{excerpt}\"*")  # plain markdown, not unsafe_allow_html
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**Business Impact**")
                    st.info(issue.get("impact", "N/A"))
                with col2:
                    st.markdown("**Suggested Revision**")
                    st.success(issue.get("suggested_revision", "N/A"))

    positives = data.get("positive_clauses", [])
    if positives:
        st.markdown("### Protective Clauses")
        for p in positives:
            st.markdown(f"- {p}")

    col_miss, col_rec = st.columns(2)
    missing = data.get("missing_clauses", [])
    recs = data.get("recommendations", [])
    with col_miss:
        if missing:
            st.markdown("### Missing Clauses")
            for m in missing:
                st.warning(m)
    with col_rec:
        if recs:
            st.markdown("### Action Items")
            for r_i, r in enumerate(recs, 1):
                st.markdown(f"{r_i}. {r}")


# ── Chat Display ──────────────────────────────────────────────────────────────
for i, msg in enumerate(st.session_state.messages):
    avatar = _AVATAR_USER_PATH if msg["role"] == "user" else _AVATAR_AGENT_PATH
    with st.chat_message(msg["role"], avatar=avatar):
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
    with st.expander("RAG Quality Evaluation (LLM-as-Judge)", expanded=False):
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
    with st.chat_message("user", avatar=_AVATAR_USER_PATH):
        st.markdown(prompt)
    save_message(st.session_state.current_thread, "user", prompt)

    with st.spinner("Reasoning over Indian law sources..."):
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

            with st.chat_message("assistant", avatar=_AVATAR_AGENT_PATH):
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
st.caption("AI-generated legal information only — not a substitute for professional legal advice from a licensed advocate.")
