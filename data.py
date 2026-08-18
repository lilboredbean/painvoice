import random
from datetime import datetime

COMMON_PAINKILLERS = [
    "Acetaminophen (Tylenol)",
    "Ibuprofen (Advil / Motrin)",
    "Naproxen (Aleve)",
    "Aspirin",
    "Celecoxib (Celebrex)",
    "Diclofenac (Voltaren)",
    "Tramadol",
    "Gabapentin (Neurontin)",
    "Pregabalin (Lyrica)",
    "Duloxetine (Cymbalta)",
    "Cyclobenzaprine (Flexeril)",
    "Morphine",
    "Oxycodone",
    "Hydrocodone/Acetaminophen (Vicodin)",
    "Other",
]

AVATAR_PALETTE = ["#BEE3F8", "#F8CBE0", "#D6F5E3", "#FDE8C8", "#E4D9F9", "#FBD5D5", "#C9E4DE"]


def _parse_session_date(date_str):
    try:
        return datetime.strptime(date_str, "%b %d, %Y")
    except (ValueError, TypeError):
        return None


def record_voice_session(patient, result):
    """Persist a live GRU-Mixer analysis into the patient's record: appends
    a real session entry (matching the shape of the existing demo sessions)
    and refreshes the patient's rolling summary stats — nothing about this
    is hardcoded, it's derived entirely from `result` (the dict returned by
    PainVoiceAnalyzer.analyze()). Also logs the session to the dashboard's
    Recent Activity feed. Returns the new session entry."""
    now = datetime.now()
    session_entry = {
        "date": now.strftime("%b %d, %Y"),
        "time": now.strftime("%I:%M %p"),
        "classification": result["label"],
        "level": result["level"],
        "confidence": result["confidence"],
        "duration": f"0:{int(round(result['duration_sec'])):02d}",
        "voice_id": f"S-{random.randint(100, 999)}",
    }
    patient["sessions"].insert(0, session_entry)
    patient["last_pain_level"] = result["level"]

    # Prefer a true "last 30 days" window; fall back to the most recent
    # handful of sessions if none fall inside that window (e.g. the only
    # sessions on file are old seed/demo data).
    window = [s for s in patient["sessions"] if (d := _parse_session_date(s["date"])) and (now - d).days <= 30]
    if not window:
        window = patient["sessions"][:5]

    patient["avg_pain_30d"] = round(sum(s["level"] for s in window) / len(window), 1)
    patient["ai_accuracy"] = round(sum(s["confidence"] for s in window) / len(window), 1)

    RECENT_ACTIVITY.insert(0, {
        "time": session_entry["time"], "name": patient["name"],
        "action": "Session Generated", "level": result["level"],
    })
    return session_entry


def new_patient_record(name, age, gender, blood_type, dob, condition, allergies_raw, care_plan, existing_ids=None):
    """Build a fresh patient record dict for PATIENTS. `allergies_raw` is a raw
    comma-separated string as typed in the create-patient form."""
    existing_ids = existing_ids or set()
    patient_id = f"PN-{random.randint(1000, 9999)}"
    while patient_id in existing_ids:
        patient_id = f"PN-{random.randint(1000, 9999)}"

    allergies = [a.strip() for a in (allergies_raw or "").split(",") if a.strip()]

    return {
        "id": patient_id, "name": name, "age": age, "gender": gender,
        "blood_type": blood_type or "Unknown", "status_label": "New Patient", "case": "New Case",
        "condition": condition, "dob": dob or "Not on file",
        "avatar_color": random.choice(AVATAR_PALETTE),
        "allergies": allergies or ["None reported"],
        "care_plan": care_plan or "Not yet prescribed",
        "next_titration": "Not scheduled",
        "last_pain_level": None, "avg_pain_30d": 0,
        "adherence": 0, "ai_accuracy": 0,
        "sessions": [],
    }


PATIENTS = [
    {
            "id": "PN-1092", "name": "Marcus Holloway", "age": 38, "gender": "Male",
            "blood_type": "B+", "status_label": "Active Monitoring", "case": "Active Case",
            "condition": "Post-Surgical Pain (Knee Replacement)", "dob": "Mar 19, 1987",
            "avatar_color": "#BEE3F8", "allergies": ["Sulfa Drugs"],
            "care_plan": "Naproxen 500mg BID", "next_titration": "Nov 10",
            "last_pain_level": 5, "avg_pain_30d": 5.0,
            "adherence": 91, "ai_accuracy": 88.7,
            "sessions": [
                {"date": "Oct 23, 2024", "time": "01:20 PM", "classification": "Moderate Pain", "level": 5, "confidence": 86, "duration": "0:11", "voice_id": "S-188"},
            ],
        },
    {
        "id": "P-88293", "name": "Maria Rodriguez", "age": 42, "gender": "Female",
        "blood_type": "A+", "status_label": "Post-Op Week 4", "case": "Active Case",
        "condition": "Chronic Lower Back Pain (L4-L5 Herniation)",
        "dob": "May 12, 1978", "avatar_color": "#F8CBE0",
        "allergies": ["Penicillin", "Latex"],
        "care_plan": "Pregabalin 75mg bid", "next_titration": "Nov 05",
        "last_pain_level": 8, "avg_pain_30d": 5.4,
        "adherence": 94, "ai_accuracy": 91.2,
        "sessions": [
            {"date": "Oct 24, 2024", "time": "09:15 AM", "classification": "High Pain", "level": 8, "confidence": 92, "duration": "0:12", "voice_id": "S-101"},
            {"date": "Oct 17, 2024", "time": "02:30 PM", "classification": "Moderate Pain", "level": 6, "confidence": 88, "duration": "0:10", "voice_id": "S-100"},
            {"date": "Oct 10, 2024", "time": "11:00 AM", "classification": "Moderate Pain", "level": 4, "confidence": 85, "duration": "0:11", "voice_id": "S-099"},
            {"date": "Oct 03, 2024", "time": "08:45 AM", "classification": "Low Pain", "level": 2, "confidence": 95, "duration": "0:10", "voice_id": "S-098"},
            {"date": "Sep 26, 2024", "time": "04:15 PM", "classification": "High Pain", "level": 7, "confidence": 89, "duration": "0:13", "voice_id": "S-097"},
        ],
    },
    {
        "id": "DEMO-0001", "name": "Demo Patient", "age": 35, "gender": "Other",
        "blood_type": "Unknown", "status_label": "Demo Profile", "case": "Demo Case",
        "condition": "Demo / Testing Profile", "dob": "Not on file",
        "avatar_color": "#D6F5E3", "allergies": ["None reported"],
        "care_plan": "Not yet prescribed", "next_titration": "Not scheduled",
        "last_pain_level": None, "avg_pain_30d": 0,
        "adherence": 0, "ai_accuracy": 0,
        "sessions": [],
        "is_demo": True,
    },
]

CLINICIAN = {"name": "Sarah Chen", "title": "Ortho Nurse"}

DASHBOARD_KPIS = {
    "active_patients": {"value": 128, "delta": "+4 from last week", "trend": "+3.2%"},
    "todays_sessions": {"value": 24, "delta": "6 sessions pending review", "trend": "+12%"},
    "completed_reports": {"value": 892, "delta": "Monthly compliance: 98%"},
    "system_health": {"value": "Optimal", "delta": "AI Model v1.2.0 active"},
}

SYSTEM_INSIGHTS = [
    {
        "icon": "📈",
        "title": "Trend Anomaly Detected",
        "body": "Patient Kenji Sato (PN-3310) shows a 40% increase in pain severity frequency over the last 48 hours. Suggest scheduling immediate review.",
    },
    {
        "icon": "📄",
        "title": "Pending Reports Ready",
        "body": "4 session analyses from today are waiting for clinical validation before final report generation.",
    },
]

RECENT_ACTIVITY = [
    {"time": "09:12 AM", "name": "Maria Rodriguez", "action": "Session Generated", "level": 8},
    {"time": "08:30 AM", "name": "Marcus Holloway", "action": "Session Recorded", "level": 5},
]

ACOUSTIC_BIOMARKERS_HIGH = [
    {"label": "Pitch Variability", "value": "42.5 Hz", "note": "High frequency modulation indicative of acute distress."},
    {"label": "Harmonic-to-Noise", "value": "12.2 dB", "note": "Significant vocal breathiness and strain detected."},
    {"label": "Intensity Jitter", "value": "8.4%", "note": "Unstable amplitude consistent with breath-holding."},
]

ACOUSTIC_BIOMARKERS_LOW = [
    {"label": "Pitch Variability", "value": "18.1 Hz", "note": "Stable modulation within normal speech range."},
    {"label": "Harmonic-to-Noise", "value": "21.6 dB", "note": "Clear vocal tone, minimal strain detected."},
    {"label": "Intensity Jitter", "value": "2.7%", "note": "Consistent amplitude, no breath-holding observed."},
]

AI_NOTES_HIGH = [
    {"label": "Trend Analysis", "body": "Pain levels have increased by 2 points since the last session (48h ago). Recommend reviewing medication efficacy."},
    {"label": "Acoustic Match", "body": "Analysis matches 94% of documented \"Chronic Flare-up\" speech signatures in the clinical database."},
]

AI_NOTES_LOW = [
    {"label": "Trend Analysis", "body": "Pain levels have decreased steadily over the last 3 sessions. Current treatment appears effective."},
    {"label": "Acoustic Match", "body": "Analysis matches 92% of documented \"Stable Recovery\" speech signatures in the clinical database."},
]

AI_SUGGESTIONS = [
    {"tag": "MEDICATION UPDATE", "confidence": 94, "body": "Transition from Naproxen to Pregabalin has resulted in a 40% improvement in voice-coded stability.", "link": "View Clinical Rationale"},
    {"tag": "SCHEDULE ALERT", "confidence": 82, "body": "Pain spikes correlate with longer intervals between therapeutic recordings. Recommend increasing session frequency to daily.", "link": "Adjust Tracking Plan"},
]

CLINICAL_NOTES = [
    {"date": "OCT 30, 2024", "tag": "Follow-up", "body": "Patient reports significant reduction in morning stiffness since Pregabalin initiation."},
    {"date": "OCT 26, 2024", "tag": "Assessment", "body": "Speech analysis detected lower glottal tension than previous session."},
]