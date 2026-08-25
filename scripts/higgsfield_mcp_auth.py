"""Higgsfield MCP icin bearer token al ve .mcp.json'a yaz.

Neden: mcp.higgsfield.ai kendini issuer olarak ilan ediyor ama yetkilendirmeyi
Clerk'e proxy'liyor ve callback'te upstream'in `iss` degerini
(https://clerk.higgsfield.ai) oldugu gibi geciriyor. Claude Code bunu RFC 9207
geregi reddediyor ("Issuer mismatch in authorization response"). Akisi burada
kendimiz yurutup token'i statik header olarak veriyoruz; boylece Claude Code
hic OAuth'a girmiyor.

Kullanim: python scripts/higgsfield_mcp_auth.py
Token 24 saat gecerli; suresi dolunca ayni komutu tekrar calistir (refresh
token varsa tarayici acilmaz).
"""
import base64
import hashlib
import http.server
import json
import os
import secrets
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

AS = "https://mcp.higgsfield.ai"
RESOURCE = f"{AS}/mcp"
PORT = 8765
REDIRECT = f"http://localhost:{PORT}/callback"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN_FILE = os.path.join(ROOT, ".higgsfield_token.json")
MCP_JSON = os.path.join(ROOT, ".mcp.json")


def post(url, payload, form=False):
    if form:
        data = urllib.parse.urlencode(payload).encode()
        content_type = "application/x-www-form-urlencoded"
    else:
        data = json.dumps(payload).encode()
        content_type = "application/json"
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": content_type}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def refresh(saved):
    """Kayitli refresh token ile yeni access token al; olmazsa None don."""
    if not saved.get("refresh_token"):
        return None
    try:
        tok = post(f"{AS}/oauth2/token", {
            "grant_type": "refresh_token",
            "refresh_token": saved["refresh_token"],
            "client_id": saved["client_id"],
            "resource": RESOURCE,
        }, form=True)
    except urllib.error.HTTPError as e:
        print(f"refresh basarisiz ({e.code}), yeniden yetkilendirme gerekiyor")
        return None
    tok.setdefault("refresh_token", saved["refresh_token"])
    tok["client_id"] = saved["client_id"]
    return tok


def authorize():
    """Tarayici uzerinden PKCE authorization-code akisi."""
    client = post(f"{AS}/oauth2/register", {
        "client_name": "claude-code-local",
        "redirect_uris": [REDIRECT],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": "openid email offline_access",
    })
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    auth_url = f"{AS}/oauth2/authorize?" + urllib.parse.urlencode({
        "response_type": "code",
        "client_id": client["client_id"],
        "redirect_uri": REDIRECT,
        "scope": "openid email offline_access",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": RESOURCE,
    })

    got = {}
    done = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def _finish(self, params):
            # Tarayici favicon vb. icin de istek atiyor; ayrica onceki
            # denemelerden kalan sekmeler eski state ile geri donebiliyor.
            # Sadece bu akisa ait callback'i kabul et, gerisini yok say.
            if "code" not in params and "error" not in params:
                self.send_error(404)
                return
            if params.get("state") != state:
                print("eski/yabanci callback yok sayildi (state uyusmuyor)")
                self.send_error(400)
                return
            got.update(params)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<h2>Tamam, sekmeyi kapatabilirsin.</h2>".encode())
            done.set()

        def do_GET(self):
            query = urllib.parse.urlparse(self.path).query
            self._finish({k: v[0] for k, v in urllib.parse.parse_qs(query).items()})

        def do_POST(self):  # response_mode=form_post ihtimaline karsi
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode()
            self._finish({k: v[0] for k, v in urllib.parse.parse_qs(body).items()})

        def log_message(self, *args):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print("Tarayici aciliyor. Acilmazsa su adrese git:\n" + auth_url)
    webbrowser.open(auth_url)
    if not done.wait(600):
        raise SystemExit("timeout: callback gelmedi")
    srv.shutdown()

    if "code" not in got:
        raise SystemExit(f"callback'te code yok: {got}")

    tok = post(f"{AS}/oauth2/token", {
        "grant_type": "authorization_code",
        "code": got["code"],
        "redirect_uri": REDIRECT,
        "client_id": client["client_id"],
        "code_verifier": verifier,
        "resource": RESOURCE,
    }, form=True)
    tok["client_id"] = client["client_id"]
    return tok


def smoke_test(access_token):
    """MCP initialize cagrisi; token gercekten gecerli mi."""
    body = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "higgsfield-mcp-auth", "version": "1"},
        },
    }).encode()
    req = urllib.request.Request(RESOURCE, data=body, method="POST", headers={
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.read(400).decode("utf-8", "replace")


saved = {}
if os.path.exists(TOKEN_FILE):
    with open(TOKEN_FILE, encoding="utf-8") as f:
        saved = json.load(f)

token = refresh(saved) if saved else None
if token is None:
    token = authorize()

with open(TOKEN_FILE, "w", encoding="utf-8") as f:
    json.dump(token, f, indent=2)
os.chmod(TOKEN_FILE, 0o600)

config = {"mcpServers": {"higgsfield": {
    "type": "http",
    "url": RESOURCE,
    "headers": {"Authorization": f"Bearer {token['access_token']}"},
}}}
with open(MCP_JSON, "w", encoding="utf-8") as f:
    json.dump(config, f, indent=2)

status, preview = smoke_test(token["access_token"])
print(f"MCP initialize -> HTTP {status}")
print(preview.splitlines()[0] if preview else "(bos yanit)")
print(f"token yazildi: {TOKEN_FILE} (gecerlilik {token.get('expires_in')} sn)")
print(f".mcp.json guncellendi: {MCP_JSON}")
print("Claude Code'u yeniden baslat, sonra /mcp ile kontrol et.")
