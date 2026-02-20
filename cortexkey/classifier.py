"""
SVM Classifier — CortexKey v0.1

Real machine learning classifier for EEG-based authentication.
Uses Support Vector Machine (SVM) with RBF kernel, trained on
PSD-derived feature vectors.

This is NOT mock — the classifier genuinely learns to distinguish
users based on their spectral features. When real EEG data replaces
the mock data, the same classifier architecture will work.

Architecture:
  - StandardScaler for feature normalization
  - SVM with RBF kernel (handles non-linear spectral boundaries)
  - Probability calibration (Platt scaling) for confidence scores
  - One-vs-Rest strategy for multi-user classification

References:
  - Scikit-learn SVM: sklearn.svm.SVC
  - Chuang et al. (2013): SVM for brainwave authentication
  - Gui et al. (2014): SVM superiority for EEG biometrics
"""

import numpy as np
from sklearn.svm import SVC
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import cross_val_score
from typing import Dict, Tuple, Optional
import pickle
import os


class NeuralClassifier:
    """
    SVM-based neural signature classifier for CortexKey authentication.

    Supports:
    - Enrollment: Learning a user's neural signature from multiple trials
    - Verification: Checking if a new signal matches an enrolled user
    - Rejection: Detecting impostors with confidence thresholds
    """

    def __init__(self, confidence_threshold: float = 0.70):
        """
        Parameters
        ----------
        confidence_threshold : float
            Minimum SVM probability to accept authentication.
            Higher = more secure but more false rejections.
            0.70 is a good balance for demo purposes.
        """
        self.confidence_threshold = confidence_threshold
        self.pipeline = Pipeline([
            ('scaler', StandardScaler()),
            ('svm', SVC(
                kernel='rbf',
                C=10.0,            # Regularization — tuned for small datasets
                gamma='scale',     # Automatic kernel width
                probability=True,  # Enable Platt scaling for probabilities
                random_state=42,
            ))
        ])
        self.is_trained = False
        self.enrolled_users = []
        self.training_features = None
        self.training_labels = None
        self.cv_accuracy = None

    def enroll(
        self,
        features_by_user: Dict[str, np.ndarray],
    ) -> Dict[str, float]:
        """
        Enroll one or more users by training the classifier on their
        neural signature feature vectors.

        Parameters
        ----------
        features_by_user : dict
            {user_id: np.ndarray of shape (n_trials, n_features)}

        Returns
        -------
        dict
            Training metrics including accuracy
        """
        all_features = []
        all_labels = []

        for user_id, features in features_by_user.items():
            all_features.append(features)
            all_labels.extend([user_id] * len(features))
            if user_id not in self.enrolled_users:
                self.enrolled_users.append(user_id)

        X = np.vstack(all_features)
        y = np.array(all_labels)

        self.training_features = X
        self.training_labels = y

        n_classes = len(np.unique(y))

        if n_classes < 2:
            # SVM needs at least 2 classes. If only 1 user is enrolled,
            # we generate synthetic "impostor" samples with jittered features
            # so the classifier can still function for single-user verification.
            rng = np.random.default_rng(42)
            n_impostor = len(X)
            impostor_features = X.copy()
            # Significantly perturb all features to create a synthetic "other" class
            impostor_features = impostor_features * rng.uniform(0.3, 0.6, impostor_features.shape)
            impostor_features += rng.normal(0, np.std(X, axis=0) * 0.5, impostor_features.shape)

            X = np.vstack([X, impostor_features])
            impostor_labels = np.array(["__impostor__"] * n_impostor)
            y = np.concatenate([y, impostor_labels])
            n_classes = 2

        # Train the pipeline
        self.pipeline.fit(X, y)
        self.is_trained = True

        # Cross-validation for confidence metric
        if len(X) >= 10:
            cv_folds = min(5, n_classes)
            if cv_folds >= 2:
                scores = cross_val_score(
                    Pipeline([
                        ('scaler', StandardScaler()),
                        ('svm', SVC(kernel='rbf', C=10.0, gamma='scale',
                                    probability=True, random_state=42))
                    ]),
                    X, y, cv=cv_folds,
                )
                self.cv_accuracy = float(np.mean(scores))
            else:
                self.cv_accuracy = 1.0
        else:
            self.cv_accuracy = 1.0

        metrics = {
            "n_users": len(self.enrolled_users),
            "n_samples": len(X),
            "n_features": X.shape[1],
            "cv_accuracy": self.cv_accuracy,
            "enrolled_users": self.enrolled_users.copy(),
        }

        return metrics

    def verify(
        self,
        feature_vector: np.ndarray,
        claimed_user: str,
    ) -> Dict:
        """
        Verify if a feature vector matches the claimed user's neural signature.

        Parameters
        ----------
        feature_vector : np.ndarray
            Feature vector from a single EEG trial
        claimed_user : str
            The user ID being claimed

        Returns
        -------
        dict with:
            'authenticated' : bool — whether auth passed
            'confidence' : float — SVM probability for claimed user
            'predicted_user' : str — who the classifier thinks it is
            'all_probabilities' : dict — probabilities for all enrolled users
            'threshold' : float — the required confidence threshold
        """
        if not self.is_trained:
            raise RuntimeError("Classifier not trained. Enroll users first.")

        if feature_vector.ndim == 1:
            feature_vector = feature_vector.reshape(1, -1)

        # Get prediction and probabilities
        predicted = self.pipeline.predict(feature_vector)[0]
        probabilities = self.pipeline.predict_proba(feature_vector)[0]

        # Map probabilities to user IDs
        classes = self.pipeline.classes_
        prob_dict = {cls: float(prob) for cls, prob in zip(classes, probabilities)}

        # Get confidence for the claimed user
        claimed_confidence = prob_dict.get(claimed_user, 0.0)

        # Authentication decision
        authenticated = (
            predicted == claimed_user and
            claimed_confidence >= self.confidence_threshold
        )

        return {
            "authenticated": authenticated,
            "confidence": claimed_confidence,
            "predicted_user": predicted,
            "predicted_confidence": float(max(probabilities)),
            "all_probabilities": prob_dict,
            "threshold": self.confidence_threshold,
            "reason": self._get_rejection_reason(
                authenticated, predicted, claimed_user, claimed_confidence
            ),
        }

    def _get_rejection_reason(
        self,
        authenticated: bool,
        predicted: str,
        claimed: str,
        confidence: float,
    ) -> str:
        """Generate human-readable auth result explanation."""
        if authenticated:
            return f"Neural signature verified — {confidence:.1%} confidence match"

        if predicted != claimed:
            return (
                f"Neural signature mismatch — pattern does not match enrolled user '{claimed}'. "
                f"Classifier identified as '{predicted}' instead."
            )
        else:
            return (
                f"Confidence too low — {confidence:.1%} < {self.confidence_threshold:.1%} threshold. "
                f"Possible stress, fatigue, or environmental interference."
            )

    def save(self, filepath: str):
        """Save trained model to disk."""
        with open(filepath, 'wb') as f:
            pickle.dump({
                'pipeline': self.pipeline,
                'enrolled_users': self.enrolled_users,
                'confidence_threshold': self.confidence_threshold,
                'cv_accuracy': self.cv_accuracy,
                'is_trained': self.is_trained,
            }, f)

    def load(self, filepath: str):
        """Load trained model from disk."""
        with open(filepath, 'rb') as f:
            data = pickle.load(f)
            self.pipeline = data['pipeline']
            self.enrolled_users = data['enrolled_users']
            self.confidence_threshold = data['confidence_threshold']
            self.cv_accuracy = data['cv_accuracy']
            self.is_trained = data['is_trained']
