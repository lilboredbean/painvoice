# painvoice
Speech Emotion Recognition for Mulitclass Pain Classification System

A Streamlit application that predicts whether the voice is low, moderate or high pain
The deployed app uses a GRU-Mixer Model to classify the pain levels. The neutral network
is trained and made from scratch with the data from TAME-Pain Dataset.

## Run Application
https://painvoice.streamlit.app/

## Run locally

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

# Project Structure
**File / Folder	Purpose
app.py	Streamlit UI — pages, navigation, session state, all page logic.
data.py	In-memory data store: PATIENTS list, dashboard/demo content, record_voice_session(), new_patient_record().
gru_mixer.py	GRU-Mixer model, audio preprocessing, PainVoiceAnalyzer (analyze() and analyze_scripted()).
pdf_report.py	reportlab-based PDF generation for the medical report and effectiveness report.
styles.py	All custom CSS, injected once via st.markdown(get_css()).
demo_audio/	Three bundled WAV samples for the Demo Patient's quick-test buttons.
.streamlit/config.toml	Forces a light theme, independent of visitor OS/browser preference.
requirements.txt	Pinned Python dependencies.
**
