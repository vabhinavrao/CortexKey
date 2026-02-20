"""
Passkey Manager — CortexKey v0.1

Implements FIDO2/WebAuthn passkey lifecycle management with
brainwave-based user verification.

This module simulates a complete WebAuthn Relying Party + Authenticator flow:

REGISTRATION (Onboarding):
  1. User clicks "Register CortexKey Passkey"
  2. Relying Party (our server) generates a challenge
  3. CortexKey captures EEG → verifies identity → if OK:
  4. Generate ECDSA P-256 keypair
  5. Sign challenge with private key
  6. Send public key + credential to Relying Party
  7. Relying Party stores credential

AUTHENTICATION (Login):
  1. User clicks "Login with CortexKey"
  2. Relying Party sends challenge
  3. CortexKey captures EEG → verifies identity → if OK:
  4. Sign challenge with stored private key
  5. Relying Party verifies signature with stored public key
  6. Access granted

GOOGLE PASSKEY INTEGRATION:
  For the hackathon demo, we demonstrate compatibility with the Google
  Passkey ecosystem by implementing the same WebAuthn data structures
  and cryptographic operations that Google uses. The demo shows:
  - Credential creation matching Google's passkey format
  - Challenge-response authentication flow
  - COSE key format output (same as real passkeys)

References:
  - WebAuthn Level 2 spec: https://www.w3.org/TR/webauthn-2/
  - Google Passkeys: https://developers.google.com/identity/passkeys
  - FIDO Alliance: https://fidoalliance.org/
"""

import os
import json
import base64
import hashlib
import time
from datetime import datetime
from typing import Dict, Optional, List

from .crypto_utils import (
    generate_keypair,
    generate_credential_id,
    sign_challenge,
    verify_signature,
    public_key_to_pem,
    public_key_to_cose,
    private_key_to_pem,
    pem_to_private_key,
)

# Storage
PASSKEY_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "passkeys")


def _ensure_dirs():
    os.makedirs(PASSKEY_DIR, exist_ok=True)


class PasskeyCredential:
    """Represents a single WebAuthn/FIDO2 credential."""

    def __init__(
        self,
        credential_id: str,
        user_id: str,
        rp_id: str,  # Relying Party ID (e.g., "google.com", "cortexkey.local")
        public_key_pem: str,
        private_key_pem: str,
        created_at: str = None,
    ):
        self.credential_id = credential_id
        self.user_id = user_id
        self.rp_id = rp_id
        self.public_key_pem = public_key_pem
        self.private_key_pem = private_key_pem
        self.created_at = created_at or datetime.now().isoformat()
        self.sign_count = 0
        self.last_used = None

    def to_dict(self) -> Dict:
        return {
            "credential_id": self.credential_id,
            "user_id": self.user_id,
            "rp_id": self.rp_id,
            "public_key_pem": self.public_key_pem,
            "created_at": self.created_at,
            "sign_count": self.sign_count,
            "last_used": self.last_used,
        }

    def to_webauthn_response(self) -> Dict:
        """Format as a WebAuthn PublicKeyCredential response."""
        private_key = pem_to_private_key(self.private_key_pem)
        public_key = private_key.public_key()
        cose_key = public_key_to_cose(public_key)

        return {
            "id": self.credential_id,
            "type": "public-key",
            "response": {
                "clientDataJSON": base64.urlsafe_b64encode(
                    json.dumps({
                        "type": "webauthn.create",
                        "challenge": "",  # Filled during actual registration
                        "origin": f"https://{self.rp_id}",
                    }).encode()
                ).decode('utf-8'),
                "attestationObject": {
                    "fmt": "none",  # Self-attestation (like platform authenticators)
                    "authData": {
                        "rpIdHash": hashlib.sha256(self.rp_id.encode()).hexdigest(),
                        "flags": {
                            "UP": True,   # User Present
                            "UV": True,   # User Verified (via EEG!)
                            "AT": True,   # Attested credential
                        },
                        "signCount": self.sign_count,
                        "credentialId": self.credential_id,
                        "credentialPublicKey": cose_key,
                    },
                },
            },
            "authenticatorAttachment": "cross-platform",  # CortexKey is external hardware
        }


class PasskeyManager:
    """
    Manages FIDO2/WebAuthn passkey operations for CortexKey.

    Acts as both:
    - Authenticator: Generates keys, signs challenges (hardware side)
    - Relying Party: Verifies signatures, stores credentials (server side)

    For the hackathon, both roles run locally. In production,
    the Relying Party would be a remote server.
    """

    def __init__(self):
        _ensure_dirs()
        self.credentials: Dict[str, PasskeyCredential] = {}
        self.pending_challenges: Dict[str, Dict] = {}
        self._load_credentials()

    def _load_credentials(self):
        """Load saved credentials from disk."""
        cred_file = os.path.join(PASSKEY_DIR, "credentials.json")
        if os.path.exists(cred_file):
            try:
                with open(cred_file, 'r') as f:
                    data = json.load(f)
                    for cred_data in data:
                        cred = PasskeyCredential(**cred_data)
                        self.credentials[cred.credential_id] = cred
            except Exception:
                pass

    def _save_credentials(self):
        """Save credentials to disk."""
        cred_file = os.path.join(PASSKEY_DIR, "credentials.json")
        data = []
        for cred in self.credentials.values():
            d = cred.to_dict()
            d["private_key_pem"] = cred.private_key_pem
            data.append(d)

        with open(cred_file, 'w') as f:
            json.dump(data, f, indent=2)

    # ─────────────────────────────────────────────────────
    # REGISTRATION FLOW (Passkey Creation / Onboarding)
    # ─────────────────────────────────────────────────────

    def begin_registration(
        self,
        user_id: str,
        rp_id: str = "cortexkey.local",
        rp_name: str = "CortexKey Authentication",
    ) -> Dict:
        """
        Step 1: Relying Party generates registration options.

        This is equivalent to navigator.credentials.create() options
        sent by Google/any website supporting passkeys.
        """
        # Generate random challenge (32 bytes, base64url)
        challenge = base64.urlsafe_b64encode(os.urandom(32)).decode('utf-8').rstrip('=')

        registration_options = {
            "challenge": challenge,
            "rp": {
                "id": rp_id,
                "name": rp_name,
            },
            "user": {
                "id": base64.urlsafe_b64encode(user_id.encode()).decode('utf-8').rstrip('='),
                "name": user_id,
                "displayName": user_id.title(),
            },
            "pubKeyCredParams": [
                {"type": "public-key", "alg": -7},  # ES256 (ECDSA P-256)
            ],
            "authenticatorSelection": {
                "authenticatorAttachment": "cross-platform",
                "userVerification": "required",  # EEG verification is mandatory!
                "residentKey": "required",
            },
            "timeout": 60000,  # 60 seconds
            "attestation": "none",
        }

        # Store pending challenge
        self.pending_challenges[user_id] = {
            "challenge": challenge,
            "rp_id": rp_id,
            "type": "registration",
            "timestamp": time.time(),
        }

        return registration_options

    def complete_registration(
        self,
        user_id: str,
        eeg_verified: bool,
        rp_id: str = "cortexkey.local",
    ) -> Dict:
        """
        Step 2: CortexKey authenticator creates credential.

        This happens ONLY if EEG verification passed.
        Equivalent to the authenticator's response to navigator.credentials.create().

        Parameters
        ----------
        user_id : str
            The user being registered
        eeg_verified : bool
            Whether EEG authentication passed (from AuthEngine)
        rp_id : str
            Relying Party identifier

        Returns
        -------
        dict
            Registration result with credential details
        """
        if not eeg_verified:
            return {
                "status": "failed",
                "reason": "EEG verification failed — cannot create passkey without neural authentication",
            }

        # Check pending challenge
        pending = self.pending_challenges.get(user_id)
        if not pending:
            return {
                "status": "failed",
                "reason": "No pending registration challenge",
            }

        # Generate ECDSA P-256 key pair
        private_key, public_key = generate_keypair()
        credential_id = generate_credential_id()

        # Create credential object
        credential = PasskeyCredential(
            credential_id=credential_id,
            user_id=user_id,
            rp_id=rp_id,
            public_key_pem=public_key_to_pem(public_key),
            private_key_pem=private_key_to_pem(private_key),
        )

        # Sign the registration challenge
        challenge_bytes = pending["challenge"].encode('utf-8')
        signature = sign_challenge(private_key, challenge_bytes)

        # Store credential
        self.credentials[credential_id] = credential
        self._save_credentials()

        # Clear pending challenge
        del self.pending_challenges[user_id]

        # Build WebAuthn response
        webauthn_response = credential.to_webauthn_response()

        return {
            "status": "registered",
            "credential_id": credential_id,
            "user_id": user_id,
            "rp_id": rp_id,
            "public_key_cose": public_key_to_cose(public_key),
            "webauthn_response": webauthn_response,
            "created_at": credential.created_at,
            "message": f"✅ CortexKey passkey created for {user_id} on {rp_id}",
        }

    # ─────────────────────────────────────────────────────
    # AUTHENTICATION FLOW (Passkey Login)
    # ─────────────────────────────────────────────────────

    def begin_authentication(
        self,
        rp_id: str = "cortexkey.local",
    ) -> Dict:
        """
        Step 1: Relying Party generates authentication options.

        Equivalent to navigator.credentials.get() options.
        """
        challenge = base64.urlsafe_b64encode(os.urandom(32)).decode('utf-8').rstrip('=')

        # Find credentials for this RP
        allowed_credentials = [
            {
                "type": "public-key",
                "id": cred.credential_id,
            }
            for cred in self.credentials.values()
            if cred.rp_id == rp_id
        ]

        auth_options = {
            "challenge": challenge,
            "rpId": rp_id,
            "allowCredentials": allowed_credentials,
            "userVerification": "required",
            "timeout": 60000,
        }

        self.pending_challenges["auth"] = {
            "challenge": challenge,
            "rp_id": rp_id,
            "type": "authentication",
            "timestamp": time.time(),
        }

        return auth_options

    def complete_authentication(
        self,
        credential_id: str,
        eeg_verified: bool,
    ) -> Dict:
        """
        Step 2: CortexKey authenticator signs the challenge.

        Only proceeds if EEG verification passed.

        Parameters
        ----------
        credential_id : str
            The credential to use for signing
        eeg_verified : bool
            Whether EEG authentication passed

        Returns
        -------
        dict
            Authentication result
        """
        if not eeg_verified:
            return {
                "status": "failed",
                "reason": "EEG verification failed — passkey signing denied",
                "authenticated": False,
            }

        credential = self.credentials.get(credential_id)
        if not credential:
            return {
                "status": "failed",
                "reason": "Unknown credential ID",
                "authenticated": False,
            }

        pending = self.pending_challenges.get("auth")
        if not pending:
            return {
                "status": "failed",
                "reason": "No pending authentication challenge",
                "authenticated": False,
            }

        # Load private key and sign challenge
        private_key = pem_to_private_key(credential.private_key_pem)
        challenge_bytes = pending["challenge"].encode('utf-8')
        signature = sign_challenge(private_key, challenge_bytes)

        # Verify signature with public key (server-side verification)
        from cryptography.hazmat.primitives.serialization import load_pem_public_key
        from cryptography.hazmat.backends import default_backend
        public_key = load_pem_public_key(
            credential.public_key_pem.encode('utf-8'),
            backend=default_backend(),
        )
        signature_valid = verify_signature(public_key, challenge_bytes, signature)

        # Update credential
        credential.sign_count += 1
        credential.last_used = datetime.now().isoformat()
        self._save_credentials()

        # Clear pending challenge
        del self.pending_challenges["auth"]

        return {
            "status": "authenticated" if signature_valid else "failed",
            "authenticated": signature_valid,
            "credential_id": credential_id,
            "user_id": credential.user_id,
            "rp_id": credential.rp_id,
            "sign_count": credential.sign_count,
            "signature_valid": signature_valid,
            "signature_b64": base64.urlsafe_b64encode(signature).decode('utf-8'),
            "message": (
                f"✅ Passkey authentication successful for {credential.user_id}"
                if signature_valid
                else "❌ Signature verification failed"
            ),
        }

    # ─────────────────────────────────────────────────────
    # GOOGLE PASSKEY DEMO
    # ─────────────────────────────────────────────────────

    def demo_google_passkey_registration(
        self,
        user_id: str,
        gmail_address: str,
        eeg_verified: bool,
    ) -> Dict:
        """
        Simulate registering CortexKey as a passkey for a Google account.

        This demonstrates that CortexKey produces the same WebAuthn
        data structures that Google expects. In a real deployment,
        this would be triggered by a browser extension intercepting
        Google's navigator.credentials.create() call.

        Parameters
        ----------
        user_id : str
            CortexKey user ID
        gmail_address : str
            Google account email
        eeg_verified : bool
            Whether EEG authentication passed

        Returns
        -------
        dict
            Google passkey registration result
        """
        # Start registration with Google as the RP
        options = self.begin_registration(
            user_id=user_id,
            rp_id="google.com",
            rp_name="Google Account",
        )

        if not eeg_verified:
            return {
                "status": "failed",
                "reason": "Neural verification failed — cannot register passkey",
                "google_account": gmail_address,
            }

        # Complete registration
        result = self.complete_registration(
            user_id=user_id,
            eeg_verified=True,
            rp_id="google.com",
        )

        result["google_account"] = gmail_address
        result["rp_name"] = "Google Account"
        result["passkey_name"] = f"CortexKey ({user_id})"
        result["message"] = (
            f"✅ CortexKey passkey registered for Google Account: {gmail_address}\n"
            f"   Credential ID: {result.get('credential_id', 'N/A')[:16]}...\n"
            f"   Algorithm: ES256 (ECDSA P-256)\n"
            f"   User Verification: EEG Neural Signature"
        )

        return result

    def demo_google_passkey_login(
        self,
        gmail_address: str,
        eeg_verified: bool,
    ) -> Dict:
        """
        Simulate logging into a Google account using CortexKey passkey.
        """
        # Find Google credential
        google_creds = [
            cred for cred in self.credentials.values()
            if cred.rp_id == "google.com"
        ]

        if not google_creds:
            return {
                "status": "failed",
                "reason": "No CortexKey passkey registered for Google",
                "authenticated": False,
            }

        credential = google_creds[0]

        # Start authentication
        self.begin_authentication(rp_id="google.com")

        # Complete authentication
        result = self.complete_authentication(
            credential_id=credential.credential_id,
            eeg_verified=eeg_verified,
        )

        result["google_account"] = gmail_address
        if result["authenticated"]:
            result["message"] = (
                f"✅ Successfully signed into Google Account: {gmail_address}\n"
                f"   Verified by: CortexKey Neural Authentication\n"
                f"   Sign count: {result['sign_count']}\n"
                f"   Method: FIDO2/WebAuthn Passkey"
            )

        return result

    def get_all_credentials(self) -> List[Dict]:
        """Get all stored credentials."""
        return [cred.to_dict() for cred in self.credentials.values()]

    def get_credentials_for_rp(self, rp_id: str) -> List[Dict]:
        """Get credentials for a specific Relying Party."""
        return [
            cred.to_dict()
            for cred in self.credentials.values()
            if cred.rp_id == rp_id
        ]

    def reset(self):
        """Clear all credentials."""
        self.credentials.clear()
        self.pending_challenges.clear()
        cred_file = os.path.join(PASSKEY_DIR, "credentials.json")
        if os.path.exists(cred_file):
            os.remove(cred_file)
