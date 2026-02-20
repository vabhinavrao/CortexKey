"""
CortexKey v0.1 — Streamlit Dashboard
Brainwave-Backed Authentication System

Main application entry point providing:
  1. 🧠 Onboarding — Enroll neural signatures
  2. 🔐 Authentication — Verify identity via brainwaves
  3. 📊 Signal Visualizer — Real-time EEG processing view
  4. 🔑 Passkey Manager — FIDO2/WebAuthn credential management
  5. 🌐 Google Passkey Demo — Integration with Google ecosystem

Run: streamlit run app.py

References:
  - Backyard Brains (backyardbrains.com) — Open-source neuroscience education
  - BrainFlow SDK — Biosensor data acquisition
  - MNE-Python — EEG signal processing methodology
  - FIDO Alliance — WebAuthn/Passkey specifications
"""

import streamlit as st
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import time
import json

from cortexkey.auth_engine import AuthEngine
from cortexkey.passkey_manager import PasskeyManager
from cortexkey.signal_processing import (
    full_preprocessing_pipeline,
    compute_psd,
    extract_band_powers,
    extract_features,
    BANDS,
)
from cortexkey.eeg_simulator import (
    generate_eeg_signal,
    get_available_users,
    get_user_description,
    SAMPLING_RATE,
    USER_PROFILES,
)


# ─────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────

st.set_page_config(
    page_title="CortexKey — Neural Authentication",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────
# CUSTOM CSS
# ─────────────────────────────────────────────────────────

st.markdown("""
<style>
    /* Global dark theme enhancements */
    .stApp {
        background-color: #0a0a0f;
    }

    /* Header styling */
    .cortexkey-header {
        background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
        padding: 2rem;
        border-radius: 16px;
        margin-bottom: 2rem;
        border: 1px solid rgba(100, 100, 255, 0.2);
        text-align: center;
    }

    .cortexkey-header h1 {
        color: #e0e0ff;
        font-size: 2.5rem;
        margin: 0;
    }

    .cortexkey-header p {
        color: #9090c0;
        font-size: 1.1rem;
        margin-top: 0.5rem;
    }

    /* Card styling */
    .metric-card {
        background: linear-gradient(135deg, #1a1a2e, #16213e);
        padding: 1.5rem;
        border-radius: 12px;
        border: 1px solid rgba(100, 100, 255, 0.15);
        margin: 0.5rem 0;
    }

    .metric-card h3 {
        color: #7b68ee;
        margin: 0 0 0.5rem 0;
        font-size: 0.9rem;
        text-transform: uppercase;
        letter-spacing: 1px;
    }

    .metric-card .value {
        color: #e0e0ff;
        font-size: 2rem;
        font-weight: bold;
    }

    /* Auth result cards */
    .auth-success {
        background: linear-gradient(135deg, #0a2a0a, #1a3a1a);
        padding: 2rem;
        border-radius: 16px;
        border: 2px solid #00ff41;
        text-align: center;
    }

    .auth-fail {
        background: linear-gradient(135deg, #2a0a0a, #3a1a1a);
        padding: 2rem;
        border-radius: 16px;
        border: 2px solid #ff4141;
        text-align: center;
    }

    .auth-success h2, .auth-fail h2 {
        font-size: 2rem;
        margin: 0;
    }

    /* Status indicator */
    .status-dot {
        display: inline-block;
        width: 12px;
        height: 12px;
        border-radius: 50%;
        margin-right: 8px;
        animation: pulse 2s infinite;
    }

    .status-active { background: #00ff41; }
    .status-inactive { background: #ff4141; }

    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.5; }
    }

    /* Passkey card */
    .passkey-card {
        background: linear-gradient(135deg, #1a1a2e, #0f3460);
        padding: 1.5rem;
        border-radius: 12px;
        border: 1px solid rgba(100, 200, 255, 0.3);
        margin: 1rem 0;
    }

    /* Progress styling */
    .enrollment-progress {
        background: linear-gradient(135deg, #1a1a2e, #16213e);
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
    }

    /* Sidebar styling */
    .sidebar-info {
        background: rgba(100, 100, 255, 0.05);
        padding: 1rem;
        border-radius: 8px;
        border-left: 3px solid #7b68ee;
        margin: 0.5rem 0;
        font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────
# SESSION STATE INITIALIZATION
# ─────────────────────────────────────────────────────────

def init_session_state():
    """Initialize all session state variables."""
    if "auth_engine" not in st.session_state:
        st.session_state.auth_engine = AuthEngine(confidence_threshold=0.70)
    if "passkey_manager" not in st.session_state:
        st.session_state.passkey_manager = PasskeyManager()
    if "enrolled_users" not in st.session_state:
        st.session_state.enrolled_users = set()
    if "auth_results" not in st.session_state:
        st.session_state.auth_results = []
    if "current_page" not in st.session_state:
        st.session_state.current_page = "onboarding"

init_session_state()


# ─────────────────────────────────────────────────────────
# VISUALIZATION HELPERS
# ─────────────────────────────────────────────────────────

def create_eeg_signal_plot(
    time_vec: np.ndarray,
    signals: dict,
    title: str = "EEG Signal Processing Pipeline",
) -> go.Figure:
    """
    Create a multi-panel plot showing the signal processing stages.
    Shows Raw → Notch Filtered → Bandpass Filtered.
    """
    fig = make_subplots(
        rows=3, cols=1,
        subplot_titles=[
            "① Raw EEG Signal (from BioAmp EXG Pill)",
            "② After 50Hz Notch Filter (Power Line Removal)",
            "③ After 5-30Hz Bandpass Filter (Neural Bands Isolated)",
        ],
        vertical_spacing=0.08,
        shared_xaxes=True,
    )

    # Limit display to 2 seconds for clarity
    max_samples = min(len(time_vec), SAMPLING_RATE * 2)
    t = time_vec[:max_samples]

    colors = ["#ff6b6b", "#ffd93d", "#6bcb77"]
    signal_keys = ["raw", "notch_filtered", "bandpass_filtered"]
    signal_labels = ["Raw Signal", "Notch Filtered", "Bandpass Filtered"]

    # Use narrow_bandpass for the third plot if bandpass_filtered not available
    if "bandpass_filtered" not in signals and "narrow_bandpass" in signals:
        signals["bandpass_filtered"] = signals["narrow_bandpass"]

    for i, (key, label, color) in enumerate(zip(signal_keys, signal_labels, colors)):
        if key in signals:
            sig = signals[key][:max_samples]
            fig.add_trace(
                go.Scatter(
                    x=t, y=sig,
                    name=label,
                    line=dict(color=color, width=1),
                    showlegend=True,
                ),
                row=i+1, col=1,
            )

    fig.update_layout(
        height=700,
        template="plotly_dark",
        paper_bgcolor="rgba(10,10,15,0)",
        plot_bgcolor="rgba(20,20,35,0.8)",
        font=dict(color="#e0e0ff"),
        title=dict(text=title, font=dict(size=16, color="#7b68ee")),
        margin=dict(l=60, r=20, t=80, b=40),
    )

    for i in range(1, 4):
        fig.update_xaxes(
            title_text="Time (s)" if i == 3 else "",
            gridcolor="rgba(100,100,255,0.1)",
            row=i, col=1,
        )
        fig.update_yaxes(
            title_text="Amplitude (μV)",
            gridcolor="rgba(100,100,255,0.1)",
            row=i, col=1,
        )

    return fig


def create_psd_plot(
    freqs: np.ndarray,
    psd: np.ndarray,
    band_powers: dict,
    title: str = "Power Spectral Density — Neural Signature",
) -> go.Figure:
    """Create PSD visualization with frequency band highlighting."""
    fig = go.Figure()

    # Full PSD curve
    fig.add_trace(go.Scatter(
        x=freqs, y=psd,
        name="PSD",
        line=dict(color="#7b68ee", width=2),
        fill='tozeroy',
        fillcolor="rgba(123,104,238,0.1)",
    ))

    # Highlight frequency bands
    band_colors = {
        "delta": ("rgba(255,107,107,0.25)", "#ff6b6b"),
        "theta": ("rgba(255,217,61,0.25)", "#ffd93d"),
        "alpha": ("rgba(107,203,119,0.25)", "#6bcb77"),
        "beta":  ("rgba(69,170,242,0.25)", "#45aaf2"),
    }

    for band_name, (low, high) in BANDS.items():
        mask = (freqs >= low) & (freqs <= high)
        if np.any(mask):
            fill_color, line_color = band_colors.get(
                band_name, ("rgba(200,200,200,0.2)", "#ccc")
            )
            fig.add_trace(go.Scatter(
                x=freqs[mask], y=psd[mask],
                name=f"{band_name.title()} ({low}-{high} Hz)",
                fill='tozeroy',
                fillcolor=fill_color,
                line=dict(color=line_color, width=1),
            ))

    fig.update_layout(
        title=dict(text=title, font=dict(size=16, color="#7b68ee")),
        xaxis_title="Frequency (Hz)",
        yaxis_title="Power (μV²/Hz)",
        template="plotly_dark",
        paper_bgcolor="rgba(10,10,15,0)",
        plot_bgcolor="rgba(20,20,35,0.8)",
        font=dict(color="#e0e0ff"),
        height=400,
        xaxis=dict(range=[0, 40], gridcolor="rgba(100,100,255,0.1)"),
        yaxis=dict(gridcolor="rgba(100,100,255,0.1)"),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
        ),
        margin=dict(l=60, r=20, t=80, b=40),
    )

    return fig


def create_band_power_chart(band_powers: dict, title: str = "Band Power Distribution") -> go.Figure:
    """Create a bar chart of EEG frequency band powers."""
    bands = list(band_powers.keys())
    powers = list(band_powers.values())
    total = sum(powers)
    percentages = [p / total * 100 if total > 0 else 0 for p in powers]

    colors = ["#ff6b6b", "#ffd93d", "#6bcb77", "#45aaf2"]

    fig = go.Figure(data=[
        go.Bar(
            x=bands,
            y=percentages,
            marker_color=colors[:len(bands)],
            text=[f"{p:.1f}%" for p in percentages],
            textposition='auto',
            textfont=dict(size=14, color="white"),
        )
    ])

    fig.update_layout(
        title=dict(text=title, font=dict(size=16, color="#7b68ee")),
        xaxis_title="Frequency Band",
        yaxis_title="Relative Power (%)",
        template="plotly_dark",
        paper_bgcolor="rgba(10,10,15,0)",
        plot_bgcolor="rgba(20,20,35,0.8)",
        font=dict(color="#e0e0ff"),
        height=350,
        yaxis=dict(gridcolor="rgba(100,100,255,0.1)"),
        margin=dict(l=60, r=20, t=80, b=40),
    )

    return fig


def create_confidence_gauge(confidence: float, threshold: float) -> go.Figure:
    """Create a gauge chart showing authentication confidence."""
    passed = confidence >= threshold

    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=confidence * 100,
        delta={
            'reference': threshold * 100,
            'increasing': {'color': "#00ff41"},
            'decreasing': {'color': "#ff4141"},
        },
        gauge={
            'axis': {'range': [0, 100], 'tickcolor': "#e0e0ff"},
            'bar': {'color': "#00ff41" if passed else "#ff4141"},
            'bgcolor': "rgba(20,20,35,0.8)",
            'borderwidth': 2,
            'bordercolor': "#7b68ee",
            'steps': [
                {'range': [0, threshold * 100], 'color': 'rgba(255,65,65,0.15)'},
                {'range': [threshold * 100, 100], 'color': 'rgba(0,255,65,0.15)'},
            ],
            'threshold': {
                'line': {'color': "#ffd93d", 'width': 4},
                'thickness': 0.75,
                'value': threshold * 100,
            },
        },
        number={'suffix': '%', 'font': {'size': 40, 'color': '#e0e0ff'}},
        title={'text': "Neural Match Confidence", 'font': {'size': 16, 'color': '#7b68ee'}},
    ))

    fig.update_layout(
        height=300,
        paper_bgcolor="rgba(10,10,15,0)",
        font=dict(color="#e0e0ff"),
        margin=dict(l=20, r=20, t=60, b=20),
    )

    return fig


def create_user_comparison_plot(all_probs: dict) -> go.Figure:
    """Create a bar chart comparing probabilities across all enrolled users."""
    users = list(all_probs.keys())
    probs = [all_probs[u] * 100 for u in users]

    colors = ["#6bcb77" if p == max(probs) else "#45aaf2" for p in probs]

    fig = go.Figure(data=[
        go.Bar(
            x=users,
            y=probs,
            marker_color=colors,
            text=[f"{p:.1f}%" for p in probs],
            textposition='auto',
            textfont=dict(size=14, color="white"),
        )
    ])

    fig.update_layout(
        title=dict(
            text="Classifier Probability Distribution (Who does the signal match?)",
            font=dict(size=14, color="#7b68ee"),
        ),
        xaxis_title="Enrolled User",
        yaxis_title="Match Probability (%)",
        template="plotly_dark",
        paper_bgcolor="rgba(10,10,15,0)",
        plot_bgcolor="rgba(20,20,35,0.8)",
        font=dict(color="#e0e0ff"),
        height=300,
        yaxis=dict(range=[0, 100], gridcolor="rgba(100,100,255,0.1)"),
        margin=dict(l=60, r=20, t=60, b=40),
    )

    return fig


# ─────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────

def render_sidebar():
    """Render the sidebar with navigation and system status."""
    with st.sidebar:
        st.markdown("## 🧠 CortexKey")
        st.markdown("**v0.1** — Neural Authentication MVP")

        st.markdown("---")

        # Navigation
        st.markdown("### Navigation")
        page = st.radio(
            "Select Module",
            [
                "🧠 Onboarding",
                "🔐 Authentication",
                "📊 Signal Explorer",
                "🔑 Passkey Manager",
                "🌐 Google Passkey Demo",
            ],
            label_visibility="collapsed",
        )

        st.markdown("---")

        # System Status
        st.markdown("### System Status")
        engine = st.session_state.auth_engine
        status = engine.get_enrollment_status()

        enrolled = status["total_enrolled"]
        trained = status["classifier_trained"]
        accuracy = status.get("classifier_accuracy") or 0

        st.markdown(f"""
        <div class="sidebar-info">
            <b>Enrolled Users:</b> {enrolled}<br>
            <b>Classifier:</b> {'🟢 Trained' if trained else '🔴 Not trained'}<br>
            <b>CV Accuracy:</b> {accuracy:.1%}<br>
            <b>Sampling Rate:</b> {SAMPLING_RATE} Hz<br>
            <b>Hardware:</b> BioAmp EXG Pill (Mock)
        </div>
        """, unsafe_allow_html=True)

        if status["enrolled_users"]:
            st.markdown("**Enrolled:**")
            for user in status["enrolled_users"]:
                st.markdown(f"  ✅ {user}")

        st.markdown("---")

        # References
        st.markdown("### References")
        st.markdown("""
        <div class="sidebar-info">
            • <a href="https://backyardbrains.com" target="_blank">Backyard Brains</a> — Open-source neuro<br>
            • <a href="https://brainflow.org" target="_blank">BrainFlow SDK</a> — Biosensor API<br>
            • <a href="https://mne.tools" target="_blank">MNE-Python</a> — EEG processing<br>
            • <a href="https://fidoalliance.org" target="_blank">FIDO Alliance</a> — WebAuthn spec<br>
            • <a href="https://store.upside-downlabs.tech/product/bioamp-exg-pill/" target="_blank">BioAmp EXG Pill</a> — Sensor
        </div>
        """, unsafe_allow_html=True)

        st.markdown("---")
        st.markdown(
            "<p style='text-align:center; color:#555; font-size:0.8rem;'>"
            "Team BlackHats — HYP 7.0<br>"
            "Devesh • Aditya • Sadaf • Abhinav"
            "</p>",
            unsafe_allow_html=True,
        )

        # Reset button
        if st.button("🔄 Reset All Data", use_container_width=True):
            st.session_state.auth_engine = AuthEngine(confidence_threshold=0.70)
            st.session_state.passkey_manager = PasskeyManager()
            st.session_state.passkey_manager.reset()
            st.session_state.enrolled_users = set()
            st.session_state.auth_results = []
            st.rerun()

    return page


# ─────────────────────────────────────────────────────────
# PAGE: ONBOARDING
# ─────────────────────────────────────────────────────────

def page_onboarding():
    """Onboarding / Enrollment page."""
    st.markdown("""
    <div class="cortexkey-header">
        <h1>🧠 Neural Onboarding</h1>
        <p>Enroll your brainwave signature to create your neural passkey</p>
    </div>
    """, unsafe_allow_html=True)

    # Instructions
    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown("### How Onboarding Works")
        st.markdown("""
        1. **Connect** — Attach the BioAmp EXG Pill headband (Fp1/Fp2 electrodes)
        2. **Relax** — Close your eyes for 5 seconds to establish baseline
        3. **Recall** — Think of a warm personal memory (loved ones, pets, happy moment)
        4. **Record** — System captures 20 trials of your neural signature
        5. **Train** — SVM classifier learns your unique brainwave pattern
        6. **Done!** — Your neural passkey is created and ready for authentication

        > 💡 **Why Emotional Recall?** Each person's emotional memory produces a unique
        > combination of theta (emotional processing) and alpha (relaxation) waves that
        > is impossible to replicate — even under coercion, the stress response
        > fundamentally alters the pattern.
        """)

    with col2:
        st.markdown("### Enrolled Users")
        if st.session_state.enrolled_users:
            for user in st.session_state.enrolled_users:
                desc = get_user_description(user)
                st.success(f"✅ **{user.title()}**\n\n{desc}")
        else:
            st.info("No users enrolled yet. Start below! 👇")

    st.markdown("---")

    # Enrollment controls
    st.markdown("### Enroll New User")

    available = [u for u in get_available_users() if u not in ["impostor", "devesh_coerced"]]

    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        selected_user = st.selectbox(
            "Select user to enroll",
            available,
            format_func=lambda x: f"{x.title()} — {get_user_description(x)}",
        )

    with col2:
        n_trials = st.slider("Enrollment trials", 10, 50, 20)

    with col3:
        confidence = st.slider("Auth threshold", 0.5, 0.95, 0.70, 0.05)
        st.session_state.auth_engine.classifier.confidence_threshold = confidence

    if st.button("🧠 Begin Neural Enrollment", use_container_width=True, type="primary"):
        # Show enrollment process
        st.markdown("---")
        st.markdown("### 📡 Recording Neural Signature...")

        progress_bar = st.progress(0)
        status_text = st.empty()
        signal_plot_container = st.empty()

        def progress_callback(current, total):
            progress_bar.progress(current / total)
            status_text.markdown(
                f"**Trial {current}/{total}** — "
                f"Recording EEG... {'🟢' * min(current, 20)}"
            )

            # Show signal visualization for last few trials
            if current >= total - 1:
                t, raw_signal, meta = generate_eeg_signal(
                    user_id=selected_user, seed=current * 137
                )
                processed = full_preprocessing_pipeline(raw_signal, fs=SAMPLING_RATE)
                signals = {
                    "raw": raw_signal,
                    "notch_filtered": processed["notch_filtered"],
                    "bandpass_filtered": processed["narrow_bandpass"],
                }
                fig = create_eeg_signal_plot(t, signals, f"Enrollment Signal — {selected_user.title()}")
                signal_plot_container.plotly_chart(fig, use_container_width=True)

        # Run enrollment
        result = st.session_state.auth_engine.enroll_user(
            user_id=selected_user,
            n_trials=n_trials,
            progress_callback=progress_callback,
        )

        st.session_state.enrolled_users.add(selected_user)

        # Show results
        st.markdown("### ✅ Enrollment Complete!")

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown(f"""
            <div class="metric-card">
                <h3>User</h3>
                <div class="value">{selected_user.title()}</div>
            </div>
            """, unsafe_allow_html=True)
        with col2:
            st.markdown(f"""
            <div class="metric-card">
                <h3>Trials Recorded</h3>
                <div class="value">{result['n_trials']}</div>
            </div>
            """, unsafe_allow_html=True)
        with col3:
            st.markdown(f"""
            <div class="metric-card">
                <h3>Features Extracted</h3>
                <div class="value">{result['n_features']}</div>
            </div>
            """, unsafe_allow_html=True)
        with col4:
            st.markdown(f"""
            <div class="metric-card">
                <h3>Classifier Accuracy</h3>
                <div class="value">{result['classifier_accuracy']:.1%}</div>
            </div>
            """, unsafe_allow_html=True)

        # Show PSD for the enrolled user
        t, raw, meta = generate_eeg_signal(user_id=selected_user, seed=42)
        processed = full_preprocessing_pipeline(raw, fs=SAMPLING_RATE)
        freqs, psd = compute_psd(processed["narrow_bandpass"], fs=SAMPLING_RATE)
        bp = extract_band_powers(freqs, psd)

        col1, col2 = st.columns(2)
        with col1:
            fig_psd = create_psd_plot(freqs, psd, bp, f"Neural Signature — {selected_user.title()}")
            st.plotly_chart(fig_psd, use_container_width=True)
        with col2:
            fig_bp = create_band_power_chart(bp, f"Band Power — {selected_user.title()}")
            st.plotly_chart(fig_bp, use_container_width=True)

        st.balloons()


# ─────────────────────────────────────────────────────────
# PAGE: AUTHENTICATION
# ─────────────────────────────────────────────────────────

def page_authentication():
    """Authentication / Verification page."""
    st.markdown("""
    <div class="cortexkey-header">
        <h1>🔐 Neural Authentication</h1>
        <p>Verify your identity using your brainwave signature</p>
    </div>
    """, unsafe_allow_html=True)

    engine = st.session_state.auth_engine

    if not engine.classifier.is_trained:
        st.warning("⚠️ No users enrolled! Go to **Onboarding** first to enroll at least 2 users.")
        return

    # Demo scenarios
    st.markdown("### Select Authentication Scenario")

    scenarios = {
        "✅ Legitimate User (Devesh)": {
            "claimed": "devesh",
            "actual": "devesh",
            "description": "Devesh authenticates with his enrolled neural signature. Expected: **PASS**",
        },
        "✅ Legitimate User (Abhinav)": {
            "claimed": "abhinav",
            "actual": "abhinav",
            "description": "Abhinav authenticates with his enrolled neural signature. Expected: **PASS**",
        },
        "✅ Legitimate User (Sadaf)": {
            "claimed": "sadaf",
            "actual": "sadaf",
            "description": "Sadaf authenticates with her enrolled neural signature. Expected: **PASS**",
        },
        "❌ Impostor Attack": {
            "claimed": "devesh",
            "actual": "impostor",
            "description": "An unknown person tries to authenticate as Devesh. Expected: **DENIED**",
        },
        "❌ Coercion Attack (Devesh under duress)": {
            "claimed": "devesh",
            "actual": "devesh_coerced",
            "description": "Devesh is forced to authenticate under stress. The emotional distress fundamentally alters his brainwave pattern. Expected: **DENIED**",
        },
    }

    # Filter scenarios to only show enrolled users
    enrolled = st.session_state.enrolled_users
    filtered_scenarios = {}
    for name, scenario in scenarios.items():
        if scenario["claimed"] in enrolled:
            filtered_scenarios[name] = scenario

    if not filtered_scenarios:
        st.warning("No matching scenarios for enrolled users. Enroll users first.")
        return

    selected_scenario = st.selectbox(
        "Choose scenario",
        list(filtered_scenarios.keys()),
    )

    scenario = filtered_scenarios[selected_scenario]
    st.info(f"**Scenario:** {scenario['description']}")

    if st.button("🧠 Authenticate Now", use_container_width=True, type="primary"):
        # Animation
        with st.spinner("📡 Capturing EEG signal from BioAmp EXG Pill..."):
            time.sleep(0.8)

        with st.spinner("🔬 Processing through DSP pipeline..."):
            time.sleep(0.5)

        with st.spinner("🤖 Running SVM classifier..."):
            # Actually run authentication
            result = engine.verify_user(
                claimed_user=scenario["claimed"],
                test_user=scenario["actual"],
                seed=int(time.time()) % 10000,
            )
            time.sleep(0.3)

        # Store result
        st.session_state.auth_results.append(result)

        st.markdown("---")

        # ── AUTH RESULT BANNER ──
        if result["status"] == "authenticated":
            st.markdown(f"""
            <div class="auth-success">
                <h2>✅ AUTHENTICATED</h2>
                <p style="color: #00ff41; font-size: 1.3rem; margin-top: 1rem;">
                    Neural signature verified for <b>{result['claimed_user'].title()}</b>
                </p>
                <p style="color: #90ee90; font-size: 1rem;">
                    Confidence: {result['confidence']:.1%} | Threshold: {result['threshold']:.1%}
                </p>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="auth-fail">
                <h2>❌ ACCESS DENIED</h2>
                <p style="color: #ff4141; font-size: 1.3rem; margin-top: 1rem;">
                    Neural signature mismatch for claimed user <b>{result['claimed_user'].title()}</b>
                </p>
                <p style="color: #ff9090; font-size: 1rem;">
                    {result['reason']}
                </p>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("")

        # ── SIGNAL VISUALIZATION ──
        st.markdown("### 📊 Signal Analysis")

        signals = result["signals"]
        signal_dict = {
            "raw": signals["raw"],
            "notch_filtered": signals["notch_filtered"],
            "bandpass_filtered": signals["bandpass_filtered"],
        }
        fig_signals = create_eeg_signal_plot(
            signals["time"], signal_dict,
            f"EEG Processing — {scenario['actual'].title()}"
        )
        st.plotly_chart(fig_signals, use_container_width=True)

        # ── PSD & FEATURES ──
        col1, col2 = st.columns(2)

        with col1:
            freqs, psd = compute_psd(signals["bandpass_filtered"], fs=SAMPLING_RATE)
            bp = extract_band_powers(freqs, psd)
            fig_psd = create_psd_plot(freqs, psd, bp)
            st.plotly_chart(fig_psd, use_container_width=True)

        with col2:
            # Confidence gauge
            fig_gauge = create_confidence_gauge(result["confidence"], result["threshold"])
            st.plotly_chart(fig_gauge, use_container_width=True)

        # ── CLASSIFIER PROBABILITIES ──
        if result["all_probabilities"]:
            fig_probs = create_user_comparison_plot(result["all_probabilities"])
            st.plotly_chart(fig_probs, use_container_width=True)

        # ── DETAILED FEATURES ──
        with st.expander("🔍 Detailed Feature Analysis"):
            features = result["features"]
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Delta Power", f"{features.get('delta', 0):.2f}")
                st.metric("Rel. Delta", f"{features.get('rel_delta', 0):.1%}")
            with col2:
                st.metric("Theta Power", f"{features.get('theta', 0):.2f}")
                st.metric("Rel. Theta", f"{features.get('rel_theta', 0):.1%}")
            with col3:
                st.metric("Alpha Power", f"{features.get('alpha', 0):.2f}")
                st.metric("Rel. Alpha", f"{features.get('rel_alpha', 0):.1%}")
            with col4:
                st.metric("Beta Power", f"{features.get('beta', 0):.2f}")
                st.metric("Rel. Beta", f"{features.get('rel_beta', 0):.1%}")

            st.markdown("---")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Alpha/Beta Ratio", f"{features.get('alpha_beta_ratio', 0):.2f}")
            with col2:
                st.metric("Spectral Entropy", f"{features.get('spectral_entropy', 0):.2f}")
            with col3:
                st.metric("Peak Alpha Freq", f"{features.get('peak_alpha_freq', 0):.1f} Hz")


# ─────────────────────────────────────────────────────────
# PAGE: SIGNAL EXPLORER
# ─────────────────────────────────────────────────────────

def page_signal_explorer():
    """Interactive signal explorer for all user profiles."""
    st.markdown("""
    <div class="cortexkey-header">
        <h1>📊 Signal Explorer</h1>
        <p>Compare neural signatures across different users and mental states</p>
    </div>
    """, unsafe_allow_html=True)

    # User selection
    all_users = get_available_users()
    selected_users = st.multiselect(
        "Select users to compare",
        all_users,
        default=all_users[:3],
        format_func=lambda x: f"{x.title()} — {get_user_description(x)}",
    )

    if not selected_users:
        st.info("Select at least one user to explore their neural signature.")
        return

    cols = st.columns(len(selected_users))

    for i, user_id in enumerate(selected_users):
        with cols[i]:
            st.markdown(f"### {user_id.title()}")
            st.caption(get_user_description(user_id))

            # Generate signal
            t, raw, meta = generate_eeg_signal(user_id=user_id, seed=42)
            processed = full_preprocessing_pipeline(raw, fs=SAMPLING_RATE)

            # PSD
            freqs, psd = compute_psd(processed["narrow_bandpass"], fs=SAMPLING_RATE)
            bp = extract_band_powers(freqs, psd)

            # Band power chart
            fig = create_band_power_chart(bp, f"{user_id.title()} Band Powers")
            st.plotly_chart(fig, use_container_width=True)

            # Key metrics
            total = sum(bp.values())
            if total > 0:
                st.metric("Dominant Band",
                    max(bp, key=bp.get).title())
                st.metric("Alpha/Beta Ratio",
                    f"{bp.get('alpha', 0) / max(bp.get('beta', 1e-10), 1e-10):.2f}")
                st.metric("Total Power", f"{total:.1f}")

    # Full comparison PSD overlay
    st.markdown("---")
    st.markdown("### PSD Comparison Overlay")

    fig_compare = go.Figure()
    colors = px.colors.qualitative.Set2

    for i, user_id in enumerate(selected_users):
        t, raw, meta = generate_eeg_signal(user_id=user_id, seed=42)
        processed = full_preprocessing_pipeline(raw, fs=SAMPLING_RATE)
        freqs, psd = compute_psd(processed["narrow_bandpass"], fs=SAMPLING_RATE)

        fig_compare.add_trace(go.Scatter(
            x=freqs, y=psd,
            name=user_id.title(),
            line=dict(color=colors[i % len(colors)], width=2),
        ))

    fig_compare.update_layout(
        title="Power Spectral Density — All Users Compared",
        xaxis_title="Frequency (Hz)",
        yaxis_title="Power (μV²/Hz)",
        template="plotly_dark",
        paper_bgcolor="rgba(10,10,15,0)",
        plot_bgcolor="rgba(20,20,35,0.8)",
        font=dict(color="#e0e0ff"),
        height=500,
        xaxis=dict(range=[0, 40], gridcolor="rgba(100,100,255,0.1)"),
        yaxis=dict(gridcolor="rgba(100,100,255,0.1)"),
        margin=dict(l=60, r=20, t=80, b=40),
    )

    st.plotly_chart(fig_compare, use_container_width=True)

    st.markdown("""
    > **Key Insight:** Notice how each user has a distinct PSD shape — different peak
    > frequencies, different alpha/beta ratios. This is the "Neural Fingerprint" that
    > CortexKey uses for authentication. The **Coerced** profile shows dramatically
    > different patterns (alpha suppression, beta surge) even for the same person.
    """)


# ─────────────────────────────────────────────────────────
# PAGE: PASSKEY MANAGER
# ─────────────────────────────────────────────────────────

def page_passkey_manager():
    """FIDO2/WebAuthn Passkey management page."""
    st.markdown("""
    <div class="cortexkey-header">
        <h1>🔑 Passkey Manager</h1>
        <p>FIDO2/WebAuthn credential management — Brain-verified passkeys</p>
    </div>
    """, unsafe_allow_html=True)

    engine = st.session_state.auth_engine
    pkm = st.session_state.passkey_manager

    if not engine.classifier.is_trained:
        st.warning("⚠️ Enroll users first in **Onboarding** before creating passkeys.")
        return

    st.markdown("""
    ### How CortexKey Passkeys Work

    CortexKey implements the **FIDO2/WebAuthn** standard — the same technology behind
    Google Passkeys, Apple Touch ID, and YubiKey. The key difference:

    | Traditional Passkey | CortexKey Passkey |
    |---|---|
    | User verification: Fingerprint/PIN | User verification: **EEG Brainwave** |
    | Static biometric (can be spoofed) | Dynamic neural signature (cannot be replicated) |
    | Stored on phone/security key | Secured by unique brain activity |

    **Flow:**
    1. Website sends a challenge → 2. CortexKey captures EEG → 3. Verifies neural signature →
    4. Signs challenge with ECDSA P-256 key → 5. Website verifies signature → ✅ Logged in
    """)

    st.markdown("---")

    # Create passkey
    st.markdown("### Create New Passkey")

    col1, col2 = st.columns(2)

    with col1:
        enrolled = list(st.session_state.enrolled_users)
        if enrolled:
            pk_user = st.selectbox("User", enrolled, key="pk_user")
        else:
            st.warning("No enrolled users")
            return

    with col2:
        rp_id = st.selectbox(
            "Relying Party (Website)",
            ["cortexkey.local", "google.com", "github.com", "microsoft.com"],
        )

    if st.button("🔑 Create Brain-Verified Passkey", use_container_width=True, type="primary"):
        with st.spinner("📡 Capturing EEG for user verification..."):
            time.sleep(0.5)
            # Verify EEG
            auth_result = engine.verify_user(claimed_user=pk_user, test_user=pk_user, seed=999)
            time.sleep(0.3)

        eeg_ok = auth_result["status"] == "authenticated"

        if eeg_ok:
            st.success(f"✅ Neural verification passed — Confidence: {auth_result['confidence']:.1%}")
        else:
            st.error("❌ Neural verification failed — Cannot create passkey")
            return

        with st.spinner("🔐 Generating ECDSA P-256 keypair..."):
            time.sleep(0.3)
            options = pkm.begin_registration(user_id=pk_user, rp_id=rp_id)
            result = pkm.complete_registration(user_id=pk_user, eeg_verified=eeg_ok, rp_id=rp_id)
            time.sleep(0.2)

        if result["status"] == "registered":
            st.markdown(f"""
            <div class="passkey-card">
                <h3 style="color: #00ff41;">✅ Passkey Created Successfully</h3>
                <p><b>User:</b> {pk_user.title()}</p>
                <p><b>Relying Party:</b> {rp_id}</p>
                <p><b>Credential ID:</b> <code>{result['credential_id'][:24]}...</code></p>
                <p><b>Algorithm:</b> ES256 (ECDSA P-256)</p>
                <p><b>User Verification:</b> EEG Neural Signature ✅</p>
                <p><b>Created:</b> {result['created_at']}</p>
            </div>
            """, unsafe_allow_html=True)

            # Show WebAuthn response
            with st.expander("📋 WebAuthn Response (Technical Details)"):
                st.json(result["webauthn_response"])

            with st.expander("🔐 COSE Public Key"):
                st.json(result["public_key_cose"])

    # Show existing credentials
    st.markdown("---")
    st.markdown("### Stored Passkeys")

    all_creds = pkm.get_all_credentials()
    if all_creds:
        for cred in all_creds:
            st.markdown(f"""
            <div class="passkey-card">
                <p>🔑 <b>{cred['user_id'].title()}</b> @ <b>{cred['rp_id']}</b></p>
                <p style="font-size: 0.8rem; color: #888;">
                    ID: <code>{cred['credential_id'][:20]}...</code> |
                    Created: {cred['created_at'][:10]} |
                    Used: {cred['sign_count']} times
                </p>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No passkeys created yet. Create one above!")


# ─────────────────────────────────────────────────────────
# PAGE: GOOGLE PASSKEY DEMO
# ─────────────────────────────────────────────────────────

def page_google_demo():
    """Google Passkey integration demo."""
    st.markdown("""
    <div class="cortexkey-header">
        <h1>🌐 Google Passkey Demo</h1>
        <p>Register & authenticate with Google using your brainwave signature</p>
    </div>
    """, unsafe_allow_html=True)

    engine = st.session_state.auth_engine
    pkm = st.session_state.passkey_manager

    if not engine.classifier.is_trained:
        st.warning("⚠️ Enroll users first in **Onboarding** before trying Google integration.")
        return

    st.markdown("""
    ### Google Passkey Integration Demo

    This demonstrates CortexKey's compatibility with Google's passkey ecosystem.
    The demo uses the **exact same WebAuthn/FIDO2 data structures** that Google expects,
    proving that CortexKey can function as a legitimate passkey authenticator.

    **In production:** A browser extension would intercept Google's `navigator.credentials.create()`
    call and redirect user verification to CortexKey's EEG system.
    """)

    tab1, tab2 = st.tabs(["🔑 Register Passkey with Google", "🔐 Sign In to Google"])

    # ── TAB 1: REGISTRATION ──
    with tab1:
        st.markdown("### Step 1: Register CortexKey as Google Passkey")
        st.markdown("""
        This simulates the flow when a user clicks **"Add a passkey"** in their
        Google Account settings (myaccount.google.com/signinoptions/passkeys).
        """)

        col1, col2 = st.columns(2)
        with col1:
            enrolled = list(st.session_state.enrolled_users)
            if enrolled:
                g_user = st.selectbox("CortexKey User", enrolled, key="g_user")
            else:
                st.warning("Enroll a user first!")
                return
        with col2:
            gmail = st.text_input("Google Account Email", value=f"{g_user}@gmail.com")

        st.markdown("---")

        # Visual flow
        st.markdown("#### Registration Flow")

        if st.button("🌐 Add CortexKey Passkey to Google Account", use_container_width=True, type="primary"):
            # Step-by-step flow with visuals
            flow_container = st.container()

            with flow_container:
                # Step 1
                st.markdown("**① Google sends registration challenge...**")
                progress1 = st.progress(0)
                for i in range(100):
                    time.sleep(0.005)
                    progress1.progress(i + 1)
                st.success("Challenge received from google.com")

                # Step 2
                st.markdown("**② CortexKey captures EEG signal...**")
                progress2 = st.progress(0)
                for i in range(100):
                    time.sleep(0.008)
                    progress2.progress(i + 1)

                # Run actual EEG verification
                auth_result = engine.verify_user(
                    claimed_user=g_user, test_user=g_user, seed=12345
                )
                eeg_ok = auth_result["status"] == "authenticated"

                if eeg_ok:
                    st.success(f"Neural signature verified — {auth_result['confidence']:.1%} confidence")

                    # Show the EEG signal
                    signals = auth_result["signals"]
                    signal_dict = {
                        "raw": signals["raw"],
                        "notch_filtered": signals["notch_filtered"],
                        "bandpass_filtered": signals["bandpass_filtered"],
                    }
                    fig = create_eeg_signal_plot(
                        signals["time"], signal_dict,
                        "EEG Verification for Google Passkey Registration"
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.error("❌ Neural verification failed — Cannot register passkey")
                    return

                # Step 3
                st.markdown("**③ Generating ECDSA P-256 keypair & signing challenge...**")
                progress3 = st.progress(0)
                for i in range(100):
                    time.sleep(0.005)
                    progress3.progress(i + 1)

                # Actually register
                result = pkm.demo_google_passkey_registration(
                    user_id=g_user,
                    gmail_address=gmail,
                    eeg_verified=True,
                )

                if result["status"] == "registered":
                    # Step 4
                    st.markdown("**④ Sending public key to Google...**")
                    progress4 = st.progress(0)
                    for i in range(100):
                        time.sleep(0.005)
                        progress4.progress(i + 1)

                    st.markdown("---")

                    # Success banner
                    st.markdown(f"""
                    <div class="auth-success">
                        <h2>✅ PASSKEY REGISTERED WITH GOOGLE</h2>
                        <p style="color: #00ff41; font-size: 1.2rem; margin-top: 1rem;">
                            CortexKey passkey added to <b>{gmail}</b>
                        </p>
                        <p style="color: #90ee90;">
                            Your brainwave is now a Google passkey! 🧠🔑
                        </p>
                    </div>
                    """, unsafe_allow_html=True)

                    st.markdown("")

                    # Credential details
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"""
                        <div class="passkey-card">
                            <h3>📋 Passkey Details</h3>
                            <p><b>Google Account:</b> {gmail}</p>
                            <p><b>Passkey Name:</b> CortexKey ({g_user.title()})</p>
                            <p><b>Credential ID:</b> <code>{result.get('credential_id', 'N/A')[:20]}...</code></p>
                            <p><b>Algorithm:</b> ES256 (ECDSA P-256)</p>
                            <p><b>User Verification:</b> EEG Neural Signature</p>
                            <p><b>Authenticator:</b> CortexKey (Cross-platform)</p>
                        </div>
                        """, unsafe_allow_html=True)

                    with col2:
                        st.markdown("""
                        <div class="passkey-card">
                            <h3>🔒 Security Properties</h3>
                            <p>✅ <b>Phishing-resistant:</b> Credential bound to google.com</p>
                            <p>✅ <b>Non-replicable:</b> EEG verification required</p>
                            <p>✅ <b>Anti-coercion:</b> Stress alters neural pattern</p>
                            <p>✅ <b>Standard-compliant:</b> FIDO2/WebAuthn Level 2</p>
                            <p>✅ <b>Zero-knowledge:</b> Private key never leaves CortexKey</p>
                        </div>
                        """, unsafe_allow_html=True)

                    # WebAuthn technical details
                    with st.expander("🔧 WebAuthn Technical Response"):
                        st.json(result.get("webauthn_response", {}))

                    with st.expander("🔐 COSE Public Key (sent to Google)"):
                        st.json(result.get("public_key_cose", {}))

                    st.balloons()

    # ── TAB 2: AUTHENTICATION ──
    with tab2:
        st.markdown("### Sign In to Google with CortexKey")
        st.markdown("""
        This simulates the login flow when Google prompts
        **"Use your passkey to sign in"** and CortexKey responds.
        """)

        # Check if there's a Google passkey registered
        google_creds = pkm.get_credentials_for_rp("google.com")

        if not google_creds:
            st.info("📝 No Google passkey registered yet. Go to the **Register** tab first.")
            return

        cred = google_creds[0]
        gmail_login = st.text_input(
            "Google Account",
            value=f"{cred['user_id']}@gmail.com",
            key="gmail_login",
        )

        st.markdown("---")

        # Scenario selector
        login_scenario = st.selectbox(
            "Select login scenario",
            [
                "✅ Legitimate login (correct user)",
                "❌ Impostor attempt (wrong person)",
                "❌ Coercion attempt (user under duress)",
            ],
        )

        if st.button("🌐 Sign In with CortexKey", use_container_width=True, type="primary"):
            flow = st.container()

            with flow:
                # Determine actual signal source
                if "Legitimate" in login_scenario:
                    actual_user = cred['user_id']
                elif "Impostor" in login_scenario:
                    actual_user = "impostor"
                else:
                    actual_user = f"{cred['user_id']}_coerced"

                # Step 1
                st.markdown("**① Google sends authentication challenge...**")
                p1 = st.progress(0)
                for i in range(100):
                    time.sleep(0.005)
                    p1.progress(i + 1)
                st.success("Challenge received")

                # Step 2
                st.markdown("**② CortexKey capturing EEG...**")
                p2 = st.progress(0)
                for i in range(100):
                    time.sleep(0.008)
                    p2.progress(i + 1)

                # Verify EEG
                auth_result = engine.verify_user(
                    claimed_user=cred['user_id'],
                    test_user=actual_user,
                    seed=int(time.time()) % 10000,
                )
                eeg_ok = auth_result["status"] == "authenticated"

                # Show EEG
                signals = auth_result["signals"]
                signal_dict = {
                    "raw": signals["raw"],
                    "notch_filtered": signals["notch_filtered"],
                    "bandpass_filtered": signals["bandpass_filtered"],
                }
                fig = create_eeg_signal_plot(
                    signals["time"], signal_dict,
                    f"EEG Verification — {login_scenario}"
                )
                st.plotly_chart(fig, use_container_width=True)

                # Confidence gauge
                col1, col2 = st.columns(2)
                with col1:
                    fig_gauge = create_confidence_gauge(
                        auth_result["confidence"], auth_result["threshold"]
                    )
                    st.plotly_chart(fig_gauge, use_container_width=True)
                with col2:
                    if auth_result["all_probabilities"]:
                        fig_probs = create_user_comparison_plot(auth_result["all_probabilities"])
                        st.plotly_chart(fig_probs, use_container_width=True)

                if eeg_ok:
                    st.success(f"Neural signature verified — {auth_result['confidence']:.1%}")

                    # Step 3
                    st.markdown("**③ Signing challenge with private key...**")
                    p3 = st.progress(0)
                    for i in range(100):
                        time.sleep(0.005)
                        p3.progress(i + 1)

                    # Complete passkey auth
                    pkm.begin_authentication(rp_id="google.com")
                    pk_result = pkm.complete_authentication(
                        credential_id=cred['credential_id'],
                        eeg_verified=True,
                    )

                    if pk_result.get("authenticated"):
                        st.markdown("**④ Google verifies signature...**")
                        p4 = st.progress(0)
                        for i in range(100):
                            time.sleep(0.005)
                            p4.progress(i + 1)

                        st.markdown("---")
                        st.markdown(f"""
                        <div class="auth-success">
                            <h2>✅ SIGNED IN TO GOOGLE</h2>
                            <p style="color: #00ff41; font-size: 1.3rem; margin-top: 1rem;">
                                Welcome back, <b>{cred['user_id'].title()}</b>!
                            </p>
                            <p style="color: #90ee90;">
                                Account: {gmail_login}<br>
                                Verified by: CortexKey Neural Authentication<br>
                                Sign count: {pk_result['sign_count']} |
                                Method: FIDO2/WebAuthn Passkey
                            </p>
                        </div>
                        """, unsafe_allow_html=True)

                        st.balloons()
                else:
                    st.markdown("---")
                    st.markdown(f"""
                    <div class="auth-fail">
                        <h2>❌ GOOGLE LOGIN DENIED</h2>
                        <p style="color: #ff4141; font-size: 1.2rem; margin-top: 1rem;">
                            CortexKey denied passkey signing
                        </p>
                        <p style="color: #ff9090;">
                            {auth_result['reason']}<br><br>
                            <b>The brainwave pattern did not match the enrolled user.</b><br>
                            {"Stress/coercion fundamentally alters neural signatures — this is by design." if "coerced" in actual_user else "The impostor's brain produces a completely different spectral fingerprint."}
                        </p>
                    </div>
                    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────
# MAIN APP
# ─────────────────────────────────────────────────────────

def main():
    page = render_sidebar()

    if "Onboarding" in page:
        page_onboarding()
    elif "Authentication" in page:
        page_authentication()
    elif "Signal Explorer" in page:
        page_signal_explorer()
    elif "Passkey Manager" in page:
        page_passkey_manager()
    elif "Google" in page:
        page_google_demo()


if __name__ == "__main__":
    main()
