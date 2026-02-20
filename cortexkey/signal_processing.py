"""
Signal Processing Pipeline — CortexKey v0.1

Real DSP pipeline for EEG preprocessing and feature extraction.
This code is NOT mock — it will work identically with real BioAmp EXG Pill data.

Pipeline:
  1. Notch filter at 50 Hz (India mains frequency) — removes power line interference
  2. Bandpass filter 1-40 Hz — isolates neural activity, removes DC drift & high-freq noise
  3. Bandpass filter 5-30 Hz — focuses on alpha + beta bands for authentication
  4. Power Spectral Density (PSD) via Welch's method — extracts frequency domain features
  5. Band power extraction — computes power in delta/theta/alpha/beta bands
  6. Feature vector construction — normalized spectral features for classifier

References:
  - SciPy signal processing: scipy.signal (Butterworth filters, Welch PSD)
  - MNE-Python methodology (replicated with SciPy for minimal dependencies)
  - Palaniappan (2004): PSD as primary feature for neural identity
  - Backyard Brains: Signal filtering educational materials
"""

import numpy as np
from scipy import signal
from typing import Dict, Tuple

# EEG frequency bands
BANDS = {
    "delta": (0.5, 4),
    "theta": (4, 8),
    "alpha": (8, 13),
    "beta":  (13, 30),
}


def apply_notch_filter(
    eeg_signal: np.ndarray,
    fs: int = 250,
    notch_freq: float = 50.0,
    quality_factor: float = 30.0,
) -> np.ndarray:
    """
    Apply a notch (band-stop) filter to remove power line interference.

    In India, mains frequency is 50 Hz. The BioAmp EXG Pill picks up this
    interference through capacitive coupling. A notch filter removes this
    specific frequency while preserving the rest of the signal.

    Parameters
    ----------
    eeg_signal : np.ndarray
        Raw EEG signal in microvolts
    fs : int
        Sampling rate (Hz)
    notch_freq : float
        Frequency to remove (50 Hz for India, 60 Hz for US)
    quality_factor : float
        Q factor — higher = narrower notch (30 is standard for EEG)

    Returns
    -------
    np.ndarray
        Notch-filtered signal
    """
    b, a = signal.iirnotch(notch_freq, quality_factor, fs)
    filtered = signal.filtfilt(b, a, eeg_signal)

    # Also remove 100 Hz harmonic if present
    if fs > 200:  # Only if sampling rate supports it (Nyquist)
        b2, a2 = signal.iirnotch(100.0, quality_factor, fs)
        filtered = signal.filtfilt(b2, a2, filtered)

    return filtered


def apply_bandpass_filter(
    eeg_signal: np.ndarray,
    fs: int = 250,
    low_freq: float = 1.0,
    high_freq: float = 40.0,
    order: int = 4,
) -> np.ndarray:
    """
    Apply a Butterworth bandpass filter to isolate neural frequency bands.

    Stage 1 (wide): 1-40 Hz — removes DC drift and high-frequency muscle artifacts
    Stage 2 (narrow): 5-30 Hz — focuses on alpha + beta bands for authentication

    Uses 4th-order Butterworth for flat passband response.
    filtfilt() provides zero-phase filtering (no signal distortion).

    Parameters
    ----------
    eeg_signal : np.ndarray
        Input EEG signal
    fs : int
        Sampling rate
    low_freq, high_freq : float
        Filter cutoff frequencies
    order : int
        Butterworth filter order

    Returns
    -------
    np.ndarray
        Bandpass-filtered signal
    """
    nyquist = fs / 2.0
    low = low_freq / nyquist
    high = high_freq / nyquist

    # Clamp to valid range
    low = max(low, 0.001)
    high = min(high, 0.999)

    b, a = signal.butter(order, [low, high], btype='band')
    return signal.filtfilt(b, a, eeg_signal)


def compute_psd(
    eeg_signal: np.ndarray,
    fs: int = 250,
    nperseg: int = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Compute Power Spectral Density using Welch's method.

    Welch's method divides the signal into overlapping segments,
    computes the periodogram for each, and averages them. This reduces
    variance in the PSD estimate — critical for stable feature extraction.

    This is the core of the "Neural Signature" — the PSD shape is
    unique to each individual (Palaniappan, 2004).

    Parameters
    ----------
    eeg_signal : np.ndarray
        Preprocessed EEG signal
    fs : int
        Sampling rate
    nperseg : int
        Length of each Welch segment (default: fs * 2 for 2-second windows)

    Returns
    -------
    freqs : np.ndarray
        Frequency vector (Hz)
    psd : np.ndarray
        Power spectral density (μV²/Hz)
    """
    if nperseg is None:
        nperseg = min(fs * 2, len(eeg_signal))

    freqs, psd = signal.welch(
        eeg_signal,
        fs=fs,
        nperseg=nperseg,
        noverlap=nperseg // 2,
        window='hann',
        scaling='density',
    )
    return freqs, psd


def extract_band_powers(
    freqs: np.ndarray,
    psd: np.ndarray,
) -> Dict[str, float]:
    """
    Extract power in each EEG frequency band from the PSD.

    Computes the integral (area under curve) of the PSD within each
    frequency band using the trapezoidal rule.

    Returns
    -------
    dict
        Power values for delta, theta, alpha, beta bands
    """
    band_powers = {}
    for band_name, (low, high) in BANDS.items():
        mask = (freqs >= low) & (freqs <= high)
        if np.any(mask):
            band_powers[band_name] = np.trapz(psd[mask], freqs[mask])
        else:
            band_powers[band_name] = 0.0
    return band_powers


def extract_features(
    eeg_signal: np.ndarray,
    fs: int = 250,
) -> Tuple[np.ndarray, Dict]:
    """
    Complete feature extraction pipeline for authentication.

    Extracts a feature vector from a preprocessed EEG signal:
    1. Absolute band powers (delta, theta, alpha, beta)
    2. Relative band powers (normalized to total power)
    3. Band power ratios (alpha/beta, theta/alpha, theta/beta)
    4. Spectral entropy (measure of signal complexity)
    5. Peak alpha frequency

    These features together form the "Neural Signature" vector
    fed into the SVM classifier.

    Parameters
    ----------
    eeg_signal : np.ndarray
        Preprocessed EEG signal
    fs : int
        Sampling rate

    Returns
    -------
    feature_vector : np.ndarray
        Feature vector for classifier input
    feature_dict : dict
        Named features for visualization
    """
    freqs, psd = compute_psd(eeg_signal, fs)
    band_powers = extract_band_powers(freqs, psd)

    # Total power for normalization
    total_power = sum(band_powers.values())
    if total_power == 0:
        total_power = 1e-10  # Prevent division by zero

    # Relative band powers (sum to 1.0)
    relative_powers = {
        f"rel_{k}": v / total_power for k, v in band_powers.items()
    }

    # Band power ratios — discriminative features
    alpha_p = band_powers.get("alpha", 1e-10)
    beta_p = band_powers.get("beta", 1e-10)
    theta_p = band_powers.get("theta", 1e-10)

    ratios = {
        "alpha_beta_ratio": alpha_p / max(beta_p, 1e-10),
        "theta_alpha_ratio": theta_p / max(alpha_p, 1e-10),
        "theta_beta_ratio": theta_p / max(beta_p, 1e-10),
    }

    # Spectral entropy — uniqueness measure
    psd_norm = psd / (np.sum(psd) + 1e-10)
    psd_norm = psd_norm[psd_norm > 0]
    spectral_entropy = -np.sum(psd_norm * np.log2(psd_norm + 1e-10))

    # Peak alpha frequency (Individual Alpha Frequency - IAF)
    alpha_mask = (freqs >= 8) & (freqs <= 13)
    if np.any(alpha_mask):
        alpha_freqs = freqs[alpha_mask]
        alpha_psd = psd[alpha_mask]
        peak_alpha_freq = alpha_freqs[np.argmax(alpha_psd)]
    else:
        peak_alpha_freq = 10.0  # Default

    # Construct feature dictionary
    feature_dict = {
        **band_powers,
        **relative_powers,
        **ratios,
        "spectral_entropy": spectral_entropy,
        "peak_alpha_freq": peak_alpha_freq,
        "total_power": total_power,
    }

    # Construct feature vector (ordered, for classifier)
    feature_vector = np.array([
        band_powers["delta"],
        band_powers["theta"],
        band_powers["alpha"],
        band_powers["beta"],
        relative_powers["rel_delta"],
        relative_powers["rel_theta"],
        relative_powers["rel_alpha"],
        relative_powers["rel_beta"],
        ratios["alpha_beta_ratio"],
        ratios["theta_alpha_ratio"],
        ratios["theta_beta_ratio"],
        spectral_entropy,
        peak_alpha_freq,
    ])

    return feature_vector, feature_dict


def full_preprocessing_pipeline(
    raw_signal: np.ndarray,
    fs: int = 250,
) -> Dict[str, np.ndarray]:
    """
    Complete preprocessing pipeline matching the CortexKey signal chain.

    Steps:
    1. Notch filter at 50 Hz (power line removal)
    2. Wide bandpass 1-40 Hz (artifact removal)
    3. Narrow bandpass 5-30 Hz (alpha + beta isolation for auth)

    Returns all intermediate stages for visualization.

    Parameters
    ----------
    raw_signal : np.ndarray
        Raw EEG from sensor (or simulator)
    fs : int
        Sampling rate

    Returns
    -------
    dict with keys:
        'raw' : original signal
        'notch_filtered' : after 50 Hz removal
        'wide_bandpass' : after 1-40 Hz filter
        'narrow_bandpass' : after 5-30 Hz filter (used for features)
    """
    # Stage 1: Remove 50 Hz power line noise
    notch_filtered = apply_notch_filter(raw_signal, fs, notch_freq=50.0)

    # Stage 2: Wide bandpass — remove DC drift and high-freq artifacts
    wide_bp = apply_bandpass_filter(notch_filtered, fs, low_freq=1.0, high_freq=40.0)

    # Stage 3: Narrow bandpass — focus on auth-relevant bands
    narrow_bp = apply_bandpass_filter(notch_filtered, fs, low_freq=5.0, high_freq=30.0)

    return {
        "raw": raw_signal,
        "notch_filtered": notch_filtered,
        "wide_bandpass": wide_bp,
        "narrow_bandpass": narrow_bp,
    }
