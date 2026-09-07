#!/usr/bin/env python3
"""Upload and submit the extension without touching the developer console.

Chrome refuses to let any extension script the developer console, so the
browser cannot be driven there. The Chrome Web Store API is the only way to
automate this, and it covers the package and the submission.

It does NOT cover the store listing. Description, screenshots, icons and
category are console-only, in every version of this API. Change those by hand
once, and after that every code-only release goes out with `ship`.

    python3 chrome-store/cws.py auth       once, to grant access
    python3 chrome-store/cws.py status     what the store thinks is live
    python3 chrome-store/cws.py upload     send the zip, do not submit
    python3 chrome-store/cws.py publish    submit what was uploaded
    python3 chrome-store/cws.py ship       upload then publish

Credentials live in ~/.config/overleaf-comments-export/cws.json, mode 600,
outside the repo. Nothing secret is ever written into the working tree.
"""
import base64
import hashlib
import http.server
import json
import os
import pathlib
import secrets
import socket
import ssl
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import zipfile

ITEM_ID = "nbbappjfcankkjnpbaopjhejgdagaglc"
SCOPE = "https://www.googleapis.com/auth/chromewebstore"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/chromewebstore/v1.1/items"
UPLOAD = "https://www.googleapis.com/upload/chromewebstore/v1.1/items"

ROOT = pathlib.Path(__file__).resolve().parent.parent
ZIP = ROOT / "chrome-store" / "extension.zip"
CONF = pathlib.Path.home() / ".config" / "overleaf-comments-export" / "cws.json"


def die(msg):
    sys.exit(f"error: {msg}")


def load():
    if not CONF.exists():
        die(f"no credentials yet. run `python3 {sys.argv[0]} auth` first")
    return json.loads(CONF.read_text(encoding="utf-8"))


def save(conf):
    CONF.parent.mkdir(parents=True, exist_ok=True)
    # Written before the mode is set, so create it empty and locked first.
    CONF.touch(mode=0o600, exist_ok=True)
    os.chmod(CONF, 0o600)
    CONF.write_text(json.dumps(conf, indent=2) + "\n", encoding="utf-8")


def post_form(url, fields):
    body = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, context=ssl.create_default_context()) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        die(f"{url} returned {e.code}\n{e.read().decode(errors='replace')}")


def call(url, method, token, body=None):
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("x-goog-api-version", "2")
    if body is None:
        req.add_header("Content-Length", "0")
    try:
        with urllib.request.urlopen(req, context=ssl.create_default_context()) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        die(f"{method} {url} returned {e.code}\n{e.read().decode(errors='replace')}")


def access_token(conf):
    got = post_form(TOKEN_URL, {
        "client_id": conf["client_id"],
        "client_secret": conf["client_secret"],
        "refresh_token": conf["refresh_token"],
        "grant_type": "refresh_token",
    })
    return got["access_token"]


def zip_version():
    if not ZIP.exists():
        die(f"{ZIP.relative_to(ROOT)} is missing. run `bash chrome-store/build-zip.sh`")
    with zipfile.ZipFile(ZIP) as z:
        return json.loads(z.read("manifest.json"))["version"]


def pkce_challenge(verifier):
    """S256, base64url, padding stripped. Google rejects the request outright
    if the padding is left on, and the error does not say why."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def selfcheck():
    # The one vector in RFC 7636 appendix B. If this drifts, consent fails
    # with an opaque invalid_grant much later, so it is worth pinning here.
    assert pkce_challenge(
        "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    ) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    assert "=" not in pkce_challenge("x")
    v = zip_version()
    assert v.count(".") == 2 and all(p.isdigit() for p in v.split(".")), v
    assert CONF.parent != ROOT and ROOT not in CONF.parents, "secrets must live outside the repo"
    print(f"ok. zip is {v}, credentials would go to {CONF}")


# --- commands --------------------------------------------------------------

def cmd_auth():
    """Google killed the copy-a-code flow in 2022, so this catches the
    redirect on a loopback port instead. The consent happens in your own
    browser, under your own account. Nothing types your password for you."""
    client_id = os.environ.get("CWS_CLIENT_ID") or input("OAuth client ID: ").strip()
    client_secret = os.environ.get("CWS_CLIENT_SECRET") or input("OAuth client secret: ").strip()
    if not client_id or not client_secret:
        die("both the client ID and the secret are needed")

    verifier = secrets.token_urlsafe(64)
    challenge = pkce_challenge(verifier)
    state = secrets.token_urlsafe(16)

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    redirect = f"http://127.0.0.1:{port}"

    caught = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            caught.update({k: v[0] for k, v in q.items()})
            ok = caught.get("state") == state and "code" in caught
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<h2>Done. Close this tab and go back to the terminal.</h2>"
                if ok else b"<h2>That did not work. Check the terminal.</h2>")

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.handle_request, daemon=True).start()

    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",          # without this a second run gets no refresh token
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    print("Approve access in the browser window that just opened.")
    print("If it did not open, paste this into Chrome:\n\n  " + url + "\n")
    webbrowser.open(url)

    server.server_close()
    if caught.get("state") != state:
        die("the redirect did not come back with the right state. try again")
    if "code" not in caught:
        die(f"no code came back. Google said: {caught.get('error', 'nothing')}")

    got = post_form(TOKEN_URL, {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": caught["code"],
        "code_verifier": verifier,
        "grant_type": "authorization_code",
        "redirect_uri": redirect,
    })
    if "refresh_token" not in got:
        die("Google returned no refresh token. Revoke the app at "
            "https://myaccount.google.com/permissions and run auth again")

    save({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": got["refresh_token"],
        "item_id": ITEM_ID,
    })
    print(f"saved to {CONF} (mode 600)")


def cmd_status():
    conf = load()
    got = call(f"{API}/{conf['item_id']}?projection=DRAFT", "GET", access_token(conf))
    print(json.dumps(got, indent=2))


def cmd_upload():
    conf = load()
    version = zip_version()
    print(f"uploading {ZIP.relative_to(ROOT)}, manifest says {version}")
    got = call(f"{UPLOAD}/{conf['item_id']}", "PUT",
               access_token(conf), ZIP.read_bytes())
    state = got.get("uploadState")
    print(f"uploadState: {state}")
    for err in got.get("itemError", []):
        print("  " + err.get("error_detail", json.dumps(err)))
    if state != "SUCCESS":
        die("upload did not succeed, so nothing was submitted")
    return version


def cmd_publish(assume_yes=False):
    conf = load()
    if not assume_yes:
        print("This submits the uploaded package for review. Once it passes, "
              "it goes live to everyone.")
        if input("type yes to submit: ").strip().lower() != "yes":
            sys.exit("stopped, nothing submitted")
    got = call(f"{API}/{conf['item_id']}/publish", "POST", access_token(conf))
    print("status: " + ", ".join(got.get("status", ["?"])))
    for detail in got.get("statusDetail", []):
        print("  " + detail)


def cmd_ship(assume_yes=False):
    version = cmd_upload()
    print()
    if not assume_yes:
        print(f"Version {version} is uploaded but not submitted.")
    cmd_publish(assume_yes)


if __name__ == "__main__":
    args = sys.argv[1:]
    yes = "--yes" in args
    cmd = next((a for a in args if not a.startswith("-")), "")
    if cmd == "selfcheck":
        selfcheck()
    elif cmd == "auth":
        cmd_auth()
    elif cmd == "status":
        cmd_status()
    elif cmd == "upload":
        cmd_upload()
    elif cmd == "publish":
        cmd_publish(yes)
    elif cmd == "ship":
        cmd_ship(yes)
    else:
        sys.exit(__doc__)
