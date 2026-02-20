"""
Cryptographic Utilities — CortexKey v0.1

Handles the cryptographic operations needed for FIDO2/WebAuthn passkey flow:
  - ECDSA P-256 key pair generation (same as YubiKey, Touch ID, etc.)
  - Challenge signing (proving possession of private key)
  - Credential storage

The key insight: In a traditional FIDO2 authenticator, the "user verification"
step is a fingerprint or PIN. In CortexKey, we replace that with EEG verification.
The crypto operations remain standard FIDO2-compliant.

References:
  - FIDO2/WebAuthn spec: https://www.w3.org/TR/webauthn-2/
  - cryptography library: https://cryptography.io/
"""

import os
import json
import hashlib
import base64
from datetime import datetime
from typing import Dict, Tuple, Optional

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature,
    encode_dss_signature,
)
from cryptography.hazmat.backends import default_backend


# Storage path
KEYS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "keys")


def _ensure_dirs():
    os.makedirs(KEYS_DIR, exist_ok=True)


def generate_credential_id() -> str:
    """Generate a unique credential ID (random 32 bytes, base64url encoded)."""
    return base64.urlsafe_b64encode(os.urandom(32)).decode('utf-8').rstrip('=')


def generate_keypair() -> Tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]:
    """
    Generate an ECDSA P-256 key pair.

    This is the same curve used by:
    - Apple Touch ID / Face ID passkeys
    - Google Titan Security Keys
    - YubiKey 5 series

    The private key stays on CortexKey (never leaves the device).
    The public key is sent to the relying party (e.g., Google) during registration.
    """
    private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
    public_key = private_key.public_key()
    return private_key, public_key


def sign_challenge(
    private_key: ec.EllipticCurvePrivateKey,
    challenge: bytes,
) -> bytes:
    """
    Sign a WebAuthn challenge with the private key.

    In the FIDO2 flow:
    1. Server sends a random challenge
    2. Authenticator signs it with private key
    3. Server verifies signature with stored public key

    CortexKey adds: Step 1.5 — Verify user's brainwave before signing.
    """
    signature = private_key.sign(challenge, ec.ECDSA(hashes.SHA256()))
    return signature


def verify_signature(
    public_key: ec.EllipticCurvePublicKey,
    challenge: bytes,
    signature: bytes,
) -> bool:
    """Verify a signature against the public key."""
    try:
        public_key.verify(signature, challenge, ec.ECDSA(hashes.SHA256()))
        return True
    except Exception:
        return False


def public_key_to_pem(public_key: ec.EllipticCurvePublicKey) -> str:
    """Serialize public key to PEM format."""
    return public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode('utf-8')


def public_key_to_cose(public_key: ec.EllipticCurvePublicKey) -> Dict:
    """
    Convert public key to COSE Key format (used in WebAuthn).

    COSE Key for EC2 (P-256):
    {
        1: 2,       # kty: EC2
        3: -7,      # alg: ES256
        -1: 1,      # crv: P-256
        -2: x,      # x coordinate
        -3: y,      # y coordinate
    }
    """
    numbers = public_key.public_numbers()
    x_bytes = numbers.x.to_bytes(32, byteorder='big')
    y_bytes = numbers.y.to_bytes(32, byteorder='big')

    return {
        "kty": 2,      # EC2
        "alg": -7,     # ES256
        "crv": 1,      # P-256
        "x": base64.urlsafe_b64encode(x_bytes).decode('utf-8').rstrip('='),
        "y": base64.urlsafe_b64encode(y_bytes).decode('utf-8').rstrip('='),
    }


def private_key_to_pem(
    private_key: ec.EllipticCurvePrivateKey,
    password: Optional[bytes] = None,
) -> str:
    """Serialize private key to PEM (optionally encrypted)."""
    encryption = (
        serialization.BestAvailableEncryption(password)
        if password
        else serialization.NoEncryption()
    )
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=encryption,
    ).decode('utf-8')


def pem_to_private_key(
    pem_data: str,
    password: Optional[bytes] = None,
) -> ec.EllipticCurvePrivateKey:
    """Deserialize private key from PEM."""
    return serialization.load_pem_private_key(
        pem_data.encode('utf-8'),
        password=password,
        backend=default_backend(),
    )
