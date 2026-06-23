"""
theme.py
────────
Design tokens transcribed from DESIGN-meta.md, plus the single function
that turns them into a <style> block Streamlit injects on every render.

Dark-mode values are not part of the source system (see "Known Gaps" in
DESIGN-meta.md) — they are derived here following the same rule the
source system uses for its one dark surface (`card-promo-strip`):
ink-deep becomes the canvas, canvas becomes the ink. The cobalt accent
is held constant across both modes, exactly as the source forbids
introducing additional accent colors.
"""

FONT_STACK = (
    '"Inter", "Montserrat", -apple-system, Helvetica, Arial, '
    '"Noto Sans", sans-serif'
)

RADIUS = {
    "xs": "2px", "sm": "4px", "md": "6px", "lg": "8px", "xl": "16px",
    "xxl": "24px", "xxxl": "32px", "feature": "40px", "full": "100px",
    "circle": "50%",
}

SPACE = {
    "xxs": "4px", "xs": "8px", "sm": "10px", "md": "12px", "base": "16px",
    "lg": "20px", "xl": "24px", "xxl": "32px", "xxxl": "40px",
    "section_sm": "48px", "section": "64px", "section_lg": "80px",
}

LIGHT = {
    "canvas": "#ffffff",
    "surface-soft": "#f1f4f7",
    "surface-raised": "#ffffff",
    "ink-deep": "#0a1317",
    "ink": "#1c1e21",
    "charcoal": "#444950",
    "steel": "#5d6c7b",
    "stone": "#8595a4",
    "hairline": "#ced0d4",
    "hairline-soft": "#dee3e9",
    "disabled-text": "#bcc0c4",
    "ink-button-bg": "#000000",
    "ink-button-fg": "#ffffff",
    "shadow-sticky": "rgba(20, 22, 26, 0.12)",
}

DARK = {
    "canvas": "#0a1317",
    "surface-soft": "#141b20",
    "surface-raised": "#161d22",
    "ink-deep": "#f5f7f8",
    "ink": "#e4e6e8",
    "charcoal": "#c2c6cb",
    "steel": "#93a0ac",
    "stone": "#677482",
    "hairline": "rgba(255,255,255,0.16)",
    "hairline-soft": "rgba(255,255,255,0.09)",
    "disabled-text": "#46505a",
    "ink-button-bg": "#f5f7f8",
    "ink-button-fg": "#0a1317",
    "shadow-sticky": "rgba(0, 0, 0, 0.45)",
}

# Held constant across themes — the system explicitly scopes accent
# colors to cobalt + Oculus purple and forbids adding more.
SHARED = {
    "primary": "#0064e0",
    "primary-deep": "#0457cb",
    "primary-soft": "#0091ff",
    "on-primary": "#ffffff",
    "success": "#31a24c",
    "warning": "#f7b928",
    "attention": "#f2a918",
    "critical": "#e41e3f",
    "critical-strong": "#f0284a",
}


def tokens(theme: str) -> dict:
    base = DARK if theme == "dark" else LIGHT
    return {**base, **SHARED}


def inject_css(theme: str) -> str:
    t = tokens(theme)
    return f"""
<style>
:root {{
  --canvas: {t['canvas']};
  --surface-soft: {t['surface-soft']};
  --surface-raised: {t['surface-raised']};
  --ink-deep: {t['ink-deep']};
  --ink: {t['ink']};
  --charcoal: {t['charcoal']};
  --steel: {t['steel']};
  --stone: {t['stone']};
  --hairline: {t['hairline']};
  --hairline-soft: {t['hairline-soft']};
  --disabled-text: {t['disabled-text']};
  --ink-button-bg: {t['ink-button-bg']};
  --ink-button-fg: {t['ink-button-fg']};
  --shadow-sticky: {t['shadow-sticky']};
  --primary: {t['primary']};
  --primary-deep: {t['primary-deep']};
  --primary-soft: {t['primary-soft']};
  --on-primary: {t['on-primary']};
  --success: {t['success']};
  --warning: {t['warning']};
  --attention: {t['attention']};
  --critical: {t['critical']};
  --critical-strong: {t['critical-strong']};
  --font: {FONT_STACK};
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
.block-container {{ padding-top: 1.25rem; max-width: 1280px; }}

[data-testid="stSidebar"] {{
  background: var(--surface-soft);
  border-right: 1px solid var(--hairline-soft);
}}
[data-testid="stSidebarContent"] {{ padding-top: 1.25rem; }}

hr, [data-testid="stDivider"] {{ border-color: var(--hairline-soft) !important; }}

/* ---------- Typography tiers (DESIGN-meta.md `typography.*`) ---------- */
.lai-h-hero {{ font-size: 40px; font-weight: 500; line-height: 1.18; letter-spacing: 0; margin: 0; }}
.lai-h-lg {{ font-size: 28px; font-weight: 500; line-height: 1.25; margin: 0; }}
.lai-h-md {{ font-size: 20px; font-weight: 300; line-height: 1.3; margin: 0; color: var(--steel); }}
.lai-h-sm {{ font-size: 16px; font-weight: 600; line-height: 1.3; margin: 0; }}
.lai-subtitle {{ font-size: 15px; font-weight: 400; line-height: 1.45; color: var(--steel); margin: 0; }}
.lai-body {{ font-size: 14px; font-weight: 400; line-height: 1.5; letter-spacing: -0.1px; }}
.lai-body-bold {{ font-size: 14px; font-weight: 700; line-height: 1.5; letter-spacing: -0.1px; }}
.lai-caption {{ font-size: 12px; font-weight: 400; line-height: 1.33; color: var(--stone); }}
.lai-caption-bold {{ font-size: 12px; font-weight: 700; line-height: 1.33; }}

/* ---------- Header / brand ---------- */
.lai-brand {{ display: flex; align-items: center; gap: 10px; }}
.lai-brand-mark {{
  width: 34px; height: 34px; border-radius: {RADIUS['lg']};
  background: var(--primary); display: flex; align-items: center;
  justify-content: center; color: var(--on-primary); flex-shrink: 0;
}}
.lai-brand-name {{ font-size: 19px; font-weight: 600; letter-spacing: -0.2px; color: var(--ink-deep); }}
.lai-brand-sub {{ font-size: 12px; color: var(--stone); margin-top: -2px; }}

/* ---------- Buttons (component tokens) ---------- */
.stButton > button {{
  border-radius: {RADIUS['full']} !important;
  font-weight: 700 !important;
  font-size: 13.5px !important;
  letter-spacing: -0.1px;
  transition: background 150ms ease-out, color 150ms ease-out, border-color 150ms ease-out;
  box-shadow: none !important;
}}
/* primary (type="primary") -> button-primary: ink pill */
.stButton > button[kind="primary"] {{
  background: var(--ink-button-bg) !important;
  color: var(--ink-button-fg) !important;
  border: 1px solid var(--ink-button-bg) !important;
}}
.stButton > button[kind="primary"]:hover {{ background: var(--charcoal) !important; border-color: var(--charcoal) !important; }}
/* secondary (type="secondary") -> button-ghost */
.stButton > button[kind="secondary"] {{
  background: transparent !important;
  color: var(--ink-deep) !important;
  border: 1.5px solid var(--hairline) !important;
}}
.stButton > button[kind="secondary"]:hover {{ border-color: var(--ink-deep) !important; }}

.stDownloadButton > button {{
  border-radius: {RADIUS['full']} !important;
  background: transparent !important;
  color: var(--ink-deep) !important;
  border: 1.5px solid var(--hairline) !important;
  font-weight: 700 !important; font-size: 13.5px !important;
}}

/* circular icon buttons (delete) */
.lai-icon-btn button {{
  border-radius: {RADIUS['circle']} !important;
  width: 34px !important; height: 34px !important;
  padding: 0 !important;
  background: transparent !important;
  border: 1px solid var(--hairline) !important;
  color: var(--steel) !important;
}}
.lai-icon-btn button:hover {{ border-color: var(--critical) !important; color: var(--critical) !important; }}

/* ---------- Pill-tab nav (mode switch) ---------- */
div[data-testid="stRadio"] > div {{
  gap: 8px;
  background: var(--surface-soft);
  padding: 4px; border-radius: {RADIUS['full']};
  display: inline-flex;
}}
div[data-testid="stRadio"] label {{
  border-radius: {RADIUS['full']} !important;
  padding: 8px 18px !important;
  margin: 0 !important;
  font-weight: 700; font-size: 13.5px;
  background: transparent;
  transition: background 150ms ease-out, color 150ms ease-out;
}}
div[data-testid="stRadio"] label[data-checked="true"],
div[data-testid="stRadio"] label:has(input:checked) {{
  background: var(--ink-deep) !important;
  color: var(--canvas) !important;
}}
div[data-testid="stRadio"] input {{ position: absolute; opacity: 0; }}
div[data-testid="stRadio"] [data-testid="stMarkdownContainer"] p {{ font-size: 13.5px; font-weight: 700; }}

/* ---------- Animated theme dropdown ---------- */
div[data-testid="stSelectbox"] > div > div {{
  border-radius: {RADIUS['full']} !important;
  border: 1px solid var(--hairline) !important;
  background: var(--canvas) !important;
}}
div[data-testid="stSelectbox"] {{ animation: lai-fade-in 220ms ease-out; }}
ul[data-testid="stSelectboxVirtualDropdown"],
div[data-baseweb="popover"] {{
  animation: lai-dropdown-open 200ms cubic-bezier(0.16, 1, 0.3, 1);
  transform-origin: top center;
}}
@keyframes lai-dropdown-open {{
  from {{ opacity: 0; transform: scaleY(0.85) translateY(-4px); }}
  to   {{ opacity: 1; transform: scaleY(1) translateY(0); }}
}}
@keyframes lai-fade-in {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}

/* ---------- Chat ---------- */
[data-testid="stChatMessage"] {{
  background: var(--surface-soft);
  border: 1px solid var(--hairline-soft);
  border-radius: {RADIUS['xl']};
  padding: {SPACE['base']};
  margin-bottom: {SPACE['md']};
}}
[data-testid="stChatMessageContent"] p {{ font-size: 14.5px; line-height: 1.55; }}
[data-testid="stChatInput"] textarea {{
  border-radius: {RADIUS['xl']} !important;
  border: 1px solid var(--hairline) !important;
  background: var(--canvas) !important;
}}

/* ---------- Cards ---------- */
.lai-card {{
  background: var(--surface-raised);
  border: 1px solid var(--hairline-soft);
  border-radius: {RADIUS['xl']};
  padding: {SPACE['lg']} {SPACE['xl']};
  margin-bottom: {SPACE['md']};
}}
.lai-card-flat {{
  background: var(--surface-soft);
  border-radius: {RADIUS['lg']};
  padding: {SPACE['md']} {SPACE['lg']};
  margin-bottom: {SPACE['sm']};
}}

/* ---------- Badges ---------- */
.lai-badge {{
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; font-weight: 700; line-height: 1.3;
  padding: 4px 12px; border-radius: {RADIUS['full']};
  color: #ffffff;
}}
.lai-badge.critical {{ background: var(--critical); }}
.lai-badge.high {{ background: var(--attention); }}
.lai-badge.medium {{ background: var(--primary); }}
.lai-badge.low {{ background: var(--success); }}

/* risk banner — border-left color is set inline per-instance via style attr */
.lai-risk-banner {{
  display: flex; align-items: flex-start; gap: 12px;
  border-radius: {RADIUS['xl']};
  padding: {SPACE['lg']};
  background: var(--surface-soft);
  margin-bottom: {SPACE['base']};
}}

/* sidebar thread row */
.lai-thread-row {{
  display: flex; align-items: center; gap: 8px; margin-bottom: 4px;
}}
.lai-thread-row .stButton > button {{
  border-radius: {RADIUS['lg']} !important;
  justify-content: flex-start !important;
  text-align: left !important;
  font-weight: 500 !important;
  padding: 8px 14px !important;
}}
.lai-thread-row .stButton > button[kind="secondary"] {{ border: none !important; }}
.lai-thread-row .stButton > button[kind="primary"] {{ background: var(--surface-raised) !important; color: var(--ink-deep) !important; border: 1px solid var(--hairline) !important; }}

/* responsive */
@media (max-width: 768px) {{
  .lai-h-hero {{ font-size: 26px; }}
  .lai-h-lg {{ font-size: 21px; }}
  .lai-brand-name {{ font-size: 16px; }}
  .block-container {{ padding-left: 1rem; padding-right: 1rem; }}
  div[data-testid="stRadio"] label {{ padding: 7px 12px !important; font-size: 12.5px; }}
}}
</style>
"""