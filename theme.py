"""
theme.py
────────
Design tokens transcribed from DESIGN-claude.md (Anthropic / Claude visual
system — warm cream canvas, coral primary, dark-navy product surfaces),
plus the function that turns them into a <style> block Streamlit injects
on every render.

Two surface modes are provided, both built from the same DESIGN-claude.md
token set:
  "light" — the cream canvas + ink text mode the source system documents
            for marketing/product surfaces.
  "dark"  — the source system's own `surface-dark` / `on-dark` tokens,
            promoted to the canvas. This is the same dark navy the source
            uses for code-window cards, model-comparison cards and the
            footer — not an invented fourth tone.

Coral (`primary`) is held constant across both modes, exactly as
DESIGN-claude.md requires ("the coral is scarce... but consistent").
"""

FONT_STACK = (
    '"StyreneB", "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", '
    'Roboto, sans-serif'
)
SERIF_STACK = (
    '"Copernicus", "Tiempos Headline", "Cormorant Garamond", '
    '"EB Garamond", Georgia, serif'
)
MONO_STACK = '"JetBrains Mono", ui-monospace, "SFMono-Regular", Menlo, monospace'

RADIUS = {
    "xs": "4px", "sm": "6px", "md": "8px", "lg": "12px", "xl": "16px",
    "pill": "9999px", "full": "9999px", "circle": "50%",
}

SPACE = {
    "xxs": "4px", "xs": "8px", "sm": "12px", "md": "16px", "base": "16px",
    "lg": "24px", "xl": "32px", "xxl": "48px", "section": "96px",
}

# ── Light: DESIGN-claude.md cream-canvas surface ─────────────────────────
LIGHT = {
    "canvas": "#faf9f5",
    "surface-soft": "#f5f0e8",
    "surface-raised": "#efe9de",
    "ink-deep": "#141413",
    "ink": "#141413",
    "charcoal": "#252523",
    "steel": "#3d3d3a",
    "stone": "#6c6a64",
    "disabled-text": "#8e8b82",
    "hairline": "#e6dfd8",
    "hairline-soft": "#ebe6df",
    "shadow-sticky": "rgba(20, 20, 19, 0.08)",
}

# ── Dark: DESIGN-claude.md's own surface-dark tokens, promoted to canvas ─
DARK = {
    "canvas": "#181715",
    "surface-soft": "#1f1e1b",
    "surface-raised": "#252320",
    "ink-deep": "#faf9f5",
    "ink": "#faf9f5",
    "charcoal": "#e8e4dc",
    "steel": "#a09d96",
    "stone": "#7d7a73",
    "disabled-text": "#5c5a54",
    "hairline": "rgba(250, 249, 245, 0.12)",
    "hairline-soft": "rgba(250, 249, 245, 0.06)",
    "shadow-sticky": "rgba(0, 0, 0, 0.45)",
}

# Held constant across themes — coral is the one brand accent.
SHARED = {
    "primary": "#cc785c",
    "primary-deep": "#a9583e",
    "primary-soft": "#e6dfd8",
    "on-primary": "#ffffff",
    "accent-teal": "#5db8a6",
    "accent-amber": "#e8a55a",
    "success": "#5db872",
    "warning": "#d4a017",
    "critical": "#c64545",
    "critical-strong": "#a93636",
}


def tokens(theme: str) -> dict:
    base = DARK if theme == "dark" else LIGHT
    return {**base, **SHARED}


def inject_css(theme: str) -> str:
    t = tokens(theme)
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Source+Serif+4:opsz,wght@8..60,400&display=swap');

:root {{
  --canvas: {t['canvas']};
  --surface-soft: {t['surface-soft']};
  --surface-raised: {t['surface-raised']};
  --ink-deep: {t['ink-deep']};
  --ink: {t['ink']};
  --charcoal: {t['charcoal']};
  --steel: {t['steel']};
  --stone: {t['stone']};
  --disabled-text: {t['disabled-text']};
  --hairline: {t['hairline']};
  --hairline-soft: {t['hairline-soft']};
  --shadow-sticky: {t['shadow-sticky']};
  --primary: {t['primary']};
  --primary-deep: {t['primary-deep']};
  --primary-soft: {t['primary-soft']};
  --on-primary: {t['on-primary']};
  --accent-teal: {t['accent-teal']};
  --accent-amber: {t['accent-amber']};
  --success: {t['success']};
  --warning: {t['warning']};
  --critical: {t['critical']};
  --critical-strong: {t['critical-strong']};
  --font: {FONT_STACK};
  --font-serif: {SERIF_STACK};
  --font-mono: {MONO_STACK};
}}

html, body, [class*="css"] {{ font-family: var(--font); }}

/* ---------- App shell ---------- */
.stApp {{
  background: var(--canvas);
  color: var(--ink);
  transition: background 200ms ease-out, color 200ms ease-out;
}}
[data-testid="stHeader"] {{ background: transparent; }}
#MainMenu, footer, [data-testid="stToolbar"] {{ visibility: hidden; }}
.block-container {{ padding-top: 1.5rem; max-width: 1180px; }}

[data-testid="stSidebar"] {{
  background: var(--surface-soft);
  border-right: 1px solid var(--hairline-soft);
}}
[data-testid="stSidebarContent"] {{ padding-top: 1.25rem; }}

hr, [data-testid="stDivider"] {{ border-color: var(--hairline-soft) !important; opacity: 1 !important; }}

p, span, label, div {{ letter-spacing: 0; }}

/* ---------- Global text-color pin ---------- */
/* Streamlit's native text elements ship a fixed color from its own base
   theme that does not track our CSS variables automatically — without
   this, body copy stays dark-on-dark (or light-on-light) when the page
   background flips between modes. */
body, .stApp, .stMarkdown, [data-testid="stMarkdownContainer"],
[data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li,
[data-testid="stMarkdownContainer"] strong, [data-testid="stMarkdownContainer"] em,
h1, h2, h3, h4, h5, h6,
[data-testid="stWidgetLabel"] p {{
  color: var(--ink) !important;
}}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p,
.stCaption, small {{
  color: var(--stone) !important;
}}
.lai-caption, .lai-subtitle, .lai-brand-sub {{ color: var(--stone) !important; }}
.lai-h-hero, .lai-h-lg, .lai-brand-name, .lai-h-sm {{ color: var(--ink-deep) !important; }}

/* ---------- Typography tiers ---------- */
.lai-h-hero {{ font-family: var(--font-serif); font-size: 32px; font-weight: 400; line-height: 1.15; letter-spacing: -0.5px; margin: 0; color: var(--ink-deep); }}
.lai-h-lg {{ font-family: var(--font-serif); font-size: 24px; font-weight: 400; line-height: 1.2; letter-spacing: -0.3px; margin: 0; color: var(--ink-deep); }}
.lai-h-md {{ font-size: 15px; font-weight: 400; line-height: 1.5; margin: 0; color: var(--stone); }}
.lai-h-sm {{ font-size: 14px; font-weight: 500; line-height: 1.3; margin: 0; color: var(--ink); }}
.lai-subtitle {{ font-size: 14px; font-weight: 400; line-height: 1.5; color: var(--stone); margin: 0; }}
.lai-body {{ font-size: 14.5px; font-weight: 400; line-height: 1.55; }}
.lai-caption {{ font-size: 12.5px; font-weight: 500; line-height: 1.4; color: var(--stone); }}

/* ---------- Header / brand ---------- */
.lai-brand {{ display: flex; align-items: center; gap: 12px; }}
.lai-brand-mark {{
  width: 36px; height: 36px; border-radius: {RADIUS['md']};
  background: var(--primary); display: flex; align-items: center;
  justify-content: center; color: var(--on-primary); flex-shrink: 0;
}}
.lai-brand-name {{ font-family: var(--font-serif); font-size: 22px; font-weight: 400; letter-spacing: -0.3px; color: var(--ink-deep); }}
.lai-brand-sub {{ font-size: 13px; color: var(--stone); margin-top: 1px; }}

/* ---------- Buttons (component tokens) ---------- */
.stButton > button {{
  border-radius: {RADIUS['md']} !important;
  font-weight: 500 !important;
  font-size: 13.5px !important;
  letter-spacing: 0;
  transition: background 150ms ease-out, color 150ms ease-out, border-color 150ms ease-out;
  box-shadow: none !important;
}}
/* primary -> button-primary: coral fill */
.stButton > button[kind="primary"] {{
  background: var(--primary) !important;
  color: var(--on-primary) !important;
  border: 1px solid var(--primary) !important;
}}
.stButton > button[kind="primary"]:hover {{ background: var(--primary-deep) !important; border-color: var(--primary-deep) !important; }}
/* secondary -> button-secondary: hairline outline */
.stButton > button[kind="secondary"] {{
  background: transparent !important;
  color: var(--ink-deep) !important;
  border: 1px solid var(--hairline) !important;
}}
.stButton > button[kind="secondary"]:hover {{ border-color: var(--steel) !important; background: var(--surface-raised) !important; }}

.stDownloadButton > button {{
  border-radius: {RADIUS['md']} !important;
  background: transparent !important;
  color: var(--ink-deep) !important;
  border: 1px solid var(--hairline) !important;
  font-weight: 500 !important; font-size: 13.5px !important;
}}
.stDownloadButton > button:hover {{ border-color: var(--steel) !important; }}

/* circular icon buttons (delete) */
.lai-icon-btn button {{
  border-radius: {RADIUS['circle']} !important;
  width: 32px !important; height: 32px !important;
  padding: 0 !important;
  background: transparent !important;
  border: 1px solid transparent !important;
  color: var(--stone) !important;
  font-size: 16px !important;
  line-height: 1 !important;
}}
.lai-icon-btn button:hover {{ border-color: var(--critical) !important; color: var(--critical) !important; background: transparent !important; }}

/* ---------- Segmented control (mode switch) ---------- */
div[data-testid="stRadio"] > div {{
  gap: 4px;
  background: var(--surface-raised);
  padding: 4px; border-radius: {RADIUS['md']};
  display: inline-flex;
  border: 1px solid var(--hairline-soft);
}}
div[data-testid="stRadio"] label {{
  border-radius: {RADIUS['sm']} !important;
  padding: 7px 16px !important;
  margin: 0 !important;
  font-weight: 500; font-size: 13.5px;
  background: transparent;
  transition: background 150ms ease-out, color 150ms ease-out;
}}
div[data-testid="stRadio"] label[data-checked="true"],
div[data-testid="stRadio"] label:has(input:checked) {{
  background: var(--canvas) !important;
  color: var(--ink-deep) !important;
}}
div[data-testid="stRadio"] input {{ position: absolute; opacity: 0; }}
div[data-testid="stRadio"] [data-testid="stMarkdownContainer"] p {{ font-size: 13.5px; font-weight: 500; }}

/* compact theme-mode radio (sun/moon) in sidebar */
.lai-theme-toggle div[data-testid="stRadio"] > div {{
  background: transparent; border: none; padding: 0; gap: 6px;
}}
.lai-theme-toggle div[data-testid="stRadio"] label {{
  border: 1px solid var(--hairline); border-radius: {RADIUS['sm']} !important;
  padding: 6px 10px !important;
}}
.lai-theme-toggle div[data-testid="stRadio"] label:has(input:checked) {{
  background: var(--surface-raised) !important; border-color: var(--steel) !important;
}}

/* ---------- Toggle ---------- */
[data-testid="stToggle"] label div[data-checked="true"], 
div[data-testid="stToggle"] span[role="checkbox"][aria-checked="true"] {{
  background-color: var(--primary) !important;
}}

/* ---------- Chat ---------- */
[data-testid="stChatMessage"] {{
  background: transparent;
  border: none;
  padding: {SPACE['sm']} 0;
  margin-bottom: 0;
  gap: 12px;
}}
/* assistant: flat, reads like editorial text */
[data-testid="stChatMessage"]:has([data-testid="stChatAvatarIcon-assistant"]) [data-testid="stChatMessageContent"] {{
  background: transparent;
}}
/* user: right-aligned coral-tinted cream bubble */
[data-testid="stChatMessage"]:has([data-testid="stChatAvatarIcon-user"]) {{
  flex-direction: row-reverse;
}}
[data-testid="stChatMessage"]:has([data-testid="stChatAvatarIcon-user"]) [data-testid="stChatMessageContent"] {{
  background: var(--surface-raised);
  border-radius: {RADIUS['lg']};
  padding: 10px 16px;
  margin-left: auto;
}}
[data-testid="stChatMessageAvatarUser"], [data-testid="stChatMessageAvatarCustom"] {{
  width: 28px !important; height: 28px !important;
}}
[data-testid="stChatMessageContent"] p {{ font-size: 15px; line-height: 1.6; color: var(--ink); }}
/* fixed bottom chat-input bar — Streamlit renders this in its own
   sticky container that does not inherit .stApp's background, so it
   must be themed explicitly or it stays on Streamlit's default light
   chrome regardless of app theme. */
[data-testid="stBottom"], [data-testid="stBottomBlockContainer"],
.stChatFloatingInputContainer, .stChatInputContainer {{
  background: var(--canvas) !important;
}}
[data-testid="stChatInput"] {{
  background: var(--canvas) !important;
}}
[data-testid="stChatInput"] textarea {{
  border-radius: {RADIUS['xl']} !important;
  border: 1px solid var(--hairline) !important;
  background: var(--canvas) !important;
  color: var(--ink) !important;
  font-size: 14.5px !important;
}}
[data-testid="stChatInput"] textarea::placeholder {{
  color: var(--stone) !important;
}}
[data-testid="stChatInput"] textarea:focus {{
  border-color: var(--primary) !important;
  box-shadow: 0 0 0 3px rgba(204, 120, 92, 0.15) !important;
}}
[data-testid="stChatInputSubmitButton"] {{
  background: var(--primary) !important; border-radius: {RADIUS['circle']} !important;
}}
[data-testid="stChatInputSubmitButton"] svg {{ color: var(--on-primary) !important; fill: var(--on-primary) !important; }}

/* ---------- Cards ---------- */
.lai-card {{
  background: var(--surface-raised);
  border: 1px solid var(--hairline-soft);
  border-radius: {RADIUS['lg']};
  padding: {SPACE['lg']} {SPACE['xl']};
  margin-bottom: {SPACE['md']};
}}
.lai-card-flat {{
  background: var(--surface-soft);
  border-radius: {RADIUS['md']};
  padding: {SPACE['md']} {SPACE['lg']};
  margin-bottom: {SPACE['sm']};
}}

/* ---------- Badges ---------- */
.lai-badge {{
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; font-weight: 500; line-height: 1.3;
  padding: 4px 12px; border-radius: {RADIUS['pill']};
  color: #ffffff;
}}
.lai-badge.critical {{ background: var(--critical); }}
.lai-badge.high {{ background: var(--accent-amber); color: var(--ink-deep); }}
.lai-badge.medium {{ background: var(--accent-teal); }}
.lai-badge.low {{ background: var(--success); }}

/* risk banner — border-left color set inline per instance */
.lai-risk-banner {{
  display: flex; align-items: flex-start; gap: 12px;
  border-radius: {RADIUS['md']};
  padding: {SPACE['md']} {SPACE['lg']};
  background: var(--surface-soft);
  border: 1px solid var(--hairline-soft);
  margin-bottom: {SPACE['base']};
}}

/* expander -> issue card */
[data-testid="stExpander"] {{
  border: 1px solid var(--hairline-soft) !important;
  border-radius: {RADIUS['md']} !important;
  background: var(--surface-soft) !important;
  margin-bottom: {SPACE['xs']};
}}
[data-testid="stExpander"] summary {{ font-size: 14px; }}

/* info / success / warning boxes used inside contract report */
[data-testid="stAlert"] {{
  border-radius: {RADIUS['md']} !important;
  border: 1px solid var(--hairline-soft) !important;
  background: var(--surface-soft) !important;
}}
[data-testid="stAlert"] p {{ font-size: 13.5px !important; color: var(--ink) !important; }}

/* sidebar thread row */
.lai-thread-row {{
  display: flex; align-items: center; gap: 6px; margin-bottom: 2px;
}}
.lai-thread-row .stButton > button {{
  border-radius: {RADIUS['sm']} !important;
  justify-content: flex-start !important;
  text-align: left !important;
  font-weight: 400 !important;
  font-size: 13.5px !important;
  padding: 8px 10px !important;
}}
.lai-thread-row .stButton > button[kind="secondary"] {{ border: none !important; background: transparent !important; }}
.lai-thread-row .stButton > button[kind="secondary"]:hover {{ background: var(--surface-raised) !important; }}
.lai-thread-row .stButton > button[kind="primary"] {{
  background: var(--surface-raised) !important; color: var(--ink-deep) !important;
  border: none !important; font-weight: 500 !important;
}}

/* responsive */
@media (max-width: 768px) {{
  .lai-h-hero {{ font-size: 24px; }}
  .lai-h-lg {{ font-size: 19px; }}
  .lai-brand-name {{ font-size: 18px; }}
  .block-container {{ padding-left: 1rem; padding-right: 1rem; }}
  div[data-testid="stRadio"] label {{ padding: 6px 11px !important; font-size: 12.5px; }}
}}
</style>
"""
