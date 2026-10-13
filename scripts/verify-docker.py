"""End-to-end local checks using only Python's standard library.

Exercises the same authorization-code + S256 PKCE flow as Scalar.
Never prints access tokens, refresh tokens, or passwords.
"""
import base64
import hashlib
import http.cookiejar
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

API = "https://localhost:7001"
ISSUER = "http://localhost:8080/realms/fileshub"
CALLBACK = f"{API}/scalar/v1"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class LocalhostCookiePolicy(http.cookiejar.DefaultCookiePolicy):
    def return_ok_secure(self, cookie, request):
        # Browsers allow Secure cookies on http://localhost. Keycloak uses
        # this exception; Python's CookieJar does not implement it by default.
        if urllib.parse.urlsplit(request.full_url).hostname == "localhost":
            return True
        return super().return_ok_secure(cookie, request)


class LoginForm(HTMLParser):
    def __init__(self):
        super().__init__()
        self.action = None
        self.active = False
        self.fields = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form" and attrs.get("id") == "kc-form-login":
            self.action = attrs["action"]
            self.active = True
        if tag == "input" and self.active and attrs.get("type") == "hidden" and "name" in attrs:
            self.fields[attrs["name"]] = attrs.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form":
            self.active = False


opener = urllib.request.build_opener(
    NoRedirect(),
    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar(LocalhostCookiePolicy())),
)


def request(url, *, form=None, token=None, headers=None):
    request_headers = dict(headers or {})
    if token:
        request_headers["Authorization"] = f"Bearer {token}"
    data = urllib.parse.urlencode(form).encode() if form is not None else None
    req = urllib.request.Request(url, data=data, headers=request_headers)
    try:
        response = opener.open(req, timeout=20)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, response.headers, response.read().decode()


def expect(status, expected, label):
    if status != expected:
        raise RuntimeError(f"{label}: expected {expected}, got {status}")
    print(f"PASS {label}: {status}")


def main():
    status, headers, _ = request(API)
    expect(status, 302, "root redirect")
    assert headers["Location"] == "/scalar/v1"
    status, _, scalar = request(CALLBACK)
    expect(status, 200, "Scalar documentation")
    assert "keycloak-test-scalar" in scalar
    status, _, body = request(f"{API}/openapi/v1.json")
    expect(status, 200, "OpenAPI")
    document = json.loads(body)
    flow = document["components"]["securitySchemes"]["Keycloak"]["flows"]["authorizationCode"]
    assert flow["authorizationUrl"] == f"{ISSUER}/protocol/openid-connect/auth"
    for path in ("/api/me", "/api/data"):
        status, _, _ = request(f"{API}{path}")
        expect(status, 401, f"anonymous {path}")
    status, _, _ = request(f"{API}/api/me", token="invalid-token")
    expect(status, 401, "invalid token")

    status, _, body = request(f"{ISSUER}/.well-known/openid-configuration")
    expect(status, 200, "Keycloak discovery")
    metadata = json.loads(body)
    assert metadata["issuer"] == ISSUER
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(24)
    auth_query = urllib.parse.urlencode({
        "client_id": "keycloak-test-scalar", "redirect_uri": CALLBACK,
        "response_type": "code", "scope": "openid profile email",
        "code_challenge": challenge, "code_challenge_method": "S256", "state": state,
    })
    status, _, html = request(f'{metadata["authorization_endpoint"]}?{auth_query}')
    expect(status, 200, "PKCE login page")
    login = LoginForm()
    login.feed(html)
    if not login.action:
        raise RuntimeError("Keycloak login form was not found")
    login.fields.update(username="demo", password="Demo-local-2026!")
    status, headers, _ = request(login.action, form=login.fields)
    expect(status, 302, "demo user login")
    callback = urllib.parse.urlsplit(headers["Location"])
    assert f"{callback.scheme}://{callback.netloc}{callback.path}" == CALLBACK
    params = urllib.parse.parse_qs(callback.query)
    assert params.get("state") == [state]
    status, headers, body = request(metadata["token_endpoint"], form={
        "grant_type": "authorization_code", "client_id": "keycloak-test-scalar",
        "redirect_uri": CALLBACK, "code": params["code"][0], "code_verifier": verifier,
    }, headers={"Origin": API})
    expect(status, 200, "PKCE token exchange")
    assert headers.get("Access-Control-Allow-Origin") == API
    tokens = json.loads(body)
    status, _, body = request(f"{API}/api/me", token=tokens["access_token"])
    expect(status, 200, "authenticated /api/me")
    user = json.loads(body)
    assert user["id"] and user["username"] == "demo" and user["groups"] == ["/engineering"]
    assert user["email"] == "demo@example.com" and user["name"] == "Demo User"
    status, _, body = request(f"{API}/api/data", token=tokens["access_token"])
    expect(status, 200, "authenticated /api/data")
    assert json.loads(body) == [{"id": 1, "name": "First sample item"}, {"id": 2, "name": "Second sample item"}]
    status, _, _ = request(f"{API}/api/me", token=tokens["id_token"])
    expect(status, 401, "ID token rejected as API credential")
    parts = tokens["access_token"].split(".")
    parts[2] = ("A" if parts[2][0] != "A" else "B") + parts[2][1:]
    status, _, _ = request(f"{API}/api/me", token=".".join(parts))
    expect(status, 401, "tampered signature")
    print("All local Docker checks passed, including HTTPS and authorization code with PKCE.")


if __name__ == "__main__":
    main()
