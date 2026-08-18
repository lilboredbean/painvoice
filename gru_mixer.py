"""
gru_mixer.py
────────────────────────────────────────────────────────────────────────────
Voice-based pain classifier used by the "Voice Capture" flow in app.py.

The architecture and preprocessing steps mirror the reference notebook
(`gru_mixer_pain_classification.ipynb`), which replicates the GRU-Mixer
model from Alhudhaif (2025), *Diagnostics*, 15, 2362:

    raw audio -> resample to 8kHz -> pad/trim to 3s
              -> 64-band log-Mel spectrogram (per-utterance normalized)
              -> bidirectional GRU (3 layers, hidden=64)
              -> temporal mixing (adaptive avg-pool over time)
              -> dropout -> linear head -> softmax over pain classes

This module wires a REAL forward pass into the app: whatever the patient
records is actually resampled, turned into a spectrogram, and pushed
through the network below — there is no mocked/random classification
in this file.

── A note on model weights ──────────────────────────────────────────────
No trained checkpoint ships with this app, because training requires the
TAME-Pain dataset, which isn't bundled here. On startup the network is
initialized with a fixed random seed (reproducible, but NOT clinically
meaningful). To make predictions clinically meaningful:

    1. Run `gru_mixer_pain_classification.ipynb` end-to-end against the
       TAME-Pain dataset (or your own labeled dataset in the same shape).
    2. Save the trained weights:  torch.save(model.state_dict(), MODEL_CHECKPOINT_PATH)
    3. Restart the app — the checkpoint is picked up automatically and
       `analyze()` will report `is_trained: True`.

Until then, treat classification output as a functional demo of the
pipeline, not a diagnostic result. The Acoustic Biomarkers card is
computed independently with plain signal-processing (real, not learned)
so it stays informative either way.
"""

import io
import os
import random

import numpy as np
import torch
import torch.nn as nn
import torchaudio.transforms as T
import soundfile as sf

# ── Config (mirrors the notebook) ───────────────────────────────────────────
SEED = 42
TARGET_SR = 8000
CLIP_DURATION = 3
N_SAMPLES = TARGET_SR * CLIP_DURATION

N_FFT = 1024
HOP_LENGTH = 256
N_MELS = 64

GRU_HIDDEN = 64
GRU_LAYERS = 3
DROPOUT = 0.5

CLASS_LABELS = ["Low Pain", "Moderate Pain", "High Pain"]
# Numeric 1-10 "level" is now constrained to the range implied by the
# WINNING class (see analyze() below) rather than a free-floating
# probability-weighted average across all three anchors. The old approach
# (dot(probs, [2.5, 5.5, 8.5])) could land near 5 for a near-uniform
# distribution regardless of which class actually won — producing exactly
# the "Low Pain / Level 5" contradiction this maps out of.
CLASS_LEVEL_RANGES = {
    "Low Pain": (1, 3),
    "Moderate Pain": (4, 6),
    "High Pain": (7, 10),
}

MODEL_CHECKPOINT_PATH = os.environ.get("PAINVOICE_MODEL_PATH", "model_weights/gru_mixer.pt")

random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)


# ── Model (identical to the notebook's GRUMixer) ────────────────────────────
class GRUMixer(nn.Module):
    """
    GRU-Mixer architecture from Alhudhaif (2025).
    Input : (batch, T, F)  — Log-Mel spectrogram sequence
    Output: (batch, n_classes) — logits
    """

    def __init__(self, input_size=N_MELS, hidden_size=GRU_HIDDEN,
                 num_layers=GRU_LAYERS, n_classes=len(CLASS_LABELS), dropout=DROPOUT):
        super().__init__()
        self.gru = nn.GRU(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            bidirectional=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.pool = nn.AdaptiveAvgPool1d(1)
        self.dropout = nn.Dropout(p=dropout)
        self.fc = nn.Linear(hidden_size * 2, n_classes)  # x2 for bidirectional

    def forward(self, x):
        out, _ = self.gru(x)               # (B, T, 2H)
        out = out.permute(0, 2, 1)          # (B, 2H, T)
        out = self.pool(out).squeeze(-1)    # (B, 2H)
        out = self.dropout(out)
        return self.fc(out)                 # (B, n_classes)


_mel_transform = T.MelSpectrogram(
    sample_rate=TARGET_SR, n_fft=N_FFT, hop_length=HOP_LENGTH,
    n_mels=N_MELS, window_fn=torch.hann_window, power=2.0,
)
_amp_to_db = T.AmplitudeToDB(stype="power", top_db=80)


# ── Audio preprocessing ──────────────────────────────────────────────────────
def _read_audio_bytes(audio_bytes: bytes):
    """Decode raw bytes (e.g. from st.audio_input) into a mono float32 array + sr."""
    data, sr = sf.read(io.BytesIO(audio_bytes), dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)
    return data, sr


def preprocess(audio_bytes: bytes) -> torch.Tensor:
    """Raw bytes -> (1, N_SAMPLES) waveform, mono, resampled, padded/trimmed."""
    data, sr = _read_audio_bytes(audio_bytes)
    waveform = torch.tensor(data, dtype=torch.float32).unsqueeze(0)  # (1, N)
    if sr != TARGET_SR:
        waveform = T.Resample(orig_freq=sr, new_freq=TARGET_SR)(waveform)
    length = waveform.shape[-1]
    if length < N_SAMPLES:
        waveform = torch.nn.functional.pad(waveform, (0, N_SAMPLES - length))
    else:
        waveform = waveform[..., :N_SAMPLES]
    return waveform


def _raw_log_mel_db(waveform: torch.Tensor) -> torch.Tensor:
    """(1, N_SAMPLES) waveform -> (1, N_MELS, T) log-Mel spectrogram in dB,
    BEFORE per-utterance normalization. Shared by extract_log_mel() (which
    normalizes it for the model) and spectrogram_for_display() (which keeps
    the raw dB scale, since that's what's actually interpretable to look at)."""
    mel = _mel_transform(waveform)      # (1, N_MELS, T)
    return _amp_to_db(mel)              # log scale, roughly -80..+40 dB


def extract_log_mel(waveform: torch.Tensor) -> torch.Tensor:
    """(1, N_SAMPLES) waveform -> (1, T, N_MELS) log-Mel spectrogram batch,
    normalized per-utterance to roughly zero-mean/unit-variance.

    Without this normalization step, log-Mel dB values (typically -80..+40)
    are far outside the ~unit-variance range PyTorch's default GRU weight
    init assumes. Feeding such large-magnitude values into the GRU drives
    its sigmoid/tanh gates into saturation, which makes the network's
    output nearly constant regardless of the input audio — i.e. it
    "collapses" to whichever class its random bias favors, independent of
    what's actually in the recording. Per-utterance mean/variance
    normalization (standard CMVN, used in most speech models) keeps the
    GRU responsive to input variation even with untrained weights.
    """
    log_mel = _raw_log_mel_db(waveform)
    log_mel = (log_mel - log_mel.mean()) / (log_mel.std() + 1e-6)
    return log_mel.transpose(1, 2)      # (1, T, N_MELS)


def spectrogram_for_display(waveform: torch.Tensor) -> dict:
    """Raw (un-normalized) log-Mel spectrogram plus axis info, for plotting —
    this is what the model actually "sees" (before normalization), in an
    interpretable dB scale rather than the zero-mean/unit-variance version
    used internally for inference."""
    db = _raw_log_mel_db(waveform).squeeze(0).numpy()  # (N_MELS, T)
    n_mels, n_frames = db.shape
    time_axis = (np.arange(n_frames) * HOP_LENGTH / TARGET_SR).tolist()
    mel_axis = list(range(n_mels))
    return {"db": db, "time_axis": time_axis, "mel_axis": mel_axis}


# ── Lightweight acoustic biomarkers (real DSP, shown regardless of training) ─
def _voiced_f0_track(wave: np.ndarray, sr: int, frame=400, hop=160, fmin=70, fmax=400):
    """Small autocorrelation-based F0 tracker for the biomarker card only —
    this does NOT feed the neural network, it's a separate, transparent signal."""
    f0s = []
    for start in range(0, max(len(wave) - frame, 0), hop):
        seg = wave[start:start + frame]
        seg = seg - seg.mean()
        if np.abs(seg).max() < 1e-4:
            continue
        corr = np.correlate(seg, seg, mode="full")[frame - 1:]
        lo, hi = int(sr / fmax), int(sr / fmin)
        if hi >= len(corr) or lo >= hi:
            continue
        segment = corr[lo:hi]
        if len(segment) == 0 or corr[0] <= 0:
            continue
        peak = int(np.argmax(segment)) + lo
        if peak > 0 and corr[peak] > 0.3 * corr[0]:
            f0s.append(sr / peak)
    return np.array(f0s)


def compute_biomarkers(waveform: torch.Tensor, sr: int = TARGET_SR):
    """Real, signal-processing-only features computed from the actual recording."""
    wave = waveform.squeeze(0).numpy()

    f0 = _voiced_f0_track(wave, sr)
    pitch_var = float(np.std(f0)) if len(f0) > 3 else 0.0

    frame, hop = 400, 160
    energies = np.array([
        np.sqrt(np.mean(wave[i:i + frame] ** 2))
        for i in range(0, max(len(wave) - frame, 1), hop)
    ])
    energies = energies[energies > 1e-5]
    jitter_pct = float(100 * np.std(energies) / np.mean(energies)) if len(energies) > 3 else 0.0

    windowed = wave * np.hanning(len(wave))
    spec = np.abs(np.fft.rfft(windowed))
    spec = spec[spec > 1e-8]
    if len(spec) > 0:
        gmean = np.exp(np.mean(np.log(spec)))
        amean = np.mean(spec)
        flatness = gmean / amean if amean > 0 else 1.0
        hnr_db = float(np.clip(-10 * np.log10(flatness + 1e-9), 0, 30))
    else:
        hnr_db = 0.0

    return [
        {
            "label": "Pitch Variability", "value": f"{pitch_var:.1f} Hz",
            "note": ("High-frequency pitch modulation, consistent with acute distress."
                      if pitch_var > 30 else "Modulation within the stable speech range."),
        },
        {
            "label": "Harmonic-to-Noise", "value": f"{hnr_db:.1f} dB",
            "note": ("Reduced harmonic clarity — vocal breathiness/strain detected."
                      if hnr_db < 15 else "Clear vocal tone, minimal strain detected."),
        },
        {
            "label": "Intensity Jitter", "value": f"{jitter_pct:.1f}%",
            "note": ("Unstable amplitude, consistent with breath-holding."
                      if jitter_pct > 5 else "Consistent amplitude, no breath-holding observed."),
        },
    ]


# ── Inference wrapper ────────────────────────────────────────────────────────
class PainVoiceAnalyzer:
    """Loads (or lazily initializes) the GRU-Mixer model once per process."""

    _instance = None

    def __init__(self):
        self.model = GRUMixer(n_classes=len(CLASS_LABELS))
        self.is_trained = False
        if os.path.exists(MODEL_CHECKPOINT_PATH):
            try:
                state = torch.load(MODEL_CHECKPOINT_PATH, map_location="cpu")
                self.model.load_state_dict(state)
                self.is_trained = True
            except Exception:
                self.is_trained = False
        self.model.eval()

    @classmethod
    def get(cls) -> "PainVoiceAnalyzer":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @torch.no_grad()
    def analyze(self, audio_bytes: bytes) -> dict:
        waveform = preprocess(audio_bytes)
        spec = extract_log_mel(waveform)
        logits = self.model(spec)
        probs = torch.softmax(logits, dim=-1).squeeze(0).numpy()

        pred_idx = int(probs.argmax())
        label = CLASS_LABELS[pred_idx]
        confidence = float(probs[pred_idx]) * 100

        # Map confidence -> a level WITHIN the winning class's own range,
        # so the displayed number can never contradict the label. A 3-way
        # softmax's confidence floor is 33.3% (total uncertainty, which
        # lands at the bottom of the bucket) up to 100% (full certainty,
        # top of the bucket).
        lo, hi = CLASS_LEVEL_RANGES[label]
        frac = (confidence - 100 / 3) / (100 - 100 / 3)
        frac = max(0.0, min(1.0, frac))
        level_int = int(round(lo + frac * (hi - lo)))
        level_int = max(lo, min(hi, level_int))

        return {
            "label": label,
            "level": level_int,
            "confidence": round(confidence, 1),
            "probs": {CLASS_LABELS[i]: round(float(probs[i]) * 100, 1) for i in range(len(CLASS_LABELS))},
            "biomarkers": compute_biomarkers(waveform),
            "is_trained": self.is_trained,
            "is_scripted_demo": False,
            "duration_sec": round(waveform.shape[-1] / TARGET_SR, 1),
            "spectrogram": spectrogram_for_display(waveform),
        }

    def analyze_scripted(self, audio_bytes: bytes, label: str, confidence: float) -> dict:
        """Build a result for the Demo Patient's one-click quick-test buttons
        using a FIXED, scripted classification instead of a live model
        prediction. With no trained checkpoint, live inference on these
        samples is arbitrary (see analyze()'s docstring) — for a demo
        button explicitly labeled "Low/Moderate/High Pain Sample", showing
        that arbitrary output instead of the labeled outcome would just be
        confusing. Biomarkers, duration, and the spectrogram are still
        computed for real from the actual audio; only the classification
        itself is fixed, and the result is explicitly flagged
        (`is_scripted_demo: True`) so the UI never claims this came from
        live inference."""
        if label not in CLASS_LABELS:
            raise ValueError(f"Unknown label {label!r}, expected one of {CLASS_LABELS}")
        waveform = preprocess(audio_bytes)
        lo, hi = CLASS_LEVEL_RANGES[label]
        level_int = int(round((lo + hi) / 2))

        other_labels = [l for l in CLASS_LABELS if l != label]
        remaining = max(0.0, 100.0 - confidence)
        probs = {label: round(confidence, 1)}
        for other in other_labels:
            probs[other] = round(remaining / len(other_labels), 1)

        return {
            "label": label,
            "level": level_int,
            "confidence": round(confidence, 1),
            "probs": probs,
            "biomarkers": compute_biomarkers(waveform),
            "is_trained": self.is_trained,
            "is_scripted_demo": True,
            "duration_sec": round(waveform.shape[-1] / TARGET_SR, 1),
            "spectrogram": spectrogram_for_display(waveform),
        }