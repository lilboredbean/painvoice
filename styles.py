def get_css():
    return """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

:root {
  --pv-blue:        #25AFF4;
  --pv-blue-dark:   #1C97D6;
  --pv-blue-bg:     #EAF7FD;
  --pv-ink:         #171A1C;
  --pv-sub:         #5B6470;
  --pv-muted:       #8A929C;
  --pv-border:      #E7E8EA;
  --pv-page-bg:     #F9FAFA;
  --pv-card-bg:     #FFFFFF;
  --pv-sidebar-bg:  #FCFCFC;
  --pv-red:         #D42525;
  --pv-red-bg:      #FDF4F4;
  --pv-red-soft:    #FCE9E9;
  --pv-green:       #1FA34D;
  --pv-green-bg:    #F4FCF4;
  --pv-amber:       #C8860A;
  --pv-amber-bg:    #FDF8EC;
  --radius:         12px;
  --radius-lg:      16px;
}

html, body, [class*="css"] {
  font-family: 'Plus Jakarta Sans', sans-serif;
}

/* Force light form-control rendering regardless of OS/browser dark-mode
   preference. Without this, browsers can paint native form elements (and
   Streamlit/BaseWeb portal-rendered menus below) with a dark UA theme
   before our CSS below takes over, which is what caused the black
   dropdown/button flash. */
html { color-scheme: light only; }

/* page background */
[data-testid="stAppViewContainer"] {
  background-color: var(--pv-page-bg);
}
[data-testid="stHeader"] { background-color: transparent; }

.block-container {
  padding-top: 1.5rem !important;
  max-width: 1200px;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
  background-color: var(--pv-sidebar-bg) !important;
  border-right: 1px solid var(--pv-border);
}
[data-testid="stSidebar"] > div:first-child { padding-top: 1.2rem; }

/* ── Typography ── */
h1 { font-weight: 800 !important; color: var(--pv-ink) !important; letter-spacing: -0.01em; }
h2, h3 { font-weight: 700 !important; color: var(--pv-ink) !important; }
p, span, div, label { color: var(--pv-ink); }

/* ── Buttons (default = primary teal) ──
   .stFormSubmitButton covers st.form_submit_button (e.g. the Sign In
   button) and .stDownloadButton covers st.download_button (e.g. the PDF
   report download) — Streamlit renders each under its own wrapper class
   distinct from .stButton, so without explicitly covering them here they
   fall back to default (dark) styling, same root cause as the Sign In
   button bug. */
.stButton > button,
.stFormSubmitButton > button,
.stDownloadButton > button {
  background: var(--pv-blue) !important;
  color: #FFFFFF !important;
  border: none !important;
  border-radius: 10px !important;
  font-weight: 600 !important;
  font-size: 0.92rem !important;
  padding: 0.55rem 1.3rem !important;
  box-shadow: none !important;
  transition: background 0.15s ease;
}
.stButton > button:hover,
.stFormSubmitButton > button:hover,
.stDownloadButton > button:hover { background: var(--pv-blue-dark) !important; }
.stButton > button p,
.stFormSubmitButton > button p,
.stDownloadButton > button p { color: #FFFFFF !important; }

/* secondary-style button via kind=secondary */
.stButton > button[kind="secondary"],
.stFormSubmitButton > button[kind="secondary"],
.stDownloadButton > button[kind="secondary"] {
  background: #FFFFFF !important;
  color: var(--pv-ink) !important;
  border: 1px solid var(--pv-border) !important;
}
.stButton > button[kind="secondary"]:hover,
.stFormSubmitButton > button[kind="secondary"]:hover,
.stDownloadButton > button[kind="secondary"]:hover {
  background: #F5F6F7 !important;
  border-color: #D6D8DB !important;
}
.stButton > button[kind="secondary"] p,
.stFormSubmitButton > button[kind="secondary"] p,
.stDownloadButton > button[kind="secondary"] p { color: var(--pv-ink) !important; }

/* ── Inputs ── */
.stTextInput > div > div > input,
.stTextArea textarea,
.stNumberInput input,
.stSelectbox > div > div,
.stDateInput input {
  background: #FFFFFF !important;
  border: 1px solid var(--pv-border) !important;
  border-radius: 10px !important;
  color: var(--pv-ink) !important;
}
.stTextInput > div > div > input:focus,
.stTextArea textarea:focus {
  border-color: var(--pv-blue) !important;
  box-shadow: 0 0 0 1px var(--pv-blue) !important;
}
label, .stTextInput label, .stSelectbox label, .stTextArea label {
  color: var(--pv-sub) !important;
  font-size: 0.82rem !important;
  font-weight: 500 !important;
}

/* ── Selectbox closed/collapsed value display ──
   Maximal-specificity + testid-based override, using a full wildcard
   inside the control rather than trying to guess BaseWeb's exact nested
   div/span structure (a previous, narrower attempt at this still left
   the closed value invisible — the open dropdown list uses a completely
   separate code path/portal and was already fixed above, but the CLOSED
   control's "selected value" text lives deeper than div/span alone
   reached). BaseWeb's own Select styling is injected via emotion CSS-in-
   JS, sometimes also flagged !important, which can win a same-
   specificity tie against an external rule purely on source order —
   chaining ancestor context (html body ...) raises our rule's
   specificity enough to win outright instead of relying on that
   tiebreak. -webkit-text-fill-color is added because some engines use it
   instead of/in addition to color for form-control text. */
html body [data-testid="stSelectbox"] > div > div {
  background-color: #FFFFFF !important;
  border: 1px solid var(--pv-border) !important;
  border-radius: 10px !important;
}
html body [data-testid="stSelectbox"] * {
  background-color: transparent !important;
  color: var(--pv-ink) !important;
  -webkit-text-fill-color: var(--pv-ink) !important;
}
html body [data-testid="stSelectbox"] svg {
  fill: var(--pv-muted) !important;
}

/* ── Selectbox / dropdown popover menus ──
   These render in a portal appended outside the normal app container, so
   the rules above (scoped to .stSelectbox) never reach them. Left
   unstyled, they fall back to Streamlit/BaseWeb's own theme — which can
   render black if the visitor's browser/OS prefers dark mode. Cover
   multiple selectors since exact test-ids vary across Streamlit versions. */
div[data-baseweb="popover"] { z-index: 999999 !important; }
div[data-baseweb="popover"] > div,
div[data-baseweb="popover"] ul,
[data-testid="stSelectboxVirtualDropdown"] {
  background-color: #FFFFFF !important;
  border: 1px solid var(--pv-border) !important;
  box-shadow: 0 6px 20px rgba(23, 26, 28, 0.12) !important;
}
div[data-baseweb="popover"] li,
[data-testid="stSelectboxVirtualDropdown"] li,
ul[role="listbox"] li,
li[role="option"] {
  background-color: #FFFFFF !important;
  color: var(--pv-ink) !important;
}
div[data-baseweb="popover"] li *,
[data-testid="stSelectboxVirtualDropdown"] li * {
  color: var(--pv-ink) !important;
}
div[data-baseweb="popover"] li:hover,
[data-testid="stSelectboxVirtualDropdown"] li:hover,
li[role="option"]:hover {
  background-color: #F0F1F2 !important;
}
li[aria-selected="true"] {
  background-color: var(--pv-blue-bg) !important;
  color: var(--pv-blue-dark) !important;
}

/* ── Dialog / modal (st.dialog, e.g. "Create New Patient") ──
   Same portal problem as the popovers above: st.dialog renders its own
   container outside the styled app tree. Our global text-color rules
   (h1/h2/p/label etc.) DO still reach inside it — CSS selectors aren't
   scoped by DOM portal boundaries — but nothing was setting the modal's
   own background, so it fell back to a dark default and swallowed all
   that (correctly-colored-for-a-white-background) text. */
div[data-testid="stDialog"] [role="dialog"],
div[data-baseweb="modal"] [role="dialog"],
div[role="dialog"] {
  background-color: #FFFFFF !important;
}
div[data-testid="stDialog"] * ,
div[data-baseweb="modal"] [role="dialog"] * {
  color: var(--pv-ink);
}
div[data-testid="stDialog"] h1,
div[data-testid="stDialog"] h2,
div[data-testid="stDialog"] h3 {
  color: var(--pv-ink) !important;
}

/* ── Date-input calendar popover ── */
div[data-baseweb="calendar"] {
  background-color: #FFFFFF !important;
  color: var(--pv-ink) !important;
}

/* ── Cards ── */
.pv-card {
  background: var(--pv-card-bg);
  border: 1px solid var(--pv-border);
  border-radius: var(--radius-lg);
  padding: 1.4rem 1.6rem;
  margin-bottom: 1rem;
}
.pv-card-flush { padding: 0; overflow: hidden; }

.pv-section-title {
  font-weight: 700;
  font-size: 1rem;
  color: var(--pv-ink);
  margin-bottom: 0.2rem;
}
.pv-section-sub {
  font-size: 0.83rem;
  color: var(--pv-sub);
  margin-bottom: 1rem;
}

/* ── Badges ── */
.pv-badge {
  display: inline-block;
  padding: 3px 11px;
  border-radius: 999px;
  font-size: 0.74rem;
  font-weight: 600;
}
.pv-badge-blue   { background: var(--pv-blue-bg);  color: var(--pv-blue-dark); }
.pv-badge-red    { background: var(--pv-red-soft); color: var(--pv-red); }
.pv-badge-green  { background: #E3F6E9; color: var(--pv-green); }
.pv-badge-amber  { background: var(--pv-amber-bg); color: var(--pv-amber); }
.pv-badge-gray   { background: #F0F1F2; color: var(--pv-sub); }

/* ── Top header bar ── */
.pv-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.7rem 0;
  margin-bottom: 1.2rem;
}
.pv-logo {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 800;
  font-size: 1.15rem;
  color: var(--pv-ink);
}
.pv-logo-icon {
  width: 32px; height: 32px;
  border-radius: 8px;
  background: var(--pv-blue);
  display: flex; align-items: center; justify-content: center;
  color: white; font-size: 1rem;
}

/* Compact "chip" size for the topbar Logout button specifically, scoped
   via its widget key so no other buttons are affected. */
.st-key-topbar_logout button {
  padding: 0.3rem 0.7rem !important;
  font-size: 0.78rem !important;
}

/* ── KPI metric card ── */
.pv-kpi {
  background: #FFFFFF;
  border: 1px solid var(--pv-border);
  border-radius: var(--radius-lg);
  padding: 1.1rem 1.3rem;
}
.pv-kpi-icon {
  width: 34px; height: 34px;
  border-radius: 9px;
  background: var(--pv-blue-bg);
  display: flex; align-items: center; justify-content: center;
  font-size: 1rem;
  margin-bottom: 0.6rem;
}
.pv-kpi-label { font-size: 0.72rem; color: var(--pv-muted); text-transform: uppercase; letter-spacing: .05em; font-weight: 600; }
.pv-kpi-value { font-size: 1.7rem; font-weight: 800; color: var(--pv-ink); margin: 2px 0; }
.pv-kpi-delta { font-size: 0.78rem; color: var(--pv-green); }

/* ── Divider ── */
.pv-hr { border: none; border-top: 1px solid var(--pv-border); margin: 0.9rem 0; }

/* ── Patient avatar ── */
.pv-avatar {
  width: 40px; height: 40px;
  border-radius: 50%;
  background: linear-gradient(135deg, #BEE3F8, #91CEF2);
  display: flex; align-items: center; justify-content: center;
  font-weight: 700; color: #1C5A7E; font-size: 0.9rem;
}

/* ── nav buttons (sidebar) styled like tabs ── */
[data-testid="stSidebar"] .stButton > button {
  background: transparent !important;
  color: var(--pv-sub) !important;
  border: none !important;
  text-align: left !important;
  justify-content: flex-start !important;
  font-weight: 600 !important;
  padding: 0.5rem 0.7rem !important;
  border-radius: 8px !important;
}
[data-testid="stSidebar"] .stButton > button p { color: var(--pv-sub) !important; text-align: left; }
[data-testid="stSidebar"] .stButton > button:hover { background: #F0F1F2 !important; }
[data-testid="stSidebar"] .stButton > button[kind="primary"] {
  background: var(--pv-blue-bg) !important;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"] p { color: var(--pv-blue-dark) !important; }

/* hide default chrome */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }

/* progress bar override */
.stProgress > div > div > div > div { background-color: var(--pv-blue) !important; }

/* checkbox */
.stCheckbox label p { color: var(--pv-sub) !important; font-size: 0.85rem !important; }

/* alert override */
.stAlert { border-radius: 10px !important; }

/* expander — the old .streamlit-expanderHeader hook no longer matches
   current Streamlit markup, which left the header bar at its dark
   default background with equally-dark (invisible) text. Target the
   stable [data-testid="stExpander"] wrapper plus the raw <summary>/
   <details> elements Streamlit renders it with, so this keeps working
   even if internal class/testid names shift again. */
[data-testid="stExpander"] {
  border: 1px solid var(--pv-border) !important;
  border-radius: 10px !important;
  background: #FFFFFF !important;
  overflow: hidden;
}
[data-testid="stExpander"] summary,
[data-testid="stExpander"] details {
  background: #FFFFFF !important;
  color: var(--pv-ink) !important;
}
[data-testid="stExpander"] summary *,
[data-testid="stExpander"] summary svg {
  color: var(--pv-ink) !important;
  fill: var(--pv-ink) !important;
}
[data-testid="stExpander"] [data-testid="stExpanderDetails"] {
  background: #FFFFFF !important;
}
.streamlit-expanderHeader { background: #FFFFFF !important; border-radius: 10px !important; }

/* scrollbar */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-thumb { background: #D6D8DB; border-radius: 3px; }
</style>
"""