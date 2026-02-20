# 🧠 CortexKey v0.1 — Brainwave-Backed Authentication

> **The Mind-Driven Master Key** — Dynamic Neural Authentication using EEG brainwave patterns as biometric passkeys.

**Team BlackHats** — HYP 7.0 Hackathon  
Devesh • Aditya • Sadaf • Abhinav

---

## 🚀 Quick Start

```bash
# 1. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Launch the app
streamlit run app.py
```

The dashboard will open at **http://localhost:8501**

---

## 🎯 What is CortexKey?

CortexKey replaces traditional authentication (passwords, fingerprints) with **brainwave patterns**. Users perform an "Emotional Recall" mental task (thinking of loved ones, pets, warm memories) which generates a unique EEG signature that:

- ✅ **Cannot be replicated** — each person's brain is unique
- ✅ **Anti-coercion** — stress/fear fundamentally alters the neural pattern
- ✅ **Dynamic** — unlike fingerprints, brainwaves prove you're alive and willing
- ✅ **FIDO2-compliant** — works as a WebAuthn passkey (same standard as Google/Apple passkeys)

---

## 📱 Demo Flow

### 1. 🧠 Onboarding
- Connect headband (BioAmp EXG Pill + ESP32)
- Perform Emotional Recall task 20 times
- System learns your neural signature via SVM classifier

### 2. 🔐 Authentication Scenarios
| Scenario | Expected Result |
|---|---|
| Devesh (enrolled user) | ✅ Authenticated |
| Abhinav (enrolled user) | ✅ Authenticated |
| Impostor (unknown person) | ❌ Denied |
| Devesh under coercion | ❌ Denied |

### 3. 🔑 Passkey Integration
- Register CortexKey as a FIDO2/WebAuthn passkey
- Demo: Add passkey to Google Account
- Demo: Sign in to Google using brainwave authentication

---

## 🏗️ Architecture

```
Hardware Layer (Edge)              Software Layer (Processing)
┌──────────────────────┐          ┌──────────────────────────────┐
│ BioAmp EXG Pill      │──UART──▶│ Signal Acquisition           │
│ (Analog Front End)   │          │ (BrainFlow SDK / Mock)       │
├──────────────────────┤          ├──────────────────────────────┤
│ ESP32 / Arduino      │          │ Preprocessing                │
│ (ADC + Transmission) │          │ • 50Hz Notch Filter          │
├──────────────────────┤          │ • 5-30Hz Bandpass Filter     │
│ Ag/AgCl Electrodes   │          ├──────────────────────────────┤
│ (Fp1/Fp2 + Mastoid)  │          │ Feature Extraction           │
├──────────────────────┤          │ • PSD (Welch's method)       │
│ 9V Battery           │          │ • Band Powers (δ,θ,α,β)     │
│ (Isolated power)     │          │ • Spectral Ratios            │
└──────────────────────┘          ├──────────────────────────────┤
                                  │ Classification               │
                                  │ • SVM (RBF kernel)           │
                                  │ • Confidence threshold: 70%  │
                                  ├──────────────────────────────┤
                                  │ Passkey Engine               │
                                  │ • ECDSA P-256 keypair        │
                                  │ • FIDO2/WebAuthn protocol    │
                                  │ • Challenge-response signing │
                                  └──────────────────────────────┘
```

---

## 📂 Project Structure

```
CortexKey/
├── app.py                        # Streamlit dashboard (main entry)
├── requirements.txt              # Python dependencies
├── cortexkey/
│   ├── __init__.py
│   ├── eeg_simulator.py          # Mock EEG data generator (4 user profiles)
│   ├── signal_processing.py      # Real DSP pipeline (notch + bandpass + PSD)
│   ├── classifier.py             # SVM classifier (scikit-learn)
│   ├── auth_engine.py            # Enrollment + verification orchestrator
│   ├── crypto_utils.py           # ECDSA key generation & signing
│   └── passkey_manager.py        # FIDO2/WebAuthn credential manager
├── data/
│   ├── models/                   # Saved classifier models
│   ├── templates/                # Enrolled neural templates
│   ├── keys/                     # ECDSA key storage
│   └── passkeys/                 # WebAuthn credentials
└── Project_Context_CortexKey.md  # Full project documentation
```

---

## 🔬 Technical Details

### Signal Processing Pipeline
1. **Notch Filter (50Hz)** — Removes India mains power line interference
2. **Bandpass Filter (5-30Hz)** — Isolates alpha + beta neural bands
3. **Welch PSD** — Extracts frequency-domain features
4. **Feature Vector** — 13 features including band powers, ratios, spectral entropy

### Classifier
- **Algorithm:** SVM with RBF kernel
- **Normalization:** StandardScaler
- **Calibration:** Platt scaling for probability estimates
- **Threshold:** 70% confidence (configurable)

### Passkey Crypto
- **Key Algorithm:** ECDSA P-256 (same as Google/Apple passkeys)
- **Protocol:** FIDO2/WebAuthn Level 2
- **Attestation:** Self-attestation (none format)
- **User Verification:** EEG neural signature

---

## 📚 References

### Academic Papers
- Chuang et al. (2013) — "Cerebrem: A BCI for User Authentication"
- Gui et al. (2014) — "A Survey of EEG-based Biometrics"
- Ashby et al. (2011) — "Low-Cost EEG Based BCI User Identification"
- Palaniappan (2004) — "Identifying Individuals Using Brain Electrical Activity"

### Open Source
- [Backyard Brains](https://backyardbrains.com) — Open-source neuroscience hardware & education
- [BrainFlow SDK](https://brainflow.org) — Biosensor data acquisition API
- [MNE-Python](https://mne.tools) — EEG signal processing
- [BioAmp EXG Pill](https://store.upside-downlabs.tech/product/bioamp-exg-pill/) — Analog front end
- [FIDO Alliance](https://fidoalliance.org) — WebAuthn specification

---

## 🛡️ Security Properties

| Property | How CortexKey Achieves It |
|---|---|
| **Uniqueness** | Each brain has unique spectral fingerprint (alpha peak, band ratios) |
| **Non-replicability** | Internal neural signals cannot be captured externally |
| **Anti-coercion** | Stress/fear causes alpha suppression + beta surge → auth fails |
| **Liveness** | Only living, conscious brains produce coherent EEG patterns |
| **Phishing-resistant** | FIDO2 credentials are bound to specific origins (domains) |
| **Zero-knowledge** | Private key never leaves the device |

---

## 📄 License

MIT License — Built for HYP 7.0 Hackathon by Team BlackHats
