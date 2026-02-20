"""
Authentication Engine — CortexKey v0.1

Orchestrates the complete authentication flow:
  1. ONBOARDING: Record EEG → Process → Extract features → Train classifier → Store neural template
  2. VERIFICATION: Record EEG → Process → Extract features → Classify → Accept/Reject
  3. PASSKEY BINDING: Link neural signature to FIDO2/WebAuthn credential

This module ties together the simulator, signal processing, and classifier
into a coherent auth system.
"""

import numpy as np
import json
import os
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from .eeg_simulator import generate_eeg_signal, generate_enrollment_dataset, SAMPLING_RATE
from .signal_processing import full_preprocessing_pipeline, extract_features
from .classifier import NeuralClassifier


# Storage directory for enrolled neural templates
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
MODELS_DIR = os.path.join(DATA_DIR, "models")
TEMPLATES_DIR = os.path.join(DATA_DIR, "templates")


def _ensure_dirs():
    """Create data directories if they don't exist."""
    os.makedirs(MODELS_DIR, exist_ok=True)
    os.makedirs(TEMPLATES_DIR, exist_ok=True)


class AuthEngine:
    """
    CortexKey Authentication Engine.

    Manages the complete lifecycle:
    - User enrollment (onboarding)
    - Neural signature verification
    - Session management
    - Passkey credential binding
    """

    def __init__(self, confidence_threshold: float = 0.70):
        _ensure_dirs()
        self.classifier = NeuralClassifier(confidence_threshold=confidence_threshold)
        self.enrolled_users: Dict[str, Dict] = {}
        self.auth_log: List[Dict] = []
        self.model_path = os.path.join(MODELS_DIR, "cortexkey_model.pkl")

    def enroll_user(
        self,
        user_id: str,
        n_trials: int = 20,
        progress_callback=None,
    ) -> Dict:
        """
        Onboarding flow: Enroll a user's neural signature.

        In the real system:
        1. User puts on the headband
        2. User performs the "Emotional Recall" task multiple times
        3. System records EEG for each trial
        4. Features are extracted and the classifier is trained

        With mock data, we simulate this process with generated signals.

        Parameters
        ----------
        user_id : str
            Unique identifier for the user
        n_trials : int
            Number of enrollment trials (more = more robust)
        progress_callback : callable, optional
            Function called with (current_trial, total_trials) for UI updates

        Returns
        -------
        dict
            Enrollment results including metrics
        """
        enrollment_start = time.time()
        features_list = []

        for i in range(n_trials):
            # Generate (or in real system, acquire) EEG signal
            t, raw_signal, meta = generate_eeg_signal(
                user_id=user_id,
                seed=i * 137 + hash(user_id) % 10000,
            )

            # Process through the real DSP pipeline
            processed = full_preprocessing_pipeline(raw_signal, fs=SAMPLING_RATE)

            # Extract features from the filtered signal
            feature_vec, feature_dict = extract_features(
                processed["narrow_bandpass"], fs=SAMPLING_RATE
            )
            features_list.append(feature_vec)

            if progress_callback:
                progress_callback(i + 1, n_trials)

        # Stack features into matrix
        features_matrix = np.vstack(features_list)

        # Store in enrolled users dict
        self.enrolled_users[user_id] = {
            "features": features_matrix,
            "enrolled_at": datetime.now().isoformat(),
            "n_trials": n_trials,
        }

        # Save template
        template_path = os.path.join(TEMPLATES_DIR, f"{user_id}_template.npy")
        np.save(template_path, features_matrix)

        # Retrain classifier with all enrolled users
        training_metrics = self._retrain_classifier()

        enrollment_time = time.time() - enrollment_start

        result = {
            "status": "enrolled",
            "user_id": user_id,
            "n_trials": n_trials,
            "n_features": features_matrix.shape[1],
            "enrollment_time_sec": round(enrollment_time, 2),
            "classifier_accuracy": training_metrics.get("cv_accuracy", 0),
            "total_enrolled_users": len(self.enrolled_users),
        }

        self._log_event("enrollment", user_id, result)
        return result

    def _retrain_classifier(self) -> Dict:
        """Retrain the classifier with all currently enrolled users."""
        if len(self.enrolled_users) < 1:
            return {}

        features_by_user = {
            uid: data["features"]
            for uid, data in self.enrolled_users.items()
        }

        metrics = self.classifier.enroll(features_by_user)

        # Save model
        self.classifier.save(self.model_path)

        return metrics

    def verify_user(
        self,
        claimed_user: str,
        test_user: Optional[str] = None,
        seed: Optional[int] = None,
    ) -> Dict:
        """
        Verification flow: Authenticate a user via their neural signature.

        In the real system:
        1. User claims their identity
        2. User performs the mental task
        3. EEG is recorded and processed
        4. Features are compared against enrolled template

        Parameters
        ----------
        claimed_user : str
            Who the person claims to be
        test_user : str, optional
            Actual user generating the signal (for demo — allows impostor testing).
            If None, uses claimed_user (honest attempt).
        seed : int, optional
            Random seed for reproducible demo

        Returns
        -------
        dict
            Verification results
        """
        if not self.classifier.is_trained:
            return {
                "status": "error",
                "reason": "No users enrolled. Complete onboarding first.",
            }

        # The actual signal source (for demo, can differ from claimed)
        signal_source = test_user if test_user else claimed_user

        if seed is None:
            seed = int(time.time() * 1000) % 100000

        # Generate/acquire EEG
        t, raw_signal, meta = generate_eeg_signal(
            user_id=signal_source,
            seed=seed,
        )

        # Process through DSP pipeline
        processed = full_preprocessing_pipeline(raw_signal, fs=SAMPLING_RATE)

        # Extract features
        feature_vec, feature_dict = extract_features(
            processed["narrow_bandpass"], fs=SAMPLING_RATE
        )

        # Classify
        auth_result = self.classifier.verify(feature_vec, claimed_user)

        # Build comprehensive result
        result = {
            "status": "authenticated" if auth_result["authenticated"] else "denied",
            "claimed_user": claimed_user,
            "actual_source": signal_source,
            "confidence": auth_result["confidence"],
            "threshold": auth_result["threshold"],
            "predicted_user": auth_result["predicted_user"],
            "reason": auth_result["reason"],
            "all_probabilities": auth_result["all_probabilities"],
            "timestamp": datetime.now().isoformat(),
            # Return signal data for visualization
            "signals": {
                "time": t,
                "raw": raw_signal,
                "notch_filtered": processed["notch_filtered"],
                "bandpass_filtered": processed["narrow_bandpass"],
            },
            "features": feature_dict,
            "psd_data": None,  # Will be computed in visualization
        }

        self._log_event("verification", claimed_user, {
            "status": result["status"],
            "confidence": result["confidence"],
            "source": signal_source,
        })

        return result

    def get_enrollment_status(self) -> Dict:
        """Get current enrollment status for all users."""
        return {
            "enrolled_users": list(self.enrolled_users.keys()),
            "total_enrolled": len(self.enrolled_users),
            "classifier_trained": self.classifier.is_trained,
            "classifier_accuracy": self.classifier.cv_accuracy,
            "model_path": self.model_path,
        }

    def get_auth_log(self) -> List[Dict]:
        """Get authentication event log."""
        return self.auth_log.copy()

    def _log_event(self, event_type: str, user_id: str, details: Dict):
        """Log an authentication event."""
        self.auth_log.append({
            "event_type": event_type,
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
            "details": details,
        })

    def reset(self):
        """Reset all enrollments and the classifier."""
        self.enrolled_users.clear()
        self.auth_log.clear()
        self.classifier = NeuralClassifier(
            confidence_threshold=self.classifier.confidence_threshold
        )
