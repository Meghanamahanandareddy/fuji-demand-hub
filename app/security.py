"""Password hashing and login tokens, using only the standard library and
itsdangerous."""
import hashlib
import hmac
import os
import secrets

from dotenv import load_dotenv
from itsdangerous import BadSignature, URLSafeTimedSerializer

load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY")
TOKEN_MAX_AGE_SECONDS = 8 * 3600
ITERATIONS = 200_000


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password, stored):
    try:
        _, iterations, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations))
    except ValueError:
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


def _serializer():
    if not SECRET_KEY:
        raise RuntimeError("SECRET_KEY is not set in .env")
    return URLSafeTimedSerializer(SECRET_KEY, salt="fuji-demand-hub-auth")


def create_token(user_id):
    return _serializer().dumps({"uid": user_id})


def read_token(token):
    """Return the user id, or None if the token is invalid or expired."""
    try:
        return _serializer().loads(token, max_age=TOKEN_MAX_AGE_SECONDS)["uid"]
    except BadSignature:
        return None