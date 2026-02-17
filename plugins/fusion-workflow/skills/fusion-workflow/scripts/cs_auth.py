"""
Shared CrowdStrike OAuth2 authentication and HTTP helpers.

All other scripts import from this module. Credentials are loaded from a .env
file (never hardcoded). Run directly to verify credentials:

    python cs_auth.py
"""

import os
import sys
import json
import time
import requests

# Fix Windows console encoding
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── .env loader ─────────────────────────────────────────────────────────────

def load_env(env_file=None):
    """
    Load key=value pairs from a .env file into os.environ.

    Resolution order for the .env path:
      1. Explicit env_file argument
      2. CS_ENV_FILE environment variable
      3. Walk upward from this script's directory to find '.env'
      4. Fall back to the project root (workflows/)
    """
    if env_file is None:
        env_file = os.environ.get("CS_ENV_FILE")

    if env_file is None:
        search = os.path.dirname(os.path.abspath(__file__))
        while True:
            candidate = os.path.join(search, ".env")
            if os.path.isfile(candidate):
                env_file = candidate
                break
            parent = os.path.dirname(search)
            if parent == search:
                break
            search = parent

    if env_file is None or not os.path.isfile(env_file):
        return  # No .env found; rely on existing environment variables

    with open(env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


# ── Credentials ─────────────────────────────────────────────────────────────

def get_credentials():
    """Return (client_id, client_secret, base_url) from environment."""
    load_env()
    client_id = os.environ.get("CS_CLIENT_ID", "")
    client_secret = os.environ.get("CS_CLIENT_SECRET", "")
    base_url = os.environ.get("CS_BASE_URL", "https://api.crowdstrike.com")
    if not client_id or not client_secret:
        print("ERROR: CS_CLIENT_ID and CS_CLIENT_SECRET must be set in .env or environment.", file=sys.stderr)
        sys.exit(1)
    return client_id, client_secret, base_url.rstrip("/")


# ── Token cache ─────────────────────────────────────────────────────────────

_token_cache = {"token": None, "expires": 0}


def get_token(client_id=None, client_secret=None, base_url=None):
    """
    Obtain an OAuth2 bearer token via client_credentials grant.
    Caches the token until 60 s before expiry.
    """
    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires"]:
        return _token_cache["token"]

    if client_id is None:
        client_id, client_secret, base_url = get_credentials()

    resp = requests.post(
        f"{base_url}/oauth2/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    resp.raise_for_status()
    body = resp.json()

    _token_cache["token"] = body["access_token"]
    _token_cache["expires"] = now + body.get("expires_in", 1799) - 60
    return _token_cache["token"]


# ── HTTP helpers ────────────────────────────────────────────────────────────

def _base_url():
    load_env()
    return os.environ.get("CS_BASE_URL", "https://api.crowdstrike.com").rstrip("/")


def _headers():
    return {"Authorization": f"Bearer {get_token()}"}


def api_get(path, params=None):
    """GET request with Bearer auth. Returns parsed JSON."""
    url = f"{_base_url()}{path}"
    resp = requests.get(url, headers=_headers(), params=params)
    resp.raise_for_status()
    return resp.json()


def api_post(path, json_body=None, params=None):
    """POST request with JSON body and Bearer auth. Returns parsed JSON."""
    url = f"{_base_url()}{path}"
    resp = requests.post(url, headers=_headers(), json=json_body, params=params)
    resp.raise_for_status()
    return resp.json()


def api_post_multipart(path, file_path, params=None):
    """
    POST multipart/form-data with a YAML file upload (field name 'data_file').
    Returns parsed JSON.
    """
    url = f"{_base_url()}{path}"
    filename = os.path.basename(file_path)
    with open(file_path, "rb") as f:
        files = {"data_file": (filename, f, "application/x-yaml")}
        resp = requests.post(url, headers=_headers(), files=files, params=params)
    resp.raise_for_status()
    return resp.json()


# ── Self-test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("CrowdStrike Auth — self-test")
    print("─" * 40)
    cid, csec, burl = get_credentials()
    print(f"  Base URL  : {burl}")
    print(f"  Client ID : {cid[:8]}...{cid[-4:]}")
    print(f"  Secret    : {'*' * 8}...{csec[-4:]}")
    print()
    try:
        token = get_token(cid, csec, burl)
        print(f"  Token     : {token[:12]}...{token[-4:]}")
        print("\n  Authentication successful")
    except Exception as e:
        print(f"\n  Authentication FAILED: {e}", file=sys.stderr)
        sys.exit(1)
