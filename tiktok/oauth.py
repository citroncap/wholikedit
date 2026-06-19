"""TikTok OAuth 2.0 flow with local callback HTTP server.

Flow:
  1. App generates a CSRF state token, starts local HTTP server on 127.0.0.1:8765
  2. Opens system default browser to the TikTok authorization URL
  3. User authenticates on the TikTok website and grants permissions
  4. TikTok redirects to http://127.0.0.1:8765/callback?code=...&state=...
  5. CallbackServer captures the code, shuts down, and unblocks the thread
  6. App verifies the CSRF state token
  7. App exchanges the authorization code for access + refresh tokens
  8. App fetches the real TikTok user info to verify the token works
  9. Tokens are encrypted and stored locally via LocalPlayer

IMPORTANT: This module NEVER auto-authenticates, generates fake users, or
simulates a successful login. Mock mode is a developer-only feature that must
be explicitly enabled via Settings → "Use demo data (no real TikTok account)".
"""
from __future__ import annotations
import hashlib
import logging
import secrets
import threading
import time
import webbrowser
import urllib.parse
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional
from PyQt6.QtCore import QThread, pyqtSignal
from utils.config import (
    TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET,
    TIKTOK_REDIRECT_URI, TIKTOK_OAUTH_SCOPE,
    TIKTOK_AUTH_URL, TIKTOK_TOKEN_URL, OAUTH_CALLBACK_PORT,
)
from utils.security import generate_state_token

log = logging.getLogger(__name__)

# Sentinel value set during project setup — means API credentials are missing.
_PLACEHOLDER_KEY = "your_client_key_here"

# How long (seconds) to wait for the user to complete the browser flow.
_CALLBACK_TIMEOUT = 300  # 5 minutes


def _generate_code_verifier() -> str:
    """RFC7636 §4.1 — 96 random bytes → 128-char URL-safe base64 string."""
    return secrets.token_urlsafe(96)


def _generate_code_challenge(verifier: str) -> str:
    """TikTok-specific PKCE: hex(SHA256(verifier)).

    TikTok deviates from RFC7636 — they require hex encoding, NOT base64url.
    Ref: developers.tiktok.com Login Kit for Desktop guide.
    """
    return hashlib.sha256(verifier.encode("ascii")).hexdigest()


_SUCCESS_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Connected</title>
<style>body{background:#0a0a0a;color:#fff;font-family:Segoe UI,sans-serif;
display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}
.box{text-align:center}.icon{font-size:4rem}.title{font-size:2rem;
color:#FE2C55;font-weight:700;margin:.5rem 0}.sub{color:#888}</style></head>
<body><div class="box"><div class="icon">&#x2705;</div>
<div class="title">Connected!</div>
<div class="sub">You can close this tab and return to WhoLikedIt?</div>
</div></body></html>"""

_ERROR_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Authorization failed</title>
<style>body{background:#0a0a0a;color:#fff;font-family:Segoe UI,sans-serif;
display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}
.box{text-align:center}.icon{font-size:4rem}.title{font-size:2rem;
color:#E74C3C;font-weight:700;margin:.5rem 0}.sub{color:#888}</style></head>
<body><div class="box"><div class="icon">&#x274C;</div>
<div class="title">Authorization failed</div>
<div class="sub">Please return to WhoLikedIt? and try again.</div>
</div></body></html>"""

_CANCEL_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Cancelled</title>
<style>body{background:#0a0a0a;color:#fff;font-family:Segoe UI,sans-serif;
display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}
.box{text-align:center}.icon{font-size:4rem}.title{font-size:2rem;
color:#888;font-weight:700;margin:.5rem 0}.sub{color:#555}</style></head>
<body><div class="box"><div class="icon">&#x1F6AB;</div>
<div class="title">Cancelled</div>
<div class="sub">Close this tab and return to WhoLikedIt?</div>
</div></body></html>"""


class _CallbackHandler(BaseHTTPRequestHandler):
    """Handles a single OAuth callback GET request.

    Results are written onto `self.server.oauth_result` (a dict on the
    HTTPServer instance) so that multiple OAuthFlow attempts in the same
    session never share stale class-level state.
    """

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)

        # Ignore favicon requests or anything not on /callback
        if parsed.path != "/callback":
            self.send_response(204)
            self.end_headers()
            return

        params = urllib.parse.parse_qs(parsed.query)
        code  = params.get("code",  [None])[0]
        state = params.get("state", [None])[0]
        error = params.get("error", [None])[0]

        log.debug(
            "OAuth callback received — path=%s code_present=%s state_present=%s error=%s",
            parsed.path, bool(code), bool(state), error,
        )

        # Write result to the server instance, not a class variable
        if code:
            self.server.oauth_result = {"code": code, "state": state, "error": None}
            self._respond(200, _SUCCESS_HTML)
        elif error == "access_denied":
            self.server.oauth_result = {"code": None, "state": None, "error": "access_denied"}
            self._respond(200, _CANCEL_HTML)
        else:
            self.server.oauth_result = {
                "code": None, "state": None,
                "error": error or "unknown_error",
            }
            self._respond(400, _ERROR_HTML)

        # Shut down the server from a daemon thread so this handler can return
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def _respond(self, status: int, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, fmt, *args):  # silence default HTTP access log
        pass


class OAuthFlow(QThread):
    """Runs the full TikTok OAuth flow in a background thread.

    Parameters
    ----------
    client_key, client_secret
        TikTok developer app credentials.  Pass the user-configured values
        from Settings; leave empty to fall back to the compiled-in constants
        (which default to placeholder values).
    use_mock
        Developer-only flag.  When True the flow emits fake credentials after
        a short delay without opening a browser.  Must never be True in a
        production build unless the user explicitly opts in via Settings.

    Emits:
      success(access_token, refresh_token, open_id, display_name)
      failure(human_readable_reason)
      status_update(message)   — intermediate progress for the UI
    """
    success       = pyqtSignal(str, str, str, str)
    failure       = pyqtSignal(str)
    status_update = pyqtSignal(str)

    def __init__(
        self,
        client_key:    str  = "",
        client_secret: str  = "",
        use_mock:      bool = False,
    ) -> None:
        super().__init__()
        # Prefer caller-supplied credentials; fall back to compiled-in constants.
        self._client_key    = client_key.strip()    or TIKTOK_CLIENT_KEY
        self._client_secret = client_secret.strip() or TIKTOK_CLIENT_SECRET
        self._use_mock      = use_mock
        self._state_token   = generate_state_token()
        self._code_verifier = _generate_code_verifier()
        self._cancelled     = False

    def cancel(self) -> None:
        self._cancelled = True
        log.info("OAuthFlow.cancel() called by user")

    # ── Entry point ───────────────────────────────────────────────────────────

    def run(self) -> None:
        if self._use_mock:
            log.warning(
                "[DEMO MODE] Mock OAuth flow starting — "
                "NO real TikTok login will occur. "
                "Disable 'Use demo data' in Settings for real authentication."
            )
            self._run_mock()
        else:
            self._run_real()

    # ── Developer demo mode ───────────────────────────────────────────────────

    def _run_mock(self) -> None:
        """Developer demo — emits fake credentials after a short delay.

        This code path must NEVER run in production. It exists so developers
        can test game mechanics without a live TikTok API key.
        """
        self.status_update.emit("Demo mode: simulating browser login…")
        time.sleep(1.5)
        if self._cancelled:
            log.info("[DEMO MODE] Flow cancelled before completion.")
            return
        log.warning(
            "[DEMO MODE] Emitting fake credentials. "
            "This account is NOT a real TikTok account."
        )
        self.status_update.emit("Demo mode: authenticated as @DemoUser")
        self.success.emit(
            "demo_access_token",
            "demo_refresh_token",
            "demo_open_id_00000",
            "DemoUser",
        )

    # ── Real OAuth flow ───────────────────────────────────────────────────────

    def _run_real(self) -> None:
        log.info("Starting real TikTok OAuth flow")

        # ── Step 0: Credential sanity check ───────────────────────────────────
        if self._client_key == _PLACEHOLDER_KEY or not self._client_key:
            msg = (
                "TikTok API credentials are not configured.\n\n"
                "Go to Settings → TikTok API Setup and enter your Client Key "
                "and Client Secret from the TikTok Developer Portal "
                "(developers.tiktok.com).\n\n"
                "Or enable Developer Demo Mode in Settings to try the game "
                "without a real TikTok account."
            )
            log.error("OAuth aborted — credentials not configured")
            self.failure.emit(msg)
            return

        # ── Step 1: Start local callback server ───────────────────────────────
        log.info("Starting local OAuth callback server on 127.0.0.1:%d", OAUTH_CALLBACK_PORT)
        self.status_update.emit("Starting local callback server…")
        try:
            server = HTTPServer(("127.0.0.1", OAUTH_CALLBACK_PORT), _CallbackHandler)
        except OSError as exc:
            msg = (
                f"Cannot start callback server on port {OAUTH_CALLBACK_PORT}: {exc}\n"
                "Another application may be using this port. "
                "Close it and try again."
            )
            log.error("OAuth aborted: %s", msg)
            self.failure.emit(msg)
            return

        # Initialise the result slot so the handler always has somewhere to write
        server.oauth_result = {"code": None, "state": None, "error": None}
        server.timeout = _CALLBACK_TIMEOUT  # affects select() in serve_forever

        # ── Step 2: Build authorization URL ───────────────────────────────────
        auth_url = self._build_auth_url()
        log.info("OAuth authorization URL: %s", auth_url)

        # ── Step 3: Open system browser ───────────────────────────────────────
        self.status_update.emit("Opening TikTok login page in your browser…")
        try:
            opened = webbrowser.open(auth_url)
            if not opened:
                raise RuntimeError("webbrowser.open() returned False")
            log.info("Browser opened successfully")
        except Exception as exc:
            log.error("Failed to open browser: %s", exc)
            server.server_close()
            self.failure.emit(
                f"Could not open your browser automatically.\n"
                f"Please open this URL manually:\n{auth_url}\n\nError: {exc}"
            )
            return

        # ── Step 4: Wait for callback (blocks until handler shuts server down)
        self.status_update.emit(
            "Waiting for you to log in to TikTok in your browser…\n"
            "(This window will update automatically after you grant access)"
        )
        log.info("Waiting for OAuth callback (timeout=%ds)…", _CALLBACK_TIMEOUT)

        # Run the server in a separate thread so we can watch for cancellation
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        deadline = time.monotonic() + _CALLBACK_TIMEOUT
        while server_thread.is_alive():
            if self._cancelled:
                log.info("OAuth flow cancelled by user while waiting for callback")
                server.shutdown()
                server_thread.join(timeout=2)
                return
            if time.monotonic() > deadline:
                log.warning("OAuth callback timed out after %ds", _CALLBACK_TIMEOUT)
                server.shutdown()
                server_thread.join(timeout=2)
                self.failure.emit(
                    "Timed out waiting for TikTok login.\n"
                    "The login page was open for too long. Please try again."
                )
                return
            time.sleep(0.25)

        result = server.oauth_result
        log.debug("Callback result: error=%s code_present=%s", result["error"], bool(result["code"]))

        if self._cancelled:
            return

        # ── Step 5: Check for errors returned by TikTok ───────────────────────
        if result["error"]:
            if result["error"] == "access_denied":
                log.info("User denied TikTok authorization")
                self.failure.emit("Authorization cancelled. You declined to grant access.")
            else:
                log.error("TikTok returned OAuth error: %s", result["error"])
                self.failure.emit(f"TikTok returned an error: {result['error']}")
            return

        if not result["code"]:
            log.error("OAuth callback received but no authorization code was present")
            self.failure.emit("No authorization code received. The login may have been interrupted.")
            return

        # ── Step 6: Verify CSRF state token ───────────────────────────────────
        log.debug("Verifying CSRF state token")
        if result["state"] != self._state_token:
            log.error(
                "CSRF state mismatch! expected=%s got=%s",
                self._state_token, result["state"],
            )
            self.failure.emit(
                "Security check failed: state token mismatch.\n"
                "This may indicate a CSRF attack. Please try again."
            )
            return
        log.info("CSRF state token verified OK")

        # ── Step 7: Exchange authorization code for tokens ────────────────────
        self.status_update.emit("Exchanging authorization code for access token…")
        log.info("Exchanging authorization code for tokens")
        tokens = self._exchange_code(result["code"])
        if tokens is None:
            return  # failure already emitted inside _exchange_code

        access_token, refresh_token = tokens
        log.info("Token exchange succeeded (access_token length=%d)", len(access_token))

        if self._cancelled:
            return

        # ── Step 8: Retrieve authenticated user's profile ─────────────────────
        self.status_update.emit("Retrieving your TikTok profile…")
        log.info("Fetching TikTok user info to verify token")
        from tiktok.provider import RealTikTokProvider
        provider = RealTikTokProvider()
        info = provider.get_user_info(access_token)
        if not info:
            log.error("get_user_info returned None — token may be invalid or insufficient scope")
            self.failure.emit(
                "Connected to TikTok but could not retrieve your profile.\n"
                "Ensure the app has 'user.info.basic' scope and try again."
            )
            return

        open_id      = info.get("open_id", "")
        display_name = info.get("display_name") or info.get("nickname") or "TikTokUser"
        log.info(
            "TikTok authentication successful — open_id=%s display_name=%s",
            open_id, display_name,
        )

        # ── Step 9: Emit success with REAL credentials ────────────────────────
        self.status_update.emit(f"Successfully connected as @{display_name}")
        self.success.emit(access_token, refresh_token or "", open_id, display_name)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_auth_url(self) -> str:
        challenge = _generate_code_challenge(self._code_verifier)
        log.debug("PKCE code_verifier length=%d", len(self._code_verifier))
        log.debug("PKCE code_challenge=%s", challenge)
        log.debug("PKCE redirect_uri=%s", TIKTOK_REDIRECT_URI)
        params = {
            "client_key":           self._client_key,
            "response_type":        "code",
            "scope":                TIKTOK_OAUTH_SCOPE,
            "redirect_uri":         TIKTOK_REDIRECT_URI,
            "state":                self._state_token,
            "code_challenge":       challenge,
            "code_challenge_method": "S256",
        }
        url = TIKTOK_AUTH_URL + "?" + urllib.parse.urlencode(params)
        log.debug(
            "Built OAuth URL (client_key=%s…): %s",
            self._client_key[:6] if len(self._client_key) > 6 else "??",
            url,
        )
        return url

    def _exchange_code(
        self, code: str
    ) -> Optional[tuple[str, Optional[str]]]:
        log.debug("POSTing to token endpoint: %s", TIKTOK_TOKEN_URL)
        try:
            resp = requests.post(
                TIKTOK_TOKEN_URL,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "client_key":    self._client_key,
                    "client_secret": self._client_secret,
                    "code":          code,
                    "grant_type":    "authorization_code",
                    "redirect_uri":  TIKTOK_REDIRECT_URI,
                    "code_verifier": self._code_verifier,
                },
                timeout=15,
            )
            log.debug(
                "Token endpoint response: HTTP %d (content-type=%s)",
                resp.status_code,
                resp.headers.get("content-type", "?"),
            )
            log.debug("Token exchange response body: %s", resp.text[:500])
            resp.raise_for_status()
            data = resp.json()
            log.debug("Token response keys: %s", list(data.keys()))

            # TikTok wraps the token under data.data in some API versions
            payload = data.get("data") or data
            if "error" in data and data["error"]:
                err_desc = data.get("error_description", data["error"])
                log.error("Token exchange error from TikTok: %s", err_desc)
                self.failure.emit(f"Token exchange failed: {err_desc}")
                return None

            access  = payload.get("access_token", "")
            refresh = payload.get("refresh_token")

            if not access:
                log.error(
                    "No access_token in token response. Full response: %s", data
                )
                self.failure.emit(
                    "TikTok returned a response but it contained no access token.\n"
                    "Check that your redirect URI exactly matches what is registered "
                    "in the TikTok developer portal."
                )
                return None

            return access, refresh

        except requests.HTTPError as exc:
            log.error(
                "Token exchange HTTP error: %s — response body: %s",
                exc, exc.response.text if exc.response else "(no body)",
            )
            self.failure.emit(
                f"Token exchange HTTP error ({exc.response.status_code if exc.response else '?'}): "
                f"{exc}"
            )
            return None
        except requests.ConnectionError as exc:
            log.error("Token exchange connection error: %s", exc)
            self.failure.emit(
                "Could not reach TikTok's token endpoint. "
                "Check your internet connection and try again."
            )
            return None
        except Exception as exc:
            log.error("Token exchange unexpected error: %s", exc, exc_info=True)
            self.failure.emit(f"Token exchange failed unexpectedly: {exc}")
            return None


# ── Standalone token refresh ──────────────────────────────────────────────────

def refresh_access_token(refresh_token: str) -> Optional[str]:
    """Exchange a refresh token for a new access token.

    Returns the new access token, or None if the refresh failed.
    Logs the outcome but does not raise.
    """
    log.info("Attempting token refresh")
    try:
        resp = requests.post(
            TIKTOK_TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "client_key":    TIKTOK_CLIENT_KEY,
                "client_secret": TIKTOK_CLIENT_SECRET,
                "grant_type":    "refresh_token",
                "refresh_token": refresh_token,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        payload = data.get("data") or data
        new_token = payload.get("access_token")
        if new_token:
            log.info("Token refresh succeeded")
        else:
            log.warning("Token refresh response had no access_token: %s", data)
        return new_token
    except Exception as exc:
        log.error("Token refresh failed: %s", exc)
        return None
