# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "requests",
#   "python-dotenv",
# ]
# ///
"""
QuickBooks OAuth Helper
Run this ONCE to get your refresh token, then you're set.

Usage:
    python auth_helper.py

It will:
1. Open your browser to authorize the app
2. Start a tiny local server to catch the redirect
3. Exchange the auth code for access + refresh tokens
4. Save the refresh token to your .env file
"""

import os
import json
import webbrowser
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("QUICKBOOKS_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("QUICKBOOKS_CLIENT_SECRET", "")
COMPANY_ID = os.getenv("QUICKBOOKS_COMPANY_ID", "")

REDIRECT_URI = "http://localhost:8080/callback"
AUTH_URL = "https://appcenter.intuit.com/connect/oauth2"
TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
SCOPES = "com.intuit.quickbooks.accounting"

auth_code = None
realm_id = None


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code, realm_id
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            auth_code = params["code"][0]
            realm_id = params.get("realmId", [COMPANY_ID])[0]

            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h1>Success!</h1>"
                b"<p>Authorization complete. You can close this tab and go back to the terminal.</p>"
                b"</body></html>"
            )
        else:
            error = params.get("error", ["unknown"])[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                f"<html><body><h1>Error</h1><p>{error}</p></body></html>".encode()
            )

    def log_message(self, format, *args):
        pass  # Suppress HTTP logs


def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("ERROR: Set QUICKBOOKS_CLIENT_ID and QUICKBOOKS_CLIENT_SECRET in .env first.")
        return

    # Build auth URL
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "scope": SCOPES,
        "redirect_uri": REDIRECT_URI,
        "state": "quickbooks-mcp-auth",
    }
    url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    print("\n🔑 QuickBooks OAuth Setup")
    print("=" * 50)
    print("\n1. Opening your browser to authorize the app...")
    print("   (If it doesn't open, copy this URL manually):\n")
    print(f"   {url}\n")

    webbrowser.open(url)

    print("2. Waiting for you to authorize in the browser...\n")

    server = HTTPServer(("localhost", 8080), CallbackHandler)
    server.handle_request()  # Handle one request, then stop

    if not auth_code:
        print("ERROR: No authorization code received.")
        return

    print(f"3. Got authorization code. Exchanging for tokens...\n")

    # Exchange code for tokens
    resp = requests.post(
        TOKEN_URL,
        auth=(CLIENT_ID, CLIENT_SECRET),
        headers={"Accept": "application/json"},
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": REDIRECT_URI,
        },
    )

    if resp.status_code != 200:
        print(f"ERROR: Token exchange failed ({resp.status_code}):")
        print(resp.text)
        return

    tokens = resp.json()
    refresh_token = tokens["refresh_token"]
    access_token = tokens["access_token"]

    print("✅ Success! Got tokens.\n")

    # Save to .env
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        lines = open(env_path).readlines()
        with open(env_path, "w") as f:
            found = False
            for line in lines:
                if line.startswith("QUICKBOOKS_REFRESH_TOKEN"):
                    f.write(f"QUICKBOOKS_REFRESH_TOKEN={refresh_token}\n")
                    found = True
                elif line.startswith("QUICKBOOKS_COMPANY_ID") and realm_id:
                    f.write(f"QUICKBOOKS_COMPANY_ID={realm_id}\n")
                else:
                    f.write(line)
            if not found:
                f.write(f"QUICKBOOKS_REFRESH_TOKEN={refresh_token}\n")
        print(f"✅ Saved refresh token to .env")
    else:
        with open(env_path, "w") as f:
            f.write(f"QUICKBOOKS_CLIENT_ID={CLIENT_ID}\n")
            f.write(f"QUICKBOOKS_CLIENT_SECRET={CLIENT_SECRET}\n")
            f.write(f"QUICKBOOKS_REFRESH_TOKEN={refresh_token}\n")
            f.write(f"QUICKBOOKS_COMPANY_ID={realm_id or COMPANY_ID}\n")
            f.write(f"QUICKBOOKS_ENV=sandbox\n")
        print(f"✅ Created .env with all credentials")

    print(f"\n📋 Summary:")
    print(f"   Company ID: {realm_id or COMPANY_ID}")
    print(f"   Refresh Token: {refresh_token[:20]}...")
    print(f"\n🚀 You're all set! Restart Claude Desktop and start asking questions about your books.")


if __name__ == "__main__":
    main()
