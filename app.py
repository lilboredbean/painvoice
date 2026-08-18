import streamlit as st
import time
import os
from datetime import datetime

from styles import get_css
from data import (
    PATIENTS, CLINICIAN, DASHBOARD_KPIS, SYSTEM_INSIGHTS, RECENT_ACTIVITY,
    ACOUSTIC_BIOMARKERS_HIGH, ACOUSTIC_BIOMARKERS_LOW, AI_NOTES_HIGH, AI_NOTES_LOW,
    AI_SUGGESTIONS, CLINICAL_NOTES, COMMON_PAINKILLERS, new_patient_record,
    record_voice_session,
)
from gru_mixer import PainVoiceAnalyzer, TARGET_SR as VOICE_SAMPLE_RATE
from pdf_report import build_medical_report_pdf, build_effectiveness_report_pdf

st.set_page_config(page_title="PainVoice", page_icon="🩺", layout="wide", initial_sidebar_state="collapsed")
st.markdown(get_css(), unsafe_allow_html=True)

# Sample recordings for the Demo Patient's one-click quick-test buttons in
# Voice Capture. Ship these three files in a "demo_audio/" folder next to
# app.py — paths are resolved relative to this script, not the working
# directory the app happens to be launched from.
#
# The classification for these is intentionally SCRIPTED (see
# gru_mixer.analyze_scripted), not live model inference: with no trained
# checkpoint, live inference is arbitrary (see gru_mixer.py's docstring),
# so a button explicitly labeled "High Pain Sample" showing the model's
# random guess instead would just be confusing. Biomarkers/spectrogram are
# still computed for real from the actual audio.
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
DEMO_SAMPLES = [
    ("🟢", "Low Pain Sample", os.path.join(_APP_DIR, "demo_audio", "low_pain.wav"), "Low Pain", 94.0),
    ("🟡", "Moderate Pain Sample", os.path.join(_APP_DIR, "demo_audio", "moderate_pain.wav"), "Moderate Pain", 87.0),
    ("🔴", "High Pain Sample", os.path.join(_APP_DIR, "demo_audio", "high_pain.wav"), "High Pain", 91.0),
]

# Session state
def init_state():
    defaults = {
        "auth": False,
        "page": "login",
        "reg_step": 1,
        "active_patient_idx": 1,   # default to Maria Rodriguez (has session history)
        "session_id": "#SESS-2024-0512",
        "recording_state": "ready",   # ready | recording | done
        "last_classification": None,  # "High" or "Low", set after recording
        "last_result": None,          # full GRU-Mixer analysis dict for the active session
        "audio_bytes": None,          # raw bytes captured from st.audio_input
        "voice_error": None,
        "show_spectrogram": False,
        "show_alert_modal": False,
        "alert_sent": False,
        "suggestions_shown": False,
        "report_generated": False,
        "medical_report_pdf": None,
        "effectiveness_report_pdf": None,
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)

init_state()


def go(page):
    st.session_state.page = page
    st.rerun()


def current_patient():
    return PATIENTS[st.session_state.active_patient_idx]


def classification_colors(label: str):
    """(bg, border, accent, badge_class) CSS values for a pain
    classification label — keeps Low/Moderate/High visually distinct
    (green / amber-yellow / red) everywhere a classification is shown,
    instead of the old binary "is_high" red-or-green split that lumped
    Moderate Pain in with High Pain."""
    if label == "High Pain":
        return "var(--pv-red-bg)", "#F6CFCF", "var(--pv-red)", "pv-badge-red"
    if label == "Moderate Pain":
        return "var(--pv-amber-bg)", "#F5DBA3", "var(--pv-amber)", "pv-badge-amber"
    return "var(--pv-green-bg)", "#CDEFD4", "var(--pv-green)", "pv-badge-green"


@st.dialog("Create New Patient")
def create_patient_dialog():
    st.markdown(
        '<div style="color:var(--pv-sub); font-size:0.85rem; margin-bottom:0.6rem;">'
        "Enter the new patient's core details. Clinical specifics like care plan and "
        "session history can be filled in later from their file.</div>",
        unsafe_allow_html=True,
    )
    with st.form("create_patient_form"):
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input("Full Name*", placeholder="e.g. Emily Turner")
            age = st.number_input("Age*", min_value=0, max_value=120, value=45, step=1)
            gender = st.selectbox("Gender*", ["Female", "Male", "Other"])
        with c2:
            dob = st.text_input("Date of Birth", placeholder="e.g. Jun 14, 1979")
            blood_type = st.selectbox(
                "Blood Type", ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-", "Unknown"], index=8
            )
            care_plan = st.text_input("Initial Care Plan", placeholder="e.g. Naproxen 500mg BID")
        condition = st.text_input("Primary Condition / Diagnosis*", placeholder="e.g. Chronic Lower Back Pain (L4-L5)")
        allergies = st.text_input("Known Allergies", placeholder="Comma-separated, e.g. Penicillin, Latex — leave blank if none")

        submitted = st.form_submit_button("⊕  Create Patient", use_container_width=True)
        if submitted:
            if not name.strip() or not condition.strip():
                st.error("Full Name and Primary Condition are required.")
            else:
                existing_ids = {pt["id"] for pt in PATIENTS}
                record = new_patient_record(
                    name.strip(), int(age), gender, blood_type, dob.strip(),
                    condition.strip(), allergies, care_plan.strip(), existing_ids=existing_ids,
                )
                PATIENTS.append(record)
                st.session_state.active_patient_idx = len(PATIENTS) - 1
                st.session_state.page = "patient"
                st.rerun()


# Shared chrome
def topbar(back=False):
    cols = st.columns([0.06, 0.55, 0.39], gap="small") if back else st.columns([0.61, 0.39], gap="small")
    idx = 0
    if back:
        with cols[0]:
            if st.button("←", key="topbar_back"):
                go("dashboard")
        idx = 1
    with cols[idx]:
        st.markdown("""
        <div class="pv-logo" style="padding-top:6px;">
            <div class="pv-logo-icon">📈</div> PainVoice
        </div>
        """, unsafe_allow_html=True)
    with cols[idx + 1]:
        st.markdown(f"""
        <div style="display:flex; align-items:center; justify-content:flex-end; gap:10px; padding-top:2px;">
            <div style="text-align:right;">
                <div style="font-weight:700; font-size:0.88rem; line-height:1.1;">{CLINICIAN['name']}</div>
                <div style="font-size:0.74rem; color:var(--pv-sub); line-height:1.1;">{CLINICIAN['title']}</div>
            </div>
            <div class="pv-avatar" style="width:34px;height:34px;">SC</div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
        _, btn_col = st.columns([1, 0.75])
        with btn_col:
            if st.button("⎋ Logout", key="topbar_logout", type="secondary", use_container_width=True):
                st.session_state.auth = False
                go("login")
    # st.markdown('<hr class="pv-hr">', unsafe_allow_html=True)


def sidebar_nav():
    with st.sidebar:
        st.markdown("""
        <div class="pv-logo" style="padding:0 0.3rem 1rem;">
            <div class="pv-logo-icon">📈</div> PainVoice
        </div>
        """, unsafe_allow_html=True)
        st.markdown('<div style="font-size:0.72rem; color:var(--pv-muted); font-weight:700; letter-spacing:.06em; padding:0 0.5rem 0.4rem;">MAIN MENU</div>', unsafe_allow_html=True)

        nav_items = [
            ("dashboard", "▦", "Dashboard"),
            ("patient", "👤", "Patients"),
        ]
        for key, icon, label in nav_items:
            is_active = st.session_state.page in (key, "patient_select") if key == "patient" else st.session_state.page == key
            if st.button(f"{icon}   {label}", key=f"nav_{key}", use_container_width=True,
                         type="primary" if is_active else "secondary"):
                go(key if key != "patient" else "patient_select")

        st.markdown('<div style="flex:1;"></div>', unsafe_allow_html=True)
        st.markdown("<br>" * 12, unsafe_allow_html=True)
        st.markdown('<hr class="pv-hr">', unsafe_allow_html=True)
        if st.button("⚙️   Settings", use_container_width=True, type="secondary"):
            pass
        if st.button("⎋   Logout", use_container_width=True, type="secondary", key="sidebar_logout"):
            st.session_state.auth = False
            go("login")


# LOGIN
def page_login():
    _, mid, _ = st.columns([1, 1.1, 1])
    with mid:
        st.markdown("<div style='height:48px;'></div>", unsafe_allow_html=True)
        st.markdown("""
        <div style="text-align:center;">
            <div style="display:flex; align-items:center; justify-content:center; gap:10px;">
                <div class="pv-logo-icon" style="width:40px;height:40px;font-size:1.3rem;">📈</div>
                <span style="font-weight:800; font-size:1.5rem;">PainVoice</span>
            </div>
            <h2 style="margin-top:1.2rem; margin-bottom:0.2rem;">Login Portal</h2>
            <p style="color:var(--pv-sub); font-size:0.88rem;">AI-driven speech analysis for professional pain<br>classification and monitoring.</p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="pv-badge pv-badge-blue">🛡️ SECURE HEALTHCARE ACCESS</div>', unsafe_allow_html=True)
        st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

        with st.form("login_form"):
            st.text_input("EMAIL ADDRESS", placeholder="Enter your clinical ID")
            # c1, c2 = st.columns([1, 1])
            # with c1:
            st.markdown('<div style="font-size:0.96rem; font-weight:500; color:var(--pv-sub);"> PASSWORD</div>', unsafe_allow_html=True)
            # with c2:
            #     st.markdown('<div style="text-align:right; font-size:0.78rem;"><a href="#" style="color:var(--pv-blue); text-decoration:none;">Forgot Password?</a></div>', unsafe_allow_html=True)
            st.text_input("password_label_hidden", type="password", placeholder="••••••••••••", label_visibility="collapsed")
            st.checkbox("Remember this device for 12 hours")
            # st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
            submitted = st.form_submit_button("Sign In   →", use_container_width=True)
            if submitted:
                with st.spinner("Authenticating…"):
                    time.sleep(0.6)
                st.session_state.auth = True
                go("dashboard")

        st.markdown("""
        <div style="display:flex; align-items:center; gap:10px; margin:1.1rem 0 0.8rem;">
            <div style="flex:1; border-top:1px solid var(--pv-border);"></div>
            <div style="font-size:0.72rem; color:var(--pv-muted); font-weight:600;">NEW PRACTITIONER?</div>
            <div style="flex:1; border-top:1px solid var(--pv-border);"></div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Register Account", use_container_width=True, type="secondary"):
            go("register")
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("""
        <div style="text-align:center; margin-top:1rem; font-size:0.72rem; color:var(--pv-muted);">
            Terms of Service &nbsp;·&nbsp; Privacy Policy &nbsp;·&nbsp; © 2024 PainVoice Clinical AI &nbsp;·&nbsp; v1.2.0
        </div>
        """, unsafe_allow_html=True)


# REGISTER
def page_register():
    if st.button("←  Back to Login", type="secondary"):
        go("login")
    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

    left, right = st.columns([1, 1.3], gap="medium")
    with left:
        st.markdown("""
        <div style="background:linear-gradient(160deg,#1C97D6,#5AC8F2); border-radius:16px; padding:2.2rem 1.8rem; height:600px; color:white; display:flex; flex-direction:column;">
            <div style="display:flex; align-items:center; gap:8px; margin-bottom:2rem;">
                <div style="width:30px;height:30px;border-radius:8px;background:rgba(255,255,255,0.25); display:flex;align-items:center;justify-content:center;">📈</div>
                <span style="font-weight:800; font-size:1.05rem;">PainVoice</span>
            </div>
            <h2 style="color:white; font-size:1.7rem; line-height:1.25;">Empowering Medicine with AI Sound Metrics.</h2>
            <p style="color:rgba(255,255,255,0.85); font-size:0.9rem; margin-top:0.8rem;">
                Join thousands of healthcare professionals using speech-based biomarkers for objective pain assessment.
            </p>
            <div style="flex:1;"></div>
            <div style="font-size:0.72rem; color:rgba(255,255,255,0.7);">
                Terms of Service &nbsp;·&nbsp; Privacy Policy &nbsp;·&nbsp; Security Standards
            </div>
        </div>
        """, unsafe_allow_html=True)

    with right:
        st.markdown('<h2 style="margin-bottom:0.1rem;">Create Account</h2>', unsafe_allow_html=True)
        st.markdown('<p style="color:var(--pv-sub); font-size:0.88rem; margin-bottom:1rem;">Register your profile to start monitoring.</p>', unsafe_allow_html=True)

        step = st.session_state.reg_step
        pct = 50 if step == 1 else 100
        st.markdown(f"""
        <div style="display:flex; gap:6px; margin-bottom:1.4rem;">
            <div style="flex:1; height:4px; border-radius:4px; background:var(--pv-blue);"></div>
            <div style="flex:1; height:4px; border-radius:4px; background:{'var(--pv-blue)' if step==2 else 'var(--pv-border)'};"></div>
        </div>
        """, unsafe_allow_html=True)

        if step == 1:
            c1, c2 = st.columns(2)
            with c1:
                st.text_input("First Name", placeholder="John")
            with c2:
                st.text_input("Last Name", placeholder="Doe")

            email_c1, email_c2 = st.columns([3, 1])
            with email_c1:
                st.markdown('<div style="font-size:0.82rem; color:var(--pv-sub); font-weight:500;">Professional Email</div>', unsafe_allow_html=True)
            email = st.text_input("email_hidden", placeholder="dr.john@medical.com", label_visibility="collapsed")
            if email:
                st.markdown('<span class="pv-badge pv-badge-green">✓ Available</span>', unsafe_allow_html=True)

            st.markdown('<div style="font-size:0.82rem; color:var(--pv-blue-dark); font-weight:600; margin-top:0.4rem;">💳 National Provider Identifier (NPI)</div>', unsafe_allow_html=True)
            st.text_input("npi_hidden", placeholder="10-digit NPI Number", label_visibility="collapsed")
            st.markdown('<div style="font-size:0.74rem; color:var(--pv-muted); margin-top:-0.6rem;">Verified against National Plan and Provider Enumeration System.</div>', unsafe_allow_html=True)

            st.text_input("Clinical Specialty", placeholder="e.g. Chronic Pain Management")

            st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
            if st.button("Continue to Security  →", use_container_width=True):
                st.session_state.reg_step = 2
                st.rerun()

            st.markdown(f"""
            <div style="text-align:center; margin-top:1rem; font-size:0.85rem; color:var(--pv-sub);">
                Already have a clinical account? <a href="#" style="color:var(--pv-blue); font-weight:600; text-decoration:none;">Login here</a>
            </div>
            """, unsafe_allow_html=True)

        else:
            st.text_input("Set Password", type="password", placeholder="Minimum 8 characters")
            st.text_input("Confirm Password", type="password", placeholder="Re-enter password")
            st.selectbox("Two-Factor Authentication", ["SMS Verification", "Authenticator App", "Email Verification"])
            st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            with c1:
                if st.button("← Back", use_container_width=True, type="secondary"):
                    st.session_state.reg_step = 1
                    st.rerun()
            with c2:
                if st.button("✓ Create Account", use_container_width=True):
                    st.session_state.auth = True
                    st.session_state.reg_step = 1
                    go("dashboard")


# MAIN DASHBOARD
def page_dashboard():
    topbar()
    st.markdown('<h2 style="margin-bottom:0.1rem;">Main Dashboard</h2>', unsafe_allow_html=True)
    high_alert_count = sum(1 for p in PATIENTS if p["last_pain_level"] and p["last_pain_level"] >= 7)
    st.markdown(
        f'<p style="color:var(--pv-sub); font-size:0.9rem; margin-bottom:1.2rem;">'
        f'Welcome back. You have {high_alert_count} patients with high pain alerts today. '
        f'AI classification models are synchronized and active.</p>',
        unsafe_allow_html=True,
    )

    # KPI row
    k = DASHBOARD_KPIS
    c1, c2 = st.columns(2)
    kpi_defs = [
        (c1, "👥", "ACTIVE PATIENTS", k["active_patients"]["value"], k["active_patients"]["delta"], k["active_patients"].get("trend")),
        (c2, "🕐", "TODAY'S SESSIONS", k["todays_sessions"]["value"], k["todays_sessions"]["delta"], k["todays_sessions"].get("trend")),
        # (c3, "📄", "COMPLETED REPORTS", k["completed_reports"]["value"], k["completed_reports"]["delta"], None),
        # (c4, "📈", "SYSTEM HEALTH", k["system_health"]["value"], k["system_health"]["delta"], None),
    ]
    for col, icon, label, value, delta, trend in kpi_defs:
        with col:
            trend_html = f'<span style="color:var(--pv-green); font-size:0.78rem; float:right;">↗ {trend}</span>' if trend else ""
            st.markdown(f"""
            <div class="pv-kpi">
                <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                    <div class="pv-kpi-icon">{icon}</div>
                    {trend_html}
                </div>
                <div class="pv-kpi-label">{label}</div>
                <div class="pv-kpi-value">{value}</div>
                <div class="pv-kpi-delta" style="color:var(--pv-muted);">{delta}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

    # Search + actions row
    sc1, sc2 = st.columns([3.2, 1])
    with sc1:
        search = st.text_input("search", placeholder="🔍  Search by patient name, ID, or clinical condition...", label_visibility="collapsed")
    with sc2:
        if st.button("⊕  Create New Patient", use_container_width=True, key="dash_create_patient"):
            create_patient_dialog()

    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

    # Recent patients header
    # hc1, hc2 = st.columns([3, 1])
    # with hc1:
    st.markdown(f'<div style="font-weight:700; font-size:1.05rem;">Recent Patients <span style="color:var(--pv-muted); font-weight:500; font-size:0.85rem;">{len(PATIENTS)} TOTAL</span></div>', unsafe_allow_html=True)
    # with hc2:
    #     st.markdown('<div style="text-align:right; color:var(--pv-blue); font-weight:600; font-size:0.85rem;">View All Patients →</div>', unsafe_allow_html=True)

    st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)

    # Patient cards grid (3 columns)
    filtered = [p for p in PATIENTS if not search or search.lower() in (p["name"] + p["id"] + p["condition"]).lower()]
    cols = st.columns(3)
    for i, p in enumerate(filtered[:6]):
        with cols[i % 3]:
            level = p["last_pain_level"]
            if level is not None and level >= 7:
                badge = f'<span class="pv-badge pv-badge-red">Lv {level}</span>'
            elif level is not None and level >= 4:
                badge = f'<span class="pv-badge pv-badge-amber">Lv {level}</span>'
            elif level is not None:
                badge = f'<span class="pv-badge pv-badge-green">Lv {level}</span>'
            else:
                badge = '<span class="pv-badge pv-badge-gray">No Data</span>'
            last_visit = p["sessions"][0]["date"] if p["sessions"] else "No visits yet"
            initials = "".join([n[0] for n in p["name"].split()[:2]])
            st.markdown(f"""
            <div class="pv-card">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div style="display:flex; align-items:center; gap:10px;">
                        <div class="pv-avatar" style="background:{p['avatar_color']};">{initials}</div>
                        <div>
                            <div style="font-weight:700; font-size:0.92rem;">{p['name']}</div>
                            <div style="font-size:0.74rem; color:var(--pv-muted);">{p['id']} · Age {p['age']}</div>
                        </div>
                    </div>
                </div>
                <div style="display:flex; justify-content:space-between; margin-top:0.9rem;">
                    <div>
                        <div style="font-size:0.68rem; color:var(--pv-muted); text-transform:uppercase; letter-spacing:.04em;">Last Pain Level</div>
                        {badge}
                    </div>
                    <div style="text-align:right;">
                        <div style="font-size:0.68rem; color:var(--pv-muted); text-transform:uppercase; letter-spacing:.04em;">Last Visit</div>
                        <div style="font-size:0.78rem; font-weight:600;">{last_visit}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            bc1, bc2 = st.columns([3, 1])
            with bc1:
                if st.button("View File", key=f"view_{p['id']}_{i}", use_container_width=True, type="secondary"):
                    st.session_state.active_patient_idx = PATIENTS.index(p)
                    go("patient")
            with bc2:
                if st.button("📈", key=f"chart_{p['id']}_{i}", use_container_width=True, type="secondary"):
                    st.session_state.active_patient_idx = PATIENTS.index(p)
                    go("treatment_effectiveness")

    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)

    # System Insights + Recent Activity
    ic1, ic2 = st.columns([1.4, 1])
    with ic1:
        st.markdown('<div class="pv-section-title">System Insights</div>', unsafe_allow_html=True)
        st.markdown('<div class="pv-section-sub">Automated clinical alerts and model suggestions.</div>', unsafe_allow_html=True)
        for insight in SYSTEM_INSIGHTS:
            st.markdown(f"""
            <div style="background:var(--pv-blue-bg); border-radius:10px; padding:0.9rem 1.1rem; margin-bottom:0.6rem; display:flex; gap:10px;">
                <div style="font-size:1.1rem;">{insight['icon']}</div>
                <div>
                    <div style="font-weight:700; font-size:0.86rem;">{insight['title']}</div>
                    <div style="font-size:0.8rem; color:var(--pv-sub); margin-top:2px;">{insight['body']}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with ic2:
        st.markdown('<div class="pv-section-title">Recent Session Activity</div>', unsafe_allow_html=True)
        for act in RECENT_ACTIVITY:
            level_html = f'<span class="pv-badge pv-badge-{"red" if act["level"] and act["level"]>=7 else "amber" if act["level"] else "gray"}" style="margin-top:3px;">Pain Level: {act["level"]}</span>' if act["level"] else ""
            st.markdown(f"""
            <div style="padding:0.5rem 0; border-bottom:1px solid var(--pv-border);">
                <div style="font-size:0.74rem; color:var(--pv-muted);">{act['time']}</div>
                <div style="font-size:0.85rem;"><b>{act['name']}</b> - {act['action']}</div>
                {level_html}
            </div>
            """, unsafe_allow_html=True)
        # st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
        # st.button("View Full Audit Log", use_container_width=True, type="secondary", key="audit_log_btn")
        # st.markdown('</div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────
# PATIENT SELECT (simple list to choose which patient record to open)
# ─────────────────────────────────────────────────────────────────────────
def page_patient_select():
    topbar(back=True)
    st.markdown('<h2 style="margin-bottom:0.1rem;">Patient Dashboard</h2>', unsafe_allow_html=True)
    hcol1, hcol2 = st.columns([3, 1])
    with hcol1:
        st.markdown('<h2 style="margin-bottom:0.8rem;">Patients</h2>', unsafe_allow_html=True)
    with hcol2:
        if st.button("⊕  New Patient", use_container_width=True, key="patients_create_btn"):
            create_patient_dialog()
    for i, p in enumerate(PATIENTS):
        initials = "".join([n[0] for n in p["name"].split()[:2]])
        level = p["last_pain_level"]
        if level is not None and level >= 7:
            badge = f'<span class="pv-badge pv-badge-red">Lv {level}</span>'
        elif level is not None and level >= 4:
            badge = f'<span class="pv-badge pv-badge-amber">Lv {level}</span>'
        elif level is not None:
            badge = f'<span class="pv-badge pv-badge-green">Lv {level}</span>'
        else:
            badge = '<span class="pv-badge pv-badge-gray">No Data</span>'

        c1, c2, c3 = st.columns([0.5, 3, 1])
        with c1:
            st.markdown(f'<div class="pv-avatar" style="background:{p["avatar_color"]}; margin-top:6px;">{initials}</div>', unsafe_allow_html=True)
        with c2:
            st.markdown(f"""
            <div style="padding-top:2px;">
                <div style="font-weight:700; font-size:0.92rem;">{p['name']} <span style="font-weight:500; color:var(--pv-muted); font-size:0.78rem;">· {p['id']}</span></div>
                <div style="font-size:0.8rem; color:var(--pv-sub);">{p['condition']}</div>
            </div>
            """, unsafe_allow_html=True)
        with c3:
            st.markdown(f'<div style="text-align:right; margin-top:4px;">{badge}</div>', unsafe_allow_html=True)
            if st.button("Open File →", key=f"open_{p['id']}_{i}", use_container_width=True, type="secondary"):
                st.session_state.active_patient_idx = i
                st.session_state.effectiveness_report_pdf = None
                st.session_state.medical_report_pdf = None
                st.session_state.last_result = None
                st.session_state.last_classification = None
                st.session_state.show_spectrogram = False
                go("patient")
        st.markdown('<hr class="pv-hr">', unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────
# PATIENT RECORD DASHBOARD
# ─────────────────────────────────────────────────────────────────────────
def page_patient():
    topbar(back=True)
    st.markdown('<h2 style="margin-bottom:0.1rem;">Patient Dashboard</h2>', unsafe_allow_html=True)
    p = current_patient()
    initials = "".join([n[0] for n in p["name"].split()[:2]])

    st.markdown(f"""
    <div class="pv-card" style="border-left:3px solid var(--pv-blue); display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:1rem;">
        <div style="display:flex; align-items:center; gap:12px;">
            <div class="pv-avatar" style="width:48px; height:48px; font-size:1.1rem; background:{p['avatar_color']};">{initials}</div>
            <div>
                <div style="font-weight:800; font-size:1.15rem;">{p['name']} <span class="pv-badge pv-badge-blue" style="margin-left:6px; vertical-align:middle;">{p['case']}</span></div>
                <div style="font-size:0.85rem; color:var(--pv-sub);">{p['condition']}</div>
                <div style="font-size:0.74rem; color:var(--pv-muted); margin-top:2px;">📍 ID: {p['id']} &nbsp;&nbsp; 📅 DOB: {p['dob']}</div>
            </div>
        </div>
        <div style="display:flex; gap:1.6rem; background:#F9FAFA; border-radius:10px; padding:0.7rem 1.2rem;">
            <div><div style="font-size:0.68rem; color:var(--pv-muted); text-transform:uppercase;">Age</div><div style="font-weight:700; font-size:0.88rem;">{p['age']} Years</div></div>
            <div><div style="font-size:0.68rem; color:var(--pv-muted); text-transform:uppercase;">Gender</div><div style="font-weight:700; font-size:0.88rem;">{p['gender']}</div></div>
            <div><div style="font-size:0.68rem; color:var(--pv-muted); text-transform:uppercase;">Blood Type</div><div style="font-weight:700; font-size:0.88rem;">{p['blood_type']}</div></div>
            <div><div style="font-size:0.68rem; color:var(--pv-muted); text-transform:uppercase;">Status</div><div style="font-weight:700; font-size:0.88rem;">{p['status_label']}</div></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    col_l, col_r = st.columns([1.5, 1], gap="medium")

    with col_l:
        sh1, sh2 = st.columns([3, 1])
        with sh1:
            st.markdown('<div class="pv-section-title">Session History</div>', unsafe_allow_html=True)
            st.markdown('<div class="pv-section-sub">Chronological log of AI-assisted pain assessments</div>', unsafe_allow_html=True)
        with sh2:
            st.markdown('<div style="text-align:right;"><span class="pv-badge pv-badge-gray">🕐 Updated: Just now</span></div>', unsafe_allow_html=True)

        if not p["sessions"]:
            st.markdown("""
            <div style="text-align:center; padding:3rem 1rem; color:var(--pv-blue);">
                No Session Found
            </div>
            """, unsafe_allow_html=True)
        else:
            for s in p["sessions"]:
                level = s["level"]
                cls_badge = "pv-badge-red" if "High" in s["classification"] else ("pv-badge-amber" if "Moderate" in s["classification"] else "pv-badge-green")
                st.markdown(f"""
                <div style="border:1px solid var(--pv-border); border-radius:10px; padding:0.8rem 1rem; margin-bottom:0.6rem; display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <div style="font-weight:700; font-size:0.85rem;">{s['date']}</div>
                        <div style="font-size:0.76rem; color:var(--pv-muted);">{s['time']}</div>
                    </div>
                    <div>
                        <div style="font-size:0.7rem; color:var(--pv-muted); text-transform:uppercase;">AI Classification</div>
                        <span class="pv-badge {cls_badge}">{s['classification']} (Lvl {level})</span>
                    </div>
                    <div>
                        <div style="font-size:0.7rem; color:var(--pv-muted); text-transform:uppercase;">Confidence</div>
                        <div style="font-size:0.8rem; font-weight:600;">{s['confidence']}%</div>
                    </div>
                    <div style="text-align:right; font-size:0.74rem; color:var(--pv-muted);">
                        🎙️ {s['duration']}<br>Voice Analysis ID: {s['voice_id']}
                    </div>
                    <div style="font-size:1.1rem; color:var(--pv-muted);">›</div>
                </div>
                """, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        ac1, ac2 = st.columns(2)
        with ac1:
            st.markdown(f"""
            <div class="pv-card">
                <div style="font-weight:700; font-size:0.85rem;">⚠️ Critical Allergies</div>
                <div style="margin-top:0.5rem; display:flex; gap:6px; flex-wrap:wrap;">
                    {''.join([f'<span class="pv-badge pv-badge-red">{a}</span>' for a in p['allergies']])}
                </div>
            </div>
            """, unsafe_allow_html=True)
        with ac2:
            st.markdown(f"""
            <div class="pv-card">
                <div style="font-weight:700; font-size:0.85rem;">ℹ️ Current Care Plan</div>
                <div style="margin-top:0.5rem; font-size:0.85rem; font-weight:600;">{p['care_plan']}</div>
                <div style="font-size:0.76rem; color:var(--pv-muted);">Next titration scheduled: {p['next_titration']}</div>
            </div>
            """, unsafe_allow_html=True)

    with col_r:
        st.markdown("""
        <div style="background:var(--pv-blue-bg); border-radius:16px; padding:1.3rem 1.4rem; margin-bottom:1rem;">
            <div style="font-weight:700; color:var(--pv-blue-dark); font-size:0.95rem;">Assessment Actions</div>
            <div style="font-size:0.8rem; color:var(--pv-blue-dark); opacity:0.85; margin-bottom:0.9rem;">Begin assessment or export documentation</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("⊕  Start New Session", use_container_width=True, key="start_session_btn"):
            st.session_state.recording_state = "ready"
            st.session_state.last_result = None
            st.session_state.last_classification = None
            st.session_state.audio_bytes = None
            st.session_state.voice_error = None
            st.session_state.show_spectrogram = False
            st.session_state.report_generated = False
            st.session_state.medical_report_pdf = None
            go("voice_capture")
        if p["sessions"]:
            if st.button("📈  View Effectiveness Metrics", use_container_width=True, type="secondary", key="view_eff_btn"):
                go("treatment_effectiveness")

        if p["sessions"]:
            st.markdown(f"""
            <div class="pv-card" style="margin-top:1rem;">
                <div class="pv-section-title" style="font-size:0.9rem;">📈 Pain Trend Summary</div>
                <div style="display:flex; justify-content:space-between; align-items:baseline; margin-top:0.4rem;">
                    <span style="font-size:0.76rem; color:var(--pv-muted); text-transform:uppercase;">Average Pain (30D)</span>
                    <span style="font-size:1.3rem; font-weight:800;">{p['avg_pain_30d']}</span>
                </div>
                <div style="display:flex; gap:3px; margin:0.6rem 0;">
                    {''.join([f'<div style="flex:1; height:18px; border-radius:3px; background:{"var(--pv-red-soft)" if s["level"]>=7 else "#D6EEFB"};"></div>' for s in (p['sessions'][:8] or [{}]*8)])}
                </div>
                <div class="pv-hr"></div>
                <div style="display:flex; justify-content:space-between; font-size:0.82rem; margin-bottom:0.4rem;">
                    <span style="color:var(--pv-sub);">Adherence Rate</span><b>{p['adherence']}%</b>
                </div>
                <div style="display:flex; justify-content:space-between; font-size:0.82rem;">
                    <span style="color:var(--pv-sub);">AI Accuracy Avg</span><b style="color:var(--pv-blue-dark);">{p['ai_accuracy']}%</b>
                </div>
                <div style="font-size:0.74rem; color:var(--pv-muted); margin-top:0.6rem; font-style:italic;">
                    Trend indicates localized fluctuations. Recommend reviewing effectiveness metrics before titration.
                </div>
            </div>
            """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────
# VOICE CAPTURE
# ─────────────────────────────────────────────────────────────────────────
def render_spectrogram(spec: dict, key_suffix: str = ""):
    """Render a log-Mel spectrogram (from a GRU-Mixer analysis result) as a
    Plotly heatmap — this is literally what the model's input looks like."""
    import plotly.graph_objects as go
    fig = go.Figure(data=go.Heatmap(
        z=spec["db"], x=spec["time_axis"], y=spec["mel_axis"],
        colorscale="Blues", reversescale=True,
        colorbar=dict(title="dB", thickness=14),
    ))
    fig.update_layout(
        height=280, margin=dict(l=10, r=10, t=10, b=10),
        xaxis_title="Time (s)", yaxis_title="Mel band",
        plot_bgcolor="white", paper_bgcolor="white",
        font=dict(family="Plus Jakarta Sans, sans-serif", size=11, color="#5B6470"),
    )
    st.plotly_chart(fig, use_container_width=True, key=f"spectrogram_{key_suffix}")
    st.markdown(
        '<div style="font-size:0.76rem; color:var(--pv-muted); margin-top:-0.4rem;">'
        "64-band log-Mel spectrogram — this is the exact input the GRU-Mixer model receives.</div>",
        unsafe_allow_html=True,
    )


def page_voice_capture():
    topbar(back=True)
    p = current_patient()

    h1, h2 = st.columns([3, 1.4])
    with h1:
        st.markdown('<h2 style="margin-bottom:0;">Pain Level Monitoring</h2>', unsafe_allow_html=True)
        st.markdown(f'<div style="color:var(--pv-muted); font-size:0.84rem;">Session ID: {st.session_state.session_id}</div>', unsafe_allow_html=True)
    with h2:
        st.markdown(f"""
        <div style="background:#FFFFFF; border:1px solid var(--pv-border); border-radius:10px; padding:0.6rem 1rem; text-align:right;">
            <div style="font-weight:700; font-size:0.85rem;">{p['name']}</div>
            <div style="font-size:0.74rem; color:var(--pv-muted);">{p['id']} · {p['age']}y {p['gender']} &nbsp; <span class="pv-badge pv-badge-blue">New Assessment</span></div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
    _, mid, _ = st.columns([0.5, 2, 0.5])
    with mid:
        # st.markdown('<div class="pv-card" style="text-align:center; padding:2.2rem 1.6rem;">', unsafe_allow_html=True)

        state = st.session_state.recording_state
        if state == "ready":
            st.markdown("""
            <div style="font-size:1.8rem;">📈</div>
            <div style="font-weight:800; font-size:1.2rem; margin-top:0.4rem;">Voice Capture Ready</div>
            <div style="color:var(--pv-sub); font-size:0.85rem; margin-top:0.2rem;">Instruct the patient to describe their current pain sensations clearly for 5–10 seconds, then record below.</div>
            <div class="pv-hr"></div>
            """, unsafe_allow_html=True)

            if st.session_state.voice_error:
                st.error(st.session_state.voice_error)
                st.session_state.voice_error = None

            if p.get("is_demo"):
                st.markdown(
                    '<div style="font-size:0.82rem; font-weight:600; color:var(--pv-sub); margin-bottom:0.4rem;">'
                    "🧪 Demo Patient — quick-test with a sample recording:</div>",
                    unsafe_allow_html=True,
                )
                d1, d2, d3 = st.columns(3)
                for col, (icon, label_text, path, target_label, target_conf) in zip((d1, d2, d3), DEMO_SAMPLES):
                    with col:
                        if st.button(f"{icon} {label_text}", use_container_width=True, key=f"demo_sample_{label_text}"):
                            if os.path.exists(path):
                                with open(path, "rb") as f:
                                    audio_bytes = f.read()
                                try:
                                    with st.spinner("Loading sample and computing biomarkers…"):
                                        result = PainVoiceAnalyzer.get().analyze_scripted(audio_bytes, target_label, target_conf)
                                        session_entry = record_voice_session(current_patient(), result)
                                        result["recorded_at"] = session_entry["time"]
                                        time.sleep(1.6)  # brief buffer so it doesn't feel instant
                                    st.session_state.audio_bytes = audio_bytes
                                    st.session_state.last_result = result
                                    st.session_state.last_classification = "Low" if result["label"] == "Low Pain" else "High"
                                    st.session_state.recording_state = "done"
                                    st.rerun()
                                except Exception as exc:
                                    st.session_state.voice_error = f"Couldn't process that sample ({exc})."
                                    st.rerun()
                            else:
                                st.session_state.voice_error = f"Sample file not found: {path}"
                                st.rerun()
                st.markdown('<div class="pv-hr"></div>', unsafe_allow_html=True)
                st.markdown(
                    '<div style="font-size:0.8rem; color:var(--pv-muted); text-align:center; margin-bottom:0.6rem;">'
                    "— or record a live sample below —</div>",
                    unsafe_allow_html=True,
                )

            with st.expander("📝  Show an example prompt for the patient"):
                st.markdown("""
                <div style="font-size:0.82rem; color:var(--pv-sub); margin-bottom:0.5rem;">
                    Ask the patient to describe, in their own words: what the pain feels like, where it's
                    located, how intense it is right now (0–10), and what makes it better or worse.
                </div>
                <div style="background:var(--pv-blue-bg); border-radius:10px; padding:0.9rem 1.1rem; font-size:0.85rem; font-style:italic; color:var(--pv-ink);">
                    "Right now my pain is a dull, constant ache in my lower back, around a 6 out of 10.
                    It gets sharper, almost like a stabbing feeling, when I try to stand up or bend forward.
                    It's a bit worse than yesterday, and I feel stiff in the morning for about half an hour
                    before it loosens up. Sitting for a long time makes it worse too."
                </div>
                """, unsafe_allow_html=True)

            audio_value = st.audio_input(
                "Record patient voice sample",
                sample_rate=VOICE_SAMPLE_RATE,
                key="voice_audio_input",
                label_visibility="collapsed",
            )
            if audio_value is not None:
                st.markdown('<div style="font-size:0.82rem; color:var(--pv-green); text-align:center; margin-top:0.5rem;">✓ Recording captured — ready to analyze.</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div style="font-size:0.8rem; color:var(--pv-muted); text-align:center; margin-top:0.5rem;">ℹ️ Ensure patient is roughly 12 inches from the microphone.</div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

            b1, b2 = st.columns(2)
            with b1:
                if st.button("✕  Back to Record", use_container_width=True, type="secondary"):
                    go("patient")
            with b2:
                if st.button("🎙️  Analyze Recording", use_container_width=True, disabled=audio_value is None):
                    st.session_state.audio_bytes = audio_value.getvalue()
                    st.session_state.recording_state = "recording"
                    st.rerun()

        elif state == "recording":
            st.markdown("""
            <div style="font-size:1.8rem;">🔴</div>
            <div style="font-weight:800; font-size:1.2rem; margin-top:0.4rem;">Analyzing…</div>
            <div style="color:var(--pv-sub); font-size:0.85rem; margin-top:0.2rem;">Running the recording through the GRU-Mixer voice model.</div>
            <div class="pv-hr"></div>
            """, unsafe_allow_html=True)
            st.markdown("""
            <div style="width:140px; height:140px; border-radius:50%; border:2px solid var(--pv-blue); display:flex; align-items:center; justify-content:center; margin:1.4rem auto; flex-direction:column; animation:pulse 1.4s infinite;">
                <div style="font-size:1.6rem;">🎙️</div>
                <div style="font-size:0.8rem; color:var(--pv-blue); margin-top:4px; font-weight:600;">Analyzing</div>
            </div>
            <style>@keyframes pulse { 0% {box-shadow:0 0 0 0 rgba(37,175,244,0.3);} 70% {box-shadow:0 0 0 14px rgba(37,175,244,0);} 100% {box-shadow:0 0 0 0 rgba(37,175,244,0);} }</style>
            """, unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

            with st.spinner("Extracting log-Mel spectrogram and running the GRU-Mixer model…"):
                try:
                    result = PainVoiceAnalyzer.get().analyze(st.session_state.audio_bytes)
                    session_entry = record_voice_session(current_patient(), result)
                    result["recorded_at"] = session_entry["time"]
                    time.sleep(1.8)  # brief buffer so analysis doesn't feel instant
                    st.session_state.last_result = result
                    st.session_state.last_classification = "Low" if result["label"] == "Low Pain" else "High"
                    st.session_state.recording_state = "done"
                except Exception as exc:
                    st.session_state.voice_error = f"Couldn't analyze that recording ({exc}). Please try recording again."
                    st.session_state.audio_bytes = None
                    st.session_state.recording_state = "ready"
            st.rerun()

        elif state == "done":
            r = st.session_state.last_result or {}
            st.markdown(f"""
            <div style="font-size:1.8rem; color:var(--pv-green);">✓</div>
            <div style="font-weight:800; font-size:1.2rem; margin-top:0.4rem;">Capture Complete</div>
            <div style="color:var(--pv-sub); font-size:0.85rem; margin-top:0.2rem;">
                GRU-Mixer classification: <b>{r.get('label', '—')}</b> ({r.get('confidence', '—')}% confidence)
            </div>
            """, unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
            r1, r2 = st.columns(2)
            with r1:
                if st.button("🔄  Record Again", use_container_width=True, type="secondary"):
                    st.session_state.recording_state = "ready"
                    st.session_state.audio_bytes = None
                    st.rerun()
            with r2:
                if st.button("View Result  →", use_container_width=True):
                    go("pain_result")

            if r.get("spectrogram"):
                with st.expander("🔬  View Acoustic Spectrogram"):
                    render_spectrogram(r["spectrogram"], key_suffix="voicecap")

        r = st.session_state.last_result
        if state == "done" and r:
            if r.get("is_scripted_demo"):
                weights_note = "🧪 Scripted demo result — not live model inference"
            elif r.get("is_trained"):
                weights_note = "✓ Trained GRU-Mixer weights loaded"
            else:
                weights_note = "⚠️ Demo weights (untrained — see gru_mixer.py)"
            footer_html = f"🕐 Duration: {r['duration_sec']}s &nbsp;&nbsp;·&nbsp;&nbsp; {weights_note}"
        else:
            footer_html = "🕐 Est. Duration: ~10s &nbsp;&nbsp;·&nbsp;&nbsp; 🧠 GRU-Mixer voice analysis"
        st.markdown(f"""
        <div style="text-align:center; margin-top:1rem; font-size:0.78rem; color:var(--pv-muted);">
            {footer_html}
        </div>
        """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────
# PAIN RESULT (Low / High classification display)
# ─────────────────────────────────────────────────────────────────────────
def page_pain_result():
    topbar(back=True)
    p = current_patient()
    is_high = st.session_state.last_classification != "Low"
    initials = "".join([n[0] for n in p["name"].split()[:2]])

    st.markdown(f"""
    <div style="display:flex; justify-content:space-between; align-items:center;">
        <div style="display:flex; align-items:center; gap:10px;">
            <div class="pv-avatar" style="background:{p['avatar_color']};">{initials}</div>
            <div>
                <div style="font-weight:700;">{p['name']}</div>
                <div style="font-size:0.76rem; color:var(--pv-muted);">ID: {p['id']} · {p['gender']} · {p['age']} yrs</div>
            </div>
        </div>
        <span class="pv-badge pv-badge-gray">Active Session: {datetime.now().strftime('%d-%m-%Y')}</span>
    </div>
    <div class="pv-hr"></div>
    """, unsafe_allow_html=True)

    r = st.session_state.last_result
    if r:
        level_num = r["level"]
        confidence = r["confidence"]
        biomarkers = r["biomarkers"]
        label = r["label"]
    else:
        level_num = 8 if is_high else 3
        confidence = 92
        biomarkers = ACOUSTIC_BIOMARKERS_HIGH if is_high else ACOUSTIC_BIOMARKERS_LOW
        label = "High Pain" if is_high else "Low Pain"
    color_bg, color_border, accent, badge_class = classification_colors(label)
    notes = AI_NOTES_HIGH if is_high else AI_NOTES_LOW
    pain_word = {"Low Pain": "low", "Moderate Pain": "moderate", "High Pain": "high"}.get(label, "low")
    strain_word = {"Low Pain": "minimal", "Moderate Pain": "moderate", "High Pain": "significant"}.get(label, "minimal")

    st.markdown(f"""
    <div style="background:{color_bg}; border:1px solid {color_border}; border-radius:16px; padding:1.4rem 1.6rem; display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
        <div>
            <span class="pv-badge {badge_class}">AI Classification Result</span>
            <div style="font-size:2.1rem; font-weight:800; margin-top:0.5rem;">{label} / Level {level_num}</div>
            <div style="color:var(--pv-sub); font-size:0.88rem; margin-top:0.3rem; max-width:480px;">
                Speech patterns indicate {pain_word} pain autonomic pain responses.
                Vocal markers suggest {strain_word} physiological strain consistent with Level {level_num} intensity.
            </div>
        </div>
        <div style="width:90px; height:90px; border-radius:50%; border:7px solid {accent}; display:flex; flex-direction:column; align-items:center; justify-content:center; background:white;">
            <div style="font-weight:800; font-size:1.05rem;">{confidence}%</div>
            <div style="font-size:0.6rem; color:var(--pv-muted); text-transform:uppercase;">Confidence</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    bc1, bc2 = st.columns([1.5, 1])
    with bc1:
        h1, h2 = st.columns([3, 1.5])
        with h1:
            st.markdown('<div class="pv-section-title" style="font-size:1.28rem;">📈 Acoustic Biomarkers</div>', unsafe_allow_html=True)
        with h2:
            if st.button("📊 View Spectrogram", key="toggle_spectrogram_btn", type="secondary", use_container_width=True):
                st.session_state.show_spectrogram = not st.session_state.get("show_spectrogram", False)
        cols = st.columns(3)
        for col, bm in zip(cols, biomarkers):
            with col:
                st.markdown(f"""
                <div class="pv-card" style="padding:1rem;">
                    <div style="font-size:0.78rem; color:var(--pv-muted);">{bm['label']}</div>
                    <div style="font-weight:800; font-size:1.25rem; margin:2px 0;">{bm['value']}</div>
                    <div style="font-size:0.74rem; color:var(--pv-sub);">{bm['note']}</div>
                </div>
                """, unsafe_allow_html=True)

        if st.session_state.get("show_spectrogram"):
            if r and r.get("spectrogram"):
                st.markdown('<div class="pv-section-title" style="font-size:1.28rem;">📊 View Spectrogram</div>', unsafe_allow_html=True)
                render_spectrogram(r["spectrogram"], key_suffix="painresult")
                st.markdown('</div>', unsafe_allow_html=True)
            else:
                st.info("No live recording this session — record a voice sample to view its spectrogram.")

    with bc2:
        st.markdown('<div class="pv-section-title" style="font-size:0.92rem;">ℹ️ Clinical Context</div>', unsafe_allow_html=True)
        st.markdown('<div style="font-size:0.78rem; color:var(--pv-muted); margin-bottom:0.6rem;">AI Interpretation Notes — Automated diagnostic observations</div>', unsafe_allow_html=True)
        for note in notes:
            st.markdown(f"""
            <div style="margin-bottom:0.7rem;">
                <span style="font-weight:700; font-size:0.82rem;">{note['label']}:</span>
                <span style="font-size:0.82rem; color:var(--pv-sub);"> {note['body']}</span>
            </div>
            """, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
    st.markdown("""
    <div style="text-align:center; margin-bottom:0.6rem;">
        <div style="font-weight:700; font-size:1rem;">Clinical Decisions</div>
        <div style="font-size:0.82rem; color:var(--pv-muted);">Select the next phase of treatment based on the AI analysis above.</div>
    </div>
    """, unsafe_allow_html=True)

    d1, d2, d3 = st.columns(3)
    with d1:
        track_label = "💊  Track Treatment Plan" if is_high else "💊  Update Treatment Plan"
        if st.button(track_label, use_container_width=True, key="cd_track"):
            go("treatment_plan")
    with d2:
        if st.button("📄  Generate Medical Report", use_container_width=True, type="secondary", key="cd_report"):
            go("medical_report")
    with d3:
        if st.button("✓  End Session", use_container_width=True, type="secondary", key="cd_end"):
            go("patient")


# ─────────────────────────────────────────────────────────────────────────
# PAIN TRACKING & TREATMENT PLAN  (+ Send Alert modal)
# ─────────────────────────────────────────────────────────────────────────
def page_treatment_plan():
    topbar(back=True)
    st.markdown('<h2 style="margin-bottom:0.1rem;">Treatment Plan</h2>', unsafe_allow_html=True)
    p = current_patient()
    is_high = st.session_state.last_classification != "Low"
    r = st.session_state.last_result
    confidence = r["confidence"] if r else 87.4
    st.markdown(f'<p style="color:var(--pv-sub); font-size:0.88rem; margin-bottom:1rem;">Define the follow-up protocol and monitoring schedule for Patient: <b>{p["name"]}</b> (DOB: {p["dob"]})</p>', unsafe_allow_html=True)

    if st.session_state.show_alert_modal:
        render_alert_modal(p, is_high)
        return

    # ── Dynamic assessment note, built from the actual GRU-Mixer result —
    # no hardcoded clinical text. Falls back to a neutral placeholder if
    # this session hasn't had a live voice assessment yet. ──
    if r:
        biomarker_notes = [b["note"].rstrip(".") for b in r.get("biomarkers", [])[:2]]
        joined_notes = "; ".join(n[0].lower() + n[1:] for n in biomarker_notes) if biomarker_notes else "no notable acoustic anomalies"
        clinician_note = (
            f'Voice analysis ({r["label"]}, {r["confidence"]}% confidence) found {joined_notes}. '
            f'Primary concern on file: {p["condition"]}.'
        )
        recorded_line = f'Recorded: {r.get("recorded_at", "—")}'
    else:
        clinician_note = f'No live voice assessment recorded yet this session. Primary concern on file: {p["condition"]}.'
        recorded_line = "No live recording this session"

    # ── Dynamic historical correlation, pulled from the patient's actual
    # session history in data.py instead of fixed demo dates/levels. ──
    sessions = p.get("sessions", [])
    if len(sessions) >= 2:
        baseline, latest = sessions[-1], sessions[0]
        baseline_label = f'Baseline ({baseline["date"]})'
        latest_label = f'Last Visit ({latest["date"]})'
        baseline_level, latest_level = baseline["level"], latest["level"]
        pct_change = round((latest_level - baseline_level) / baseline_level * 100) if baseline_level else 0
        if pct_change > 0:
            trend_line, trend_color = f'⚠ Pain levels are trending upwards (+{pct_change}% since baseline)', "var(--pv-red)"
        elif pct_change < 0:
            trend_line, trend_color = f'✓ Pain levels are trending downwards ({pct_change}% since baseline)', "var(--pv-green)"
        else:
            trend_line, trend_color = "→ Pain levels are stable relative to baseline", "var(--pv-sub)"
    elif len(sessions) == 1:
        only = sessions[0]
        baseline_label, latest_label = f'Only Session on File ({only["date"]})', None
        baseline_level, latest_level = only["level"], None
        trend_line, trend_color = "ℹ Not enough sessions yet to establish a trend", "var(--pv-sub)"
    else:
        baseline_label, latest_label = "No sessions on file", None
        baseline_level, latest_level = None, None
        trend_line, trend_color = "ℹ Record a voice session to start building trend history", "var(--pv-sub)"

    col_l, col_r = st.columns([1, 1.5], gap="medium")

    with col_l:
        cls_label = r["label"] if r else ("High Pain" if is_high else "Low Pain")
        _, _, cls_accent, _ = classification_colors(cls_label)
        st.markdown(f"""
        <div class="pv-card">
            <span class="pv-badge pv-badge-blue">Active Session</span>
            <div style="float:right; font-size:0.74rem; color:var(--pv-muted);">ID: {p['id']}</div>
            <div style="font-weight:700; font-size:0.95rem; margin-top:0.6rem;">📈 Assessment Result</div>
            <div class="pv-hr" style="margin:0.6rem 0;"></div>
            <div style="display:flex; justify-content:space-between;">
                <div>
                    <div style="font-size:0.7rem; color:var(--pv-muted); text-transform:uppercase;">Classification</div>
                    <div style="font-weight:800; font-size:1.1rem; color:{cls_accent};">{cls_label}</div>
                </div>
                <div style="text-align:right;">
                    <div style="font-size:0.7rem; color:var(--pv-muted); text-transform:uppercase;">Confidence</div>
                    <div style="font-weight:800; font-size:1.1rem;">{confidence}%</div>
                </div>
            </div>
            <div class="pv-hr" style="margin:0.8rem 0;"></div>
            <div style="font-size:0.78rem; font-weight:600; color:var(--pv-sub);">Clinician Notes from Assessment:</div>
            <div style="font-size:0.83rem; font-style:italic; margin:0.3rem 0;">
                "{clinician_note}"
            </div>
            <div class="pv-hr" style="margin:0.8rem 0;"></div>
            <div style="display:flex; justify-content:space-between; font-size:0.76rem; color:var(--pv-muted);">
                <span>{recorded_line}</span><span>✓ AI Verified</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f"""
        <div class="pv-card">
            <div style="font-weight:700; font-size:0.88rem; text-transform:uppercase; letter-spacing:.03em;">Historical Correlation</div>
            <div style="display:flex; justify-content:space-between; padding:0.6rem 0; border-top:1px solid var(--pv-border); margin-top:0.5rem;">
                <span style="font-size:0.84rem;">{baseline_label}</span>{f'<span class="pv-badge pv-badge-gray">Level {baseline_level}</span>' if baseline_level is not None else ''}
            </div>
            {f'''<div style="display:flex; justify-content:space-between; padding:0.4rem 0; border-top:1px solid var(--pv-border);">
                <span style="font-size:0.84rem;">{latest_label}</span><span class="pv-badge pv-badge-gray">Level {latest_level}</span>
            </div>''' if latest_label else ''}
            <div style="font-size:0.78rem; color:{trend_color}; margin-top:0.5rem;">{trend_line}</div>
        </div>
        """, unsafe_allow_html=True)

        if r and r.get("spectrogram"):
            with st.expander("🔬  View Acoustic Spectrogram"):
                render_spectrogram(r["spectrogram"], key_suffix="treatmentplan")

    with col_r:
        st.markdown("""
        <div style="display:flex; gap:10px; align-items:flex-start;">
            <div class="pv-kpi-icon">📅</div>
            <div>
                <div style="font-weight:700; font-size:0.92rem;">Monitoring Schedule</div>
                <div style="font-size:0.8rem; color:var(--pv-muted);">Determine how frequently the patient should perform voice-based pain checks.</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
        mc1, mc2 = st.columns(2)
        with mc1:
            st.selectbox("Logging Frequency", ["2 Hours", "4 Hours", "Daily", "Twice Weekly", "Weekly"])
        with mc2:
            st.selectbox("Plan Duration", ["2 Weeks Routine", "4 Weeks Routine", "8 Weeks Extended"])
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("""
        <div style="display:flex; gap:10px; align-items:flex-start;">
            <div class="pv-kpi-icon">💊</div>
            <div>
                <div style="font-weight:700; font-size:0.92rem;">Pharmacological Intervention</div>
                <div style="font-size:0.8rem; color:var(--pv-muted);">Specify prescriptions or over-the-counter medications and titration plans.</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
        med_choice = st.selectbox(
            "Medication", COMMON_PAINKILLERS, label_visibility="collapsed", key="tp_med_select",
        )
        if med_choice == "Other":
            st.text_input(
                "Specify medication", placeholder="Enter medication name",
                key="tp_med_other", label_visibility="collapsed",
            )
        st.text_input("Dosage & Frequency", placeholder="e.g., 500mg BID, 300mg QHS", key="tp_dosage")
        st.markdown('<div style="font-size:0.78rem; color:var(--pv-sub); margin-top:0.5rem;">Administration Instructions</div>', unsafe_allow_html=True)
        st.text_area("admin_instr", placeholder="Describe any specific timing, dietary requirements, or warning signs for the patient.", label_visibility="collapsed", height=80)
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("""
        <div style="display:flex; gap:10px; align-items:flex-start;">
            <div class="pv-kpi-icon">🩺</div>
            <div>
                <div style="font-weight:700; font-size:0.92rem;">Therapeutic Regimen</div>
                <div style="font-size:0.8rem; color:var(--pv-muted);">Non-pharmacological treatments including physical therapy and home exercises.</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
        st.text_area("Therapy Details", placeholder="e.g., Targeted lumbar stretching, core stability exercises, 2x week clinic visits.", height=80)
        st.markdown('</div>', unsafe_allow_html=True)

        sb1, sb2, sb3 = st.columns([1, 1, 1.4])
        with sb1:
            st.button("Discard Changes", use_container_width=True, type="secondary", key="discard_btn")
        with sb2:
            if st.button("📄  Generate Report", use_container_width=True, type="secondary", key="gen_report_tp"):
                go("medical_report")
        with sb3:
            if st.button("Start Tracking & View Analytics  →", use_container_width=True, key="start_tracking_btn"):
                go("treatment_effectiveness")

        # ab1, ab2 = st.columns(2)
        # with ab1:
        #     st.markdown("""
        #     <div class="pv-card" style="padding:0.9rem 1.1rem;">
        #         <div style="font-weight:700; font-size:0.84rem;">📄 Pre-fill Protocol</div>
        #         <div style="font-size:0.76rem; color:var(--pv-muted);">Apply "Chronic Back Pain" template</div>
        #     </div>
        #     """, unsafe_allow_html=True)
        # with ab2:
        st.markdown(f"""
        <div style="background:var(--pv-red-bg); border:1px solid #F6CFCF; border-radius:12px; padding:0.9rem 1.1rem;">
            <div style="font-weight:700; font-size:0.84rem; color:var(--pv-red);">🩺 Alert Specialist</div>
            <div style="font-size:0.76rem; color:var(--pv-sub);">Order doctor consult</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Send Alert →", use_container_width=True, key="alert_specialist_btn"):
            st.session_state.show_alert_modal = True
            st.rerun()



def render_alert_modal(p, is_high):
    _, mid, _ = st.columns([0.3, 2, 0.3])
    with mid:
        st.markdown('<div class="pv-card" style="border:1px solid var(--pv-border);">', unsafe_allow_html=True)
        st.markdown('<div style="font-weight:800; font-size:1.15rem;">⚠️ Send Alert</div>', unsafe_allow_html=True)
        st.markdown("<div class='pv-hr'></div>", unsafe_allow_html=True)

        st.markdown('<div style="font-weight:700; font-size:0.82rem; color:var(--pv-sub); text-transform:uppercase;">👤 Patient Demographics</div>', unsafe_allow_html=True)
        dc1, dc2, dc3, dc4 = st.columns(4)
        for col, label, val in zip([dc1, dc2, dc3, dc4],
                                    ["Full Name", "Date of Birth", "Gender", "Clinical ID"],
                                    [p["name"], p["dob"], p["gender"], p["id"]]):
            with col:
                st.markdown(f'<div style="font-size:0.72rem; color:var(--pv-muted);">{label}</div><div style="font-weight:700; font-size:0.85rem;">{val}</div>', unsafe_allow_html=True)

        st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
        st.markdown('<div style="font-weight:700; font-size:0.82rem; color:var(--pv-sub); text-transform:uppercase;">🎙️ AI Speech Analysis Results</div>', unsafe_allow_html=True)
        r = st.session_state.last_result
        full_label = r["label"] if r else ("High Pain" if is_high else "Low Pain")
        level_label = full_label.upper().replace(" PAIN", "")
        confidence = r["confidence"] if r else 89.4
        alert_bg, _, alert_accent, _ = classification_colors(full_label)
        st.markdown(f"""
        <div style="background:{alert_bg}; border-radius:10px; padding:1rem 1.2rem; display:flex; justify-content:space-between; align-items:center; margin-top:0.4rem;">
            <div>
                <div style="font-size:0.74rem; color:{alert_accent}; font-weight:700;">DETECTED PAIN LEVEL</div>
                <div style="font-weight:800; font-size:1.6rem; color:{alert_accent};">{level_label}</div>
            </div>
            <span class="pv-badge pv-badge-blue">{confidence}% Confidence</span>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
        st.markdown('<div style="font-weight:700; font-size:0.82rem; color:var(--pv-sub); text-transform:uppercase;">💊 Treatment Plan & Follow-up</div>', unsafe_allow_html=True)
        st.markdown(f"""
        <div style="background:var(--pv-blue-bg); border-radius:10px; padding:0.8rem 1rem; margin-top:0.4rem;">
            <div style="font-size:0.72rem; color:var(--pv-blue-dark); font-weight:700;">PRESCRIBED REGIMEN</div>
            <div style="font-weight:700; font-size:0.88rem;">{p['care_plan'].split(' ')[0]}</div>
            <div style="font-size:0.78rem; color:var(--pv-sub);">{' '.join(p['care_plan'].split(' ')[1:])}</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
        st.markdown('<div style="font-weight:700; font-size:0.82rem; color:var(--pv-sub); text-transform:uppercase;">📝 Notes</div>', unsafe_allow_html=True)
        st.text_area("alert_notes", placeholder="Describe any specific timing, dietary requirements, or warning signs for the patient.", label_visibility="collapsed", height=80)

        st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
        bc1, bc2 = st.columns([1, 1])
        with bc1:
            if st.button("Cancel", use_container_width=True, type="secondary", key="alert_cancel"):
                st.session_state.show_alert_modal = False
                st.rerun()
        with bc2:
            if st.button("🚨  Alert Doctor  →", use_container_width=True, key="alert_confirm"):
                st.session_state.show_alert_modal = False
                st.session_state.alert_sent = True
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    if st.session_state.alert_sent:
        st.success("✓ Alert sent successfully to the attending specialist. Patient flagged for priority review.")
        st.session_state.alert_sent = False


# ─────────────────────────────────────────────────────────────────────────
# MEDICAL REPORT
# ─────────────────────────────────────────────────────────────────────────
def page_medical_report():
    topbar(back=True)
    p = current_patient()
    is_high = st.session_state.last_classification != "Low"
    r = st.session_state.last_result

    h1, h2 = st.columns([3, 1.4])
    with h1:
        st.markdown('<h2 style="margin-bottom:0;">Generate Medical Report</h2>', unsafe_allow_html=True)
        st.markdown('<div style="color:var(--pv-muted); font-size:0.84rem;">Review and finalize the clinical session summary.</div>', unsafe_allow_html=True)
    with h2:
        if st.button("⬇️  Export PDF", use_container_width=True, key="export_pdf_btn"):
            st.session_state.medical_report_pdf = build_medical_report_pdf(p, r, CLINICIAN, is_high)
            st.session_state.report_generated = True
            st.rerun()

    st.markdown("""
    <div style="background:var(--pv-blue-bg); border-radius:12px; padding:0.9rem 1.2rem; margin:1rem 0; display:flex; gap:10px; align-items:center;">
        <span style="font-size:1.1rem;">✓</span>
        <div>
            <div style="font-weight:700; font-size:0.88rem; color:var(--pv-blue-dark);">Report Verified</div>
            <div style="font-size:0.8rem; color:var(--pv-blue-dark); opacity:0.85;">AI analysis and clinician inputs have been successfully compiled. Ready for clinical archival.</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    full_label = r["label"] if r else ("High Pain" if is_high else "Low Pain")
    level_label = full_label.upper().replace(" PAIN", "")
    report_bg, _, report_accent, _ = classification_colors(full_label)
    if r:
        confidence = r["confidence"]
        duration = r["duration_sec"]
        biomarker_tags = [f"{b['label']}: {b['value']}" for b in r["biomarkers"]]
    else:
        confidence = 89.4
        duration = 10.4
        biomarker_tags = ["Increased pitch jitter", "Tension in glottal onset", "Micro-tremors detected"] if is_high else ["Stable pitch contour", "Clear glottal tone", "No tremors detected"]
    behavior_desc = {
        "Low Pain": "relaxed posture and steady vocal cadence",
        "Moderate Pain": "mild guarding with occasional vocal strain",
        "High Pain": "guarding behaviors and restricted vocal cadence",
    }.get(full_label, "relaxed posture and steady vocal cadence")

    st.markdown(f"""
    <div class="pv-card">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div>
                <div style="color:var(--pv-blue-dark); font-weight:800; font-size:1rem;">📈 PAINVOICE CLINICAL AI</div>
                <div style="font-size:0.78rem; color:var(--pv-muted); font-style:italic;">Standardized Voice-Based Pain Classification System</div>
            </div>
            <div style="text-align:right;">
                <div style="font-size:0.7rem; color:var(--pv-muted); text-transform:uppercase;">Report ID</div>
                <div style="font-weight:700; font-size:0.85rem;">{p['id']}-{datetime.now().strftime('%Y%m%d')}</div>
            </div>
        </div>
        <div class="pv-hr"></div>
        <div style="font-weight:700; font-size:0.82rem; color:var(--pv-sub); text-transform:uppercase;">👤 Patient Demographics</div>
        <div style="display:flex; gap:3rem; margin-top:0.5rem;">
            <div><div style="font-size:0.72rem; color:var(--pv-muted);">Full Name</div><div style="font-weight:700; font-size:0.85rem;">{p['name']}</div></div>
            <div><div style="font-size:0.72rem; color:var(--pv-muted);">Date of Birth</div><div style="font-weight:700; font-size:0.85rem;">{p['dob']}</div></div>
            <div><div style="font-size:0.72rem; color:var(--pv-muted);">Gender</div><div style="font-weight:700; font-size:0.85rem;">{p['gender']}</div></div>
            <div><div style="font-size:0.72rem; color:var(--pv-muted);">Clinical ID</div><div style="font-weight:700; font-size:0.85rem;">{p['id']}</div></div>
        </div>
        <div class="pv-hr"></div>
        <div style="font-weight:700; font-size:0.82rem; color:var(--pv-sub); text-transform:uppercase;">🎙️ AI Speech Analysis Results</div>
        <div style="background:{report_bg}; border-radius:10px; padding:1rem 1.2rem; display:flex; justify-content:space-between; align-items:center; margin-top:0.5rem;">
            <div>
                <div style="font-size:0.72rem; color:var(--pv-muted); text-transform:uppercase;">Detected Pain Level</div>
                <div style="font-weight:800; font-size:1.5rem; color:{report_accent};">{level_label}</div>
            </div>
            <span class="pv-badge pv-badge-blue">{confidence}% Confidence</span>
            <div style="font-size:0.8rem; color:var(--pv-sub);">🕐 Duration: <b>{duration}s</b></div>
            <div style="font-size:0.8rem; color:var(--pv-sub);">📅 Date: <b>{datetime.now().strftime('%b %d, %Y')}</b></div>
        </div>
        <div style="margin-top:0.7rem;">
            <div style="font-size:0.74rem; color:var(--pv-muted); text-transform:uppercase; margin-bottom:0.4rem;">Acoustic Biomarkers Detected</div>
            {''.join([f'<span class="pv-badge pv-badge-gray" style="margin-right:6px;">• {tag}</span>' for tag in biomarker_tags])}
        </div>
        <div class="pv-hr"></div>
        <div style="font-weight:700; font-size:0.82rem; color:var(--pv-sub); text-transform:uppercase;">🩺 Clinician Assessment</div>
        <p style="font-size:0.85rem; margin-top:0.4rem; color:var(--pv-ink);">
            Patient presented with chronic lower back discomfort. Voice recording captured during physical range-of-motion assessment.
            AI classification aligns with clinical observation of {behavior_desc}. No acute respiratory distress noted. Cognitive status remains stable.
        </p>
        <div class="pv-hr"></div>
        <div style="font-weight:700; font-size:0.82rem; color:var(--pv-sub); text-transform:uppercase;">💊 Treatment Plan & Follow-up</div>
        <div style="display:flex; gap:1rem; margin-top:0.5rem;">
            <div style="flex:1; background:var(--pv-blue-bg); border-radius:10px; padding:0.8rem 1rem;">
                <div style="font-size:0.72rem; color:var(--pv-blue-dark); font-weight:700;">PRESCRIBED REGIMEN</div>
                <div style="font-weight:700; font-size:0.86rem;">{p['care_plan']}</div>
            </div>
            <div style="flex:1; border:1px solid var(--pv-border); border-radius:10px; padding:0.8rem 1rem;">
                <div style="font-size:0.72rem; color:var(--pv-muted);">NEXT CLINICAL REVIEW</div>
                <div style="font-weight:700; font-size:0.86rem;">📅 {p['next_titration']} — Re-evaluation of pain trends required</div>
            </div>
        </div>
        <div class="pv-hr"></div>
        <div style="margin-top:0.6rem;">
            <div style="font-style:italic; font-weight:600; border-bottom:1px solid var(--pv-ink); display:inline-block;">Dr. {CLINICIAN['name']}</div>
            <div style="font-size:0.7rem; color:var(--pv-muted); text-transform:uppercase; margin-top:2px;">Digital Attestation</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if st.session_state.report_generated:
        st.success("✓ Report exported and digitally signed successfully.")
        if r and r.get("is_scripted_demo"):
            st.caption("🧪 Note: this session used a scripted demo result, not live GRU-Mixer inference.")
        elif r and not r.get("is_trained"):
            st.caption("⚠️ Note: the GRU-Mixer model is running with untrained (demo) weights — see gru_mixer.py for how to load a trained checkpoint.")
        if st.session_state.medical_report_pdf:
            st.download_button(
                "⬇️  Download PDF Report",
                data=st.session_state.medical_report_pdf,
                file_name=f"{p['id']}_medical_report_{datetime.now().strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                use_container_width=True,
                key="download_medical_report_pdf",
            )

    if st.button("←  Return to Patient File", use_container_width=True, type="secondary", key="return_patient_btn"):
        st.session_state.report_generated = False
        go("patient")


# ─────────────────────────────────────────────────────────────────────────
# TREATMENT EFFECTIVENESS  (+ AI Suggestions progressive disclosure)
# ─────────────────────────────────────────────────────────────────────────
def page_treatment_effectiveness():
    topbar(back=True)
    p = current_patient()
    st.markdown('<h2 style="margin-bottom:0.1rem;">Treatment Effectiveness Metrics</h2>', unsafe_allow_html=True)

    # ── Real, chronologically-sorted session history for charting.
    # p['sessions'] is stored newest-first (record_voice_session inserts at
    # index 0), and mixes hardcoded 2024 demo dates with real live-recorded
    # dates — sorting by actual parsed date (rather than truncating the
    # date string, which is what produced the broken squished x-axis)
    # handles both correctly regardless of how far apart they are. ──
    def _parse_session_date(date_str):
        try:
            return datetime.strptime(date_str, "%b %d, %Y")
        except (ValueError, TypeError):
            return None

    dated_sessions = [(s, _parse_session_date(s["date"])) for s in p["sessions"]]
    dated_sessions = [(s, d) for s, d in dated_sessions if d is not None]
    dated_sessions.sort(key=lambda pair: pair[1])  # oldest -> newest, left to right

    total_sessions = len(dated_sessions)
    data_sufficient = total_sessions >= 10
    sufficiency_badge = (
        '<span class="pv-badge pv-badge-blue">✓ Data Sufficient</span>' if data_sufficient
        else f'<span class="pv-badge pv-badge-amber">⚠ Building Data ({total_sessions}/10)</span>'
    )

    st.markdown(f"""
    <div class="pv-card" style="display:flex; justify-content:space-between; align-items:center;">
        <div style="display:flex; gap:2.2rem;">
            <div><div style="font-size:0.7rem; color:var(--pv-muted); text-transform:uppercase;">Current Patient</div><div style="font-weight:700; font-size:0.88rem;">{p['name']}</div></div>
            <div><div style="font-size:0.7rem; color:var(--pv-muted); text-transform:uppercase;">Patient ID</div><div style="font-weight:700; font-size:0.88rem;">{p['id']}</div></div>
            <div><div style="font-size:0.7rem; color:var(--pv-muted); text-transform:uppercase;">Primary Diagnosis</div><div style="font-weight:700; font-size:0.88rem;">{p['condition']}</div></div>
        </div>
        {sufficiency_badge}
    </div>
    """, unsafe_allow_html=True)

    import plotly.graph_objects as go

    cc1, cc2 = st.columns(2)
    with cc1:
        st.markdown('<div style="font-weight:700;">Pain Intensity Trend</div><div style="font-size:0.8rem; color:var(--pv-muted);">Speech-classified pain levels over time</div>', unsafe_allow_html=True)
        if len(dated_sessions) < 2:
            st.info("Not enough dated sessions yet to plot a trend — record at least two voice sessions.")
        else:
            x_dates = [d for _, d in dated_sessions]
            y_levels = [s["level"] for s, _ in dated_sessions]
            marker_colors = [
                "#D42525" if "High" in s["classification"] else "#C8860A" if "Moderate" in s["classification"] else "#1FA34D"
                for s, _ in dated_sessions
            ]
            fig = go.Figure(go.Scatter(
                x=x_dates, y=y_levels, mode="lines+markers",
                line=dict(color="#25AFF4", width=3),
                marker=dict(size=9, color=marker_colors, line=dict(width=1, color="white")),
                hovertemplate="%{x|%b %d, %Y}<br>Pain Level: %{y}<extra></extra>",
            ))
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(t=10, b=10, l=10, r=10), height=240,
                xaxis=dict(showgrid=False, color="#8A929C", type="date", tickformat="%b %d\n%Y"),
                yaxis=dict(showgrid=True, gridcolor="#E7E8EA", color="#8A929C", range=[0, 10]),
                font=dict(family="Plus Jakarta Sans", color="#171A1C"),
            )
            st.plotly_chart(fig, use_container_width=True)

    with cc2:
        st.markdown('<div style="font-weight:700;">Pain vs. AI Confidence</div><div style="font-size:0.8rem; color:var(--pv-muted);">How model confidence tracks alongside classified pain levels</div>', unsafe_allow_html=True)
        if len(dated_sessions) < 2:
            st.info("Not enough dated sessions yet to plot a correlation.")
        else:
            x_dates = [d for _, d in dated_sessions]
            y_levels = [s["level"] for s, _ in dated_sessions]
            y_conf = [s["confidence"] for s, _ in dated_sessions]
            bar_colors = [
                "#F6B8B8" if "High" in s["classification"] else "#F5DBA3" if "Moderate" in s["classification"] else "#BEE3F8"
                for s, _ in dated_sessions
            ]
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(
                x=x_dates, y=y_levels, marker_color=bar_colors, name="Pain Level", yaxis="y1",
                hovertemplate="%{x|%b %d, %Y}<br>Pain Level: %{y}<extra></extra>",
            ))
            fig2.add_trace(go.Scatter(
                x=x_dates, y=y_conf, mode="lines+markers", line=dict(color="#25AFF4", width=2), name="AI Confidence %", yaxis="y2",
                hovertemplate="%{x|%b %d, %Y}<br>Confidence: %{y}%<extra></extra>",
            ))
            fig2.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(t=28, b=10, l=10, r=10), height=240, showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, font=dict(size=10)),
                xaxis=dict(showgrid=False, color="#8A929C", type="date", tickformat="%b %d"),
                yaxis=dict(title="Pain Level", showgrid=True, gridcolor="#E7E8EA", color="#8A929C", range=[0, 10]),
                yaxis2=dict(title="Confidence %", overlaying="y", side="right", range=[0, 100], color="#8A929C"),
                font=dict(family="Plus Jakarta Sans", color="#171A1C"),
            )
            st.plotly_chart(fig2, use_container_width=True)

    sc1, sc2 = st.columns([1.4, 1])
    with sc1:
        st.markdown('<div style="font-weight:700;">✨ AI Improvement Suggestions</div><div style="font-size:0.8rem; color:var(--pv-sub);">Intelligence-driven recommendations based on data trends</div>', unsafe_allow_html=True)
        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

        if not st.session_state.suggestions_shown:
            _, bcol, _ = st.columns([1, 1.4, 1])
            with bcol:
                if st.button("📄  Generate Suggestions", use_container_width=True, key="gen_sugg_btn"):
                    with st.spinner("Analysing session data…"):
                        time.sleep(1.2)
                    st.session_state.suggestions_shown = True
                    st.rerun()
        else:
            gcols = st.columns(2)
            for col, s in zip(gcols, AI_SUGGESTIONS):
                with col:
                    st.markdown(f"""
                    <div style="background:#FFFFFF; border-left:3px solid var(--pv-blue); border-radius:10px; padding:0.9rem 1rem;">
                        <div style="display:flex; justify-content:space-between;">
                            <span style="font-size:0.7rem; font-weight:700; color:var(--pv-blue-dark); letter-spacing:.03em;">{s['tag']}</span>
                            <span class="pv-badge pv-badge-gray">Confidence: {s['confidence']}%</span>
                        </div>
                        <div style="font-size:0.83rem; margin-top:0.5rem;">{s['body']}</div>
                        <div style="font-size:0.78rem; color:var(--pv-blue); font-weight:600; margin-top:0.5rem;">{s['link']}</div>
                    </div>
                    """, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown(f"""
        <div class="pv-card">
            <div style="font-weight:700; font-size:0.86rem;">ℹ️ Data Sufficiency Analysis</div>
            <div style="font-size:0.8rem; color:var(--pv-sub); margin-top:0.3rem;">
                Correlation algorithms are currently based on {total_sessions} session{'s' if total_sessions != 1 else ''}. Statistical reliability of AI suggestions improves significantly after 10 sessions. Continuous monitoring is recommended for accurate trend validation.
            </div>
        </div>
        """, unsafe_allow_html=True)

    with sc2:
        st.markdown('<div style="font-weight:700;">🩺 Clinical Notes</div><div style="font-size:0.8rem; color:var(--pv-muted);">Observations from recent sessions</div>', unsafe_allow_html=True)
        for note in CLINICAL_NOTES:
            st.markdown(f"""
            <div style="padding:0.6rem 0; border-bottom:1px solid var(--pv-border);">
                <div style="display:flex; justify-content:space-between;">
                    <span style="font-size:0.74rem; color:var(--pv-muted); font-weight:600;">{note['date']}</span>
                    <span class="pv-badge pv-badge-gray">{note['tag']}</span>
                </div>
                <div style="font-size:0.82rem; margin-top:0.2rem;">{note['body']}</div>
            </div>
            """, unsafe_allow_html=True)
        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────
# ROUTER
# ─────────────────────────────────────────────────────────────────────────
def main():
    if not st.session_state.auth:
        if st.session_state.page == "register":
            page_register()
        else:
            page_login()
        return

    sidebar_nav()
    page = st.session_state.page
    pages = {
        "dashboard": page_dashboard,
        "patient_select": page_patient_select,
        "patient": page_patient,
        "voice_capture": page_voice_capture,
        "pain_result": page_pain_result,
        "treatment_plan": page_treatment_plan,
        "medical_report": page_medical_report,
        "treatment_effectiveness": page_treatment_effectiveness,
    }
    (pages.get(page) or page_dashboard)()


if __name__ == "__main__":
    main()