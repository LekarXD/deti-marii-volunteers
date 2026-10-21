import base64
import hashlib
from cryptography.fernet import Fernet
from app.core.config import get_settings

def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()

def cipher():
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(get_settings().secret_key.encode()).digest()))

def seal(value: str) -> str:
    return cipher().encrypt(value.encode()).decode()

def unseal(value: str) -> str:
    return cipher().decrypt(value.encode()).decode()
