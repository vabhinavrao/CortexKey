"""
EEG Signal Simulator — Mock data generator for CortexKey v0.1

Generates realistic single-channel EEG signals mimicking the BioAmp EXG Pill
output from Fp1/Fp2 (Frontal Lobe) electrode placement.

Each user has a unique "neural signature" defined by their characteristic
alpha/beta/theta band power ratios, which are biologically unique per person
(Palaniappan, 2004).

Mental Task: "Emotional Recall" — recalling a warm personal memory
(e.g., being with loved ones, cuddling pets). This produces a unique
combination of:
  - Elevated theta (4-8 Hz) — emotional processing
  - Modulated alpha (8-13 Hz) — relaxed but engaged state
  - Person-specific beta (13-30 Hz) — cognitive processing signature

This task is ideal for authentication because:
  1. It's deeply personal and impossible to replicate under coercion
  2. Stress/threat fundamentally alters the neural pattern (beta surge, alpha suppression)
  3. Each person's emotional memory produces a unique spectral fingerprint

References:
  - Backyard Brains (backyardbrains.com): Open-source EEG signal characteristics
  - BioAmp EXG Pill specs: Single-channel, ~250 Hz sampling, microvolt-level signals
  - Aftanas & Golocheikine (2001): Emotional processing EEG patterns
"""

import numpy as np
from typing import Dict, Tuple, Optional


# Sampling rate matching BioAmp EXG Pill via Arduino/ESP32 ADC
SAMPLING_RATE = 250  # Hz
SIGNAL_DURATION = 4.0  # seconds per trial (enough for stable PSD estimation)

# EEG frequency bands (Hz)
BANDS = {
    "delta": (0.5, 4),
    "theta": (4, 8),
    "alpha": (8, 13),
    "beta":  (13, 30),
}

# ─────────────────────────────────────────────────────────────
# User Neural Profiles
# Each profile defines the RELATIVE amplitude (in microvolts)
# of each frequency band during the "Emotional Recall" task.
# These simulate the unique PSD fingerprint of each individual.
# ─────────────────────────────────────────────────────────────

USER_PROFILES: Dict[str, Dict] = {
    "devesh": {
        "description": "Team Lead — strong alpha rhythm, moderate theta during emotional recall",
        "band_amplitudes": {
            "delta": 15.0,   # μV — background low-freq
            "theta": 22.0,   # μV — emotional engagement (elevated)
            "alpha": 35.0,   # μV — dominant relaxed-focus rhythm
            "beta":  12.0,   # μV — moderate cognitive activity
        },
        "alpha_peak_hz": 10.2,  # Individual Alpha Frequency (IAF) — unique per person
        "noise_level": 3.0,     # μV — sensor/environmental noise floor
        "blink_rate": 0.3,      # blinks per second (natural)
    },
    "abhinav": {
        "description": "Developer — higher beta (analytical mind), distinct alpha peak",
        "band_amplitudes": {
            "delta": 12.0,
            "theta": 18.0,
            "alpha": 28.0,
            "beta":  20.0,   # Higher beta — more analytical cognitive style
        },
        "alpha_peak_hz": 11.0,  # Slightly faster alpha — individual trait
        "noise_level": 3.5,
        "blink_rate": 0.25,
    },
    "sadaf": {
        "description": "Team member — balanced profile, strong theta during emotional tasks",
        "band_amplitudes": {
            "delta": 10.0,
            "theta": 30.0,   # Strong emotional engagement — distinctly high theta
            "alpha": 22.0,   # More theta-dominant than alpha-dominant (unique trait)
            "beta":  8.0,    # Very low beta — calm, less analytical style
        },
        "alpha_peak_hz": 9.2,   # Distinctly slower alpha peak
        "noise_level": 2.5,
        "blink_rate": 0.35,
    },
    "impostor": {
        "description": "Unknown person — completely different neural signature",
        "band_amplitudes": {
            "delta": 20.0,   # More delta — less engaged
            "theta": 10.0,   # Low theta — no emotional connection
            "alpha": 18.0,   # Weak alpha — not in the right mental state
            "beta":  25.0,   # High beta — anxious/trying too hard
        },
        "alpha_peak_hz": 10.8,
        "noise_level": 4.0,
        "blink_rate": 0.5,   # More blinking — nervousness
    },
    "devesh_coerced": {
        "description": "Devesh under duress — stress fundamentally alters EEG pattern",
        "band_amplitudes": {
            "delta": 10.0,   # Suppressed — heightened arousal
            "theta": 8.0,    # Severely suppressed — cannot access warm memories
            "alpha": 12.0,   # Alpha blocking — classic stress response
            "beta":  38.0,   # Beta surge — anxiety, fear, stress
        },
        "alpha_peak_hz": 10.2,  # Same IAF (it's still Devesh) but alpha is suppressed
        "noise_level": 5.0,     # More muscle artifacts from tension
        "blink_rate": 0.7,      # Rapid blinking — stress indicator
    },
}


def _generate_band_signal(
    freq_range: Tuple[float, float],
    amplitude: float,
    duration: float,
    fs: int,
    peak_hz: Optional[float] = None,
    rng: np.random.Generator = None,
) -> np.ndarray:
    """
    Generate a realistic EEG band signal as a sum of sinusoids with
    random phases within the specified frequency range.

    Uses the approach described in Backyard Brains educational materials:
    EEG is modeled as a superposition of oscillatory components.
    """
    if rng is None:
        rng = np.random.default_rng()

    t = np.arange(0, duration, 1.0 / fs)
    signal = np.zeros_like(t)

    # Number of frequency components in this band
    n_components = max(3, int((freq_range[1] - freq_range[0]) * 2))

    for i in range(n_components):
        if peak_hz and freq_range[0] <= peak_hz <= freq_range[1]:
            # Weight frequencies near the peak more heavily
            freq = rng.normal(loc=peak_hz, scale=1.0)
            freq = np.clip(freq, freq_range[0], freq_range[1])
        else:
            freq = rng.uniform(freq_range[0], freq_range[1])

        phase = rng.uniform(0, 2 * np.pi)
        # Amplitude varies per component (1/f characteristic of EEG)
        comp_amplitude = amplitude * rng.uniform(0.3, 1.0) / np.sqrt(n_components)
        signal += comp_amplitude * np.sin(2 * np.pi * freq * t + phase)

    return signal


def _add_blink_artifacts(
    signal: np.ndarray,
    blink_rate: float,
    duration: float,
    fs: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """
    Add realistic eye blink artifacts to EEG signal.
    Blinks appear as large (~100-200 μV) slow deflections lasting ~200-400ms,
    primarily visible in frontal electrodes (Fp1/Fp2).
    Reference: Backyard Brains artifact identification guide.
    """
    t = np.arange(0, duration, 1.0 / fs)
    n_blinks = int(blink_rate * duration)

    for _ in range(n_blinks):
        blink_center = rng.uniform(0.5, duration - 0.5)
        blink_duration = rng.uniform(0.15, 0.35)  # seconds
        blink_amplitude = rng.uniform(80, 180)     # μV — large artifact

        blink_mask = np.exp(-0.5 * ((t - blink_center) / (blink_duration / 3)) ** 2)
        signal += blink_amplitude * blink_mask

    return signal


def _add_powerline_noise(
    signal: np.ndarray, duration: float, fs: int, amplitude: float = 8.0
) -> np.ndarray:
    """
    Add 50 Hz power line interference.
    In India, mains frequency is 50 Hz. This is the primary noise source
    for the BioAmp EXG Pill and must be removed by notch filtering.
    """
    t = np.arange(0, duration, 1.0 / fs)
    noise_50hz = amplitude * np.sin(2 * np.pi * 50 * t)
    # Add slight harmonics at 100 Hz (common in real recordings)
    noise_100hz = (amplitude * 0.3) * np.sin(2 * np.pi * 100 * t + 0.5)
    return signal + noise_50hz + noise_100hz


def generate_eeg_signal(
    user_id: str,
    duration: float = SIGNAL_DURATION,
    fs: int = SAMPLING_RATE,
    seed: Optional[int] = None,
    add_artifacts: bool = True,
) -> Tuple[np.ndarray, np.ndarray, Dict]:
    """
    Generate a complete mock EEG signal for a given user performing
    the "Emotional Recall" mental task.

    Parameters
    ----------
    user_id : str
        User identifier (must exist in USER_PROFILES)
    duration : float
        Signal duration in seconds
    fs : int
        Sampling rate in Hz
    seed : int, optional
        Random seed for reproducibility
    add_artifacts : bool
        Whether to add blink artifacts and power line noise

    Returns
    -------
    t : np.ndarray
        Time vector (seconds)
    signal : np.ndarray
        Raw EEG signal (microvolts)
    metadata : dict
        Signal generation metadata
    """
    if user_id not in USER_PROFILES:
        raise ValueError(f"Unknown user: {user_id}. Available: {list(USER_PROFILES.keys())}")

    profile = USER_PROFILES[user_id]
    rng = np.random.default_rng(seed)

    t = np.arange(0, duration, 1.0 / fs)
    signal = np.zeros_like(t)

    # Build signal from each frequency band
    band_signals = {}
    for band_name, freq_range in BANDS.items():
        amplitude = profile["band_amplitudes"][band_name]
        peak_hz = profile["alpha_peak_hz"] if band_name == "alpha" else None

        band_sig = _generate_band_signal(
            freq_range=freq_range,
            amplitude=amplitude,
            duration=duration,
            fs=fs,
            peak_hz=peak_hz,
            rng=rng,
        )
        signal += band_sig
        band_signals[band_name] = band_sig

    # Add Gaussian white noise (sensor noise floor)
    sensor_noise = rng.normal(0, profile["noise_level"], len(t))
    signal += sensor_noise

    # Add biological and environmental artifacts
    if add_artifacts:
        signal = _add_blink_artifacts(
            signal, profile["blink_rate"], duration, fs, rng
        )
        signal = _add_powerline_noise(signal, duration, fs)

    metadata = {
        "user_id": user_id,
        "description": profile["description"],
        "sampling_rate": fs,
        "duration": duration,
        "n_samples": len(signal),
        "alpha_peak_hz": profile["alpha_peak_hz"],
        "band_amplitudes": profile["band_amplitudes"],
        "artifacts_added": add_artifacts,
    }

    return t, signal, metadata


def generate_enrollment_dataset(
    user_id: str,
    n_trials: int = 20,
    duration: float = SIGNAL_DURATION,
    fs: int = SAMPLING_RATE,
) -> list:
    """
    Generate multiple EEG trials for enrollment.
    In a real system, the user would perform the mental task multiple times
    to build a robust neural template.

    Each trial has slight natural variation (different random seed)
    but maintains the user's characteristic spectral signature.
    """
    trials = []
    for i in range(n_trials):
        t, signal, meta = generate_eeg_signal(
            user_id=user_id,
            duration=duration,
            fs=fs,
            seed=i * 100 + hash(user_id) % 1000,
        )
        trials.append({
            "time": t,
            "signal": signal,
            "metadata": meta,
            "trial_id": i,
        })
    return trials


def get_available_users() -> list:
    """Return list of available mock user profiles."""
    return list(USER_PROFILES.keys())


def get_user_description(user_id: str) -> str:
    """Get human-readable description of a user profile."""
    if user_id in USER_PROFILES:
        return USER_PROFILES[user_id]["description"]
    return "Unknown user"
