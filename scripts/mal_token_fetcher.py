import os
import json
import base64
import requests
import webbrowser
from urllib.parse import urlparse, parse_qs
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv
from pathlib import Path

# -------------------
# Load ENV variables
# -------------------
load_dotenv()

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")

# -------------------
# Paths
# -------------------
DATA_DIR = Path(__file__).resolve().parents[1] / "app" / "data"
DATA_DIR.mkdir(exist_ok=True)  # ensure it exists
TOKENS_FILE = DATA_DIR / "tokens.json"

# -------------------
# Helpers
# -------------------
def save_tokens(tokens):
    with open(TOKENS_FILE, "w") as f:
        json.dump(tokens, f, indent=2)
    print("[INFO] Tokens saved to", TOKENS_FILE)

def load_tokens():
    if os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE, "r") as f:
            return json.load(f)
    return None

def refresh_tokens(refresh_token):
    """Refresh the access token using the stored refresh token."""
    print("[INFO] Attempting to refresh tokens...")
    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    r = requests.post("https://myanimelist.net/v1/oauth2/token", data=payload)
    if r.status_code == 200:
        tokens = r.json()
        save_tokens(tokens)
        print("[SUCCESS] Tokens refreshed.")
        return tokens
    else:
        print("[ERROR] Refresh failed:", r.status_code, r.text)
        return None

# -------------------
# OAuth Flow (Plain PKCE)
# -------------------
class OAuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_url = urlparse(self.path)
        query = parse_qs(parsed_url.query)
        if "code" in query:
            self.server.auth_code = query["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>You can close this tab and return to the terminal.</h1>")
        else:
            self.send_response(400)
            self.end_headers()

def browser_login():
    """Do a full browser login flow to get a new access + refresh token."""
    code_verifier = base64.urlsafe_b64encode(os.urandom(40)).decode('utf-8').replace("=", "")

    server_address = ('', 8080)
    httpd = HTTPServer(server_address, OAuthHandler)

    auth_url = (
        f"https://myanimelist.net/v1/oauth2/authorize"
        f"?response_type=code&client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&code_challenge={code_verifier}"
        f"&code_challenge_method=plain"
        f"&state=RequestID42"
    )

    print("[INFO] Opening browser for login...")
    webbrowser.open(auth_url)
    print("[INFO] Waiting for redirect...")
    httpd.handle_request()

    auth_code = getattr(httpd, 'auth_code', None)
    if not auth_code:
        print("[ERROR] No authorization code received.")
        return None

    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": auth_code,
        "code_verifier": code_verifier,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI
    }
    r = requests.post("https://myanimelist.net/v1/oauth2/token", data=payload)
    if r.status_code == 200:
        tokens = r.json()
        save_tokens(tokens)
        print("[SUCCESS] Logged in and tokens saved.")
        return tokens
    else:
        print("[ERROR] Token exchange failed:", r.status_code, r.text)
        return None

# -------------------
# Helper for other scripts
# -------------------
def get_access_token():
    """
    Always return a valid access token.
    Refresh if possible, otherwise prompt login.
    """
    tokens = load_tokens()

    if tokens:
        refreshed = refresh_tokens(tokens["refresh_token"])
        if refreshed:
            return refreshed["access_token"]
        else:
            print("[WARN] Refresh failed. Doing browser login...")
            tokens = browser_login()
            if tokens:
                return tokens["access_token"]
            return None
    else:
        print("[INFO] No tokens found. Doing browser login...")
        tokens = browser_login()
        if tokens:
            return tokens["access_token"]
        return None

# -------------------
# CLI usage
# -------------------
if __name__ == "__main__":
    token = get_access_token()
    if token:
        print("\n[ACCESS TOKEN]", token)
    else:
        print("[ERROR] Could not obtain access token.")
