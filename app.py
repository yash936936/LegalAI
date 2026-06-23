# app.py
import json
import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from agent_graph import agent, AgentState
from evaluator import evaluate_rag, format_eval_for_display
from icons import avatar_svg, favicon_svg, icon, write_asset
from theme import inject_css, tokens
from utils import (
    init_db, create_thread, save_message, load_thread,
    get_all_threads, delete_thread, update_thread_title,
    get_thread_message_count, export_thread_as_markdown,
)

init_db()

ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

# ── Session State Init (theme decided before assets are built, so the
#    right colors get baked into the avatar/favicon SVGs below) ──────────────
if "theme" not in st.session_state:
    st.session_state.theme = "light"
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

T = tokens(st.session_state.theme)

FAVICON_PATH = write_asset(favicon_svg(bg=T["primary"], fg="#ffffff"), os.path.join(ASSET_DIR, "favicon.svg"))
USER_AVATAR = write_asset(avatar_svg("user", bg=T["steel"], fg="#ffffff"), os.path.join(ASSET_DIR, "avatar-user.svg"))
ADVISOR_AVATAR = write_asset(avatar_svg("scale", bg=T["primary"], fg="#ffffff"), os.path.join(ASSET_DIR, "avatar-advisor.svg"))
CONTRACT_AVATAR = write_asset(avatar_svg("document", bg=T["primary"], fg="#ffffff"), os.path.join(ASSET_DIR, "avatar-contract.svg"))

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Legal AI",
    page_icon=FAVICON_PATH,
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(inject_css(st.session_state.theme), unsafe_allow_html=True)

RISK_TOKEN = {
    "CRITICAL": ("critical", T["critical"]),
    "HIGH": ("high", T["attention"]),
    "MEDIUM": ("medium", T["primary"]),
    "LOW": ("low", T["success"]),
}

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        f"""
        <div class="lai-brand">
          <div class="lai-brand-mark">{icon('scale', 18, color='#ffffff')}</div>
          <div>
            <div class="lai-brand-name">Legal AI</div>
            <div class="lai-brand-sub">Hybrid RAG &middot; Indian Law</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

    if st.button("New conversation", use_container_width=True, type="primary"):
        new_tid = create_thread("New Legal Query", st.session_state.mode)
        st.session_state.current_thread = new_tid
        st.session_state.messages = []
        st.session_state.last_eval = None
        st.rerun()

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    st.markdown("<span class='lai-caption-bold'>PAST CONVERSATIONS</span>", unsafe_allow_html=True)
    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

    threads = get_all_threads()
    if not threads:
        st.markdown("<span class='lai-caption'>No conversations yet.</span>", unsafe_allow_html=True)
    else:
        for tid, title, tmode, ts in threads:
            is_active = tid == st.session_state.current_thread
            count = get_thread_message_count(tid)
            label = f"{title[:26]}{'…' if len(title) > 26 else ''}"
            col1, col2 = st.columns([5, 1])
            with col1:
                st.markdown("<div class='lai-thread-row'>", unsafe_allow_html=True)
                btn_type = "primary" if is_active else "secondary"
                if st.button(label, key=f"thread_{tid}", use_container_width=True, type=btn_type):
                    st.session_state.current_thread = tid
                    st.session_state.messages = load_thread(tid)
                    st.session_state.last_eval = None
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)
            with col2:
                st.markdown("<div class='lai-icon-btn'>", unsafe_allow_html=True)
                if st.button("✕", key=f"del_{tid}", help="Delete thread"):
                    delete_thread(tid)
                    if tid == st.session_state.current_thread:
                        new_tid = create_thread("New Legal Query", st.session_state.mode)
                        st.session_state.current_thread = new_tid
                        st.session_state.messages = []
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

    st.divider()

    if st.session_state.messages:
        md_export = export_thread_as_markdown(st.session_state.current_thread)
        st.download_button(
            "Export thread (.md)",
            data=md_export,
            file_name=f"legal_thread_{st.session_state.current_thread}.md",
            mime="text/markdown",
            use_container_width=True,
        )
        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    st.markdown("<span class='lai-caption-bold'>SETTINGS</span>", unsafe_allow_html=True)
    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

    theme_label = st.selectbox(
        "Appearance",
        options=["Light", "Dark"],
        index=0 if st.session_state.theme == "light" else 1,
        key="theme_select",
        label_visibility="visible",
    )
    new_theme = theme_label.lower()
    if new_theme != st.session_state.theme:
        st.session_state.theme = new_theme
        st.rerun()

    st.session_state.show_eval = st.toggle(
        "Show RAG quality scores", value=st.session_state.show_eval
    )
    st.markdown(
        "<span class='lai-caption'>Uses LLM-as-Judge (gemini-3.5-flash)</span>",
        unsafe_allow_html=True,
    )

# ── Main Header ───────────────────────────────────────────────────────────────
col_title, col_mode = st.columns([3, 2])
with col_title:
    st.markdown(
        """
        <div class="lai-h-lg">Legal AI Agent</div>
        <div class="lai-subtitle">LangGraph &middot; Hybrid RAG (BM25 + ChromaDB + RRF) &middot; Indian Law</div>
        """,
        unsafe_allow_html=True,
    )
with col_mode:
    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
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
    """Renders a structured contract analysis using the design system's
    badge / card / accordion components."""
    score = data.get("overall_risk_score", 0)
    level = data.get("risk_level", "UNKNOWN")
    badge_class, accent = RISK_TOKEN.get(level, ("medium", T["primary"]))

    st.markdown(
        f"""
        <div class="lai-risk-banner" style="border-left:4px solid {accent};">
          <div>
            <span class="lai-badge {badge_class}">{level} &middot; {score}/10</span>
            <div style="height:8px"></div>
            <div class="lai-body">{data.get('summary', '')}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    issues = data.get("issues", [])
    if issues:
        st.markdown(
            f"""<div class="lai-h-sm" style="display:flex;align-items:center;gap:8px;margin:18px 0 8px;">
            {icon('flag', 16, color=T['critical'])} Red flag clauses ({len(issues)})</div>""",
            unsafe_allow_html=True,
        )
        for issue in issues:
            risk_score = issue.get("risk_score", 0)
            with st.expander(
                f"{issue.get('flag', 'Unknown')} — Risk {risk_score}/10 ({issue.get('clause_type', '')})"
            ):
                st.markdown(
                    f"""<div class="lai-caption-bold" style="display:flex;gap:6px;align-items:center;">
                    {icon('clipboard', 13)} EXCERPT</div>
                    <div class="lai-body" style="font-style:italic;color:var(--steel);margin-bottom:14px;">
                    "{issue.get('excerpt', 'N/A')}"</div>""",
                    unsafe_allow_html=True,
                )
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(
                        f"""<div class="lai-caption-bold" style="display:flex;gap:6px;align-items:center;">
                        {icon('alert', 13, color=T['attention'])} BUSINESS IMPACT</div>""",
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f"<div class='lai-card-flat lai-body'>{issue.get('impact', 'N/A')}</div>",
                        unsafe_allow_html=True,
                    )
                with col2:
                    st.markdown(
                        f"""<div class="lai-caption-bold" style="display:flex;gap:6px;align-items:center;">
                        {icon('check-circle', 13, color=T['success'])} SUGGESTED REVISION</div>""",
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f"<div class='lai-card-flat lai-body'>{issue.get('suggested_revision', 'N/A')}</div>",
                        unsafe_allow_html=True,
                    )

    positives = data.get("positive_clauses", [])
    if positives:
        st.markdown(
            f"""<div class="lai-h-sm" style="display:flex;align-items:center;gap:8px;margin:18px 0 8px;">
            {icon('check-circle', 16, color=T['success'])} Protective clauses</div>""",
            unsafe_allow_html=True,
        )
        for p in positives:
            st.markdown(f"<div class='lai-body' style='margin-bottom:4px;'>&middot; {p}</div>", unsafe_allow_html=True)

    col_miss, col_rec = st.columns(2)
    missing = data.get("missing_clauses", [])
    recs = data.get("recommendations", [])
    with col_miss:
        if missing:
            st.markdown(
                f"""<div class="lai-h-sm" style="display:flex;align-items:center;gap:8px;margin:18px 0 8px;">
                {icon('alert', 16, color=T['attention'])} Missing clauses</div>""",
                unsafe_allow_html=True,
            )
            for m in missing:
                st.markdown(f"<div class='lai-card-flat lai-body'>{m}</div>", unsafe_allow_html=True)
    with col_rec:
        if recs:
            st.markdown(
                f"""<div class="lai-h-sm" style="display:flex;align-items:center;gap:8px;margin:18px 0 8px;">
                {icon('clipboard', 16, color=T['primary'])} Action items</div>""",
                unsafe_allow_html=True,
            )
            for r_i, r in enumerate(recs, 1):
                st.markdown(f"<div class='lai-body' style='margin-bottom:6px;'>{r_i}. {r}</div>", unsafe_allow_html=True)


# ── Chat Display ──────────────────────────────────────────────────────────────
for i, msg in enumerate(st.session_state.messages):
    avatar = USER_AVATAR if msg["role"] == "user" else (
        CONTRACT_AVATAR if st.session_state.mode == "contract" else ADVISOR_AVATAR
    )
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
    with st.expander("RAG quality evaluation (LLM-as-Judge)", expanded=False):
        st.markdown(format_eval_for_display(st.session_state.last_eval))

# ── Chat Input ────────────────────────────────────────────────────────────────
placeholder = (
    "Ask a legal question (e.g. 'What are my rights if arrested without warrant?')"
    if st.session_state.mode == "advisor"
    else "Paste contract text here for risk analysis..."
)

if prompt := st.chat_input(placeholder):
    # Auto-title thread from first user message
    if not st.session_state.messages:
        title = prompt[:50] + ("..." if len(prompt) > 50 else "")
        update_thread_title(st.session_state.current_thread, title)

    # Display user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(prompt)
    save_message(st.session_state.current_thread, "user", prompt)

    # Run agent
    with st.spinner("Agentic RAG reasoning…"):
        try:
            input_state = AgentState(
                messages=[{"role": "user", "content": prompt}],
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

            assistant_avatar = CONTRACT_AVATAR if st.session_state.mode == "contract" else ADVISOR_AVATAR
            with st.chat_message("assistant", avatar=assistant_avatar):
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

            # LLM-as-Judge evaluation (advisor mode only)
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
st.markdown(
    f"""
    <div style="display:flex; gap:8px; align-items:flex-start; color:var(--stone); font-size:12px; line-height:1.5;">
      <span style="flex-shrink:0; margin-top:1px;">{icon('shield', 14, color=T['stone'])}</span>
      <span>AI-generated legal information only — not a substitute for professional legal advice from a licensed advocate.</span>
    </div>
    """,
    unsafe_allow_html=True,
)