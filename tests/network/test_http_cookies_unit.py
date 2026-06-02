from fastapi.responses import JSONResponse

from democrai.core.infrastructure.network.http import cookies as cookies_mod


def test_set_and_clear_auth_cookie(monkeypatch):
    monkeypatch.setattr(cookies_mod, "auth_cookie_name", lambda: "auth")
    monkeypatch.setattr(cookies_mod, "auth_cookie_http_only", lambda: True)
    monkeypatch.setattr(cookies_mod, "auth_cookie_secure", lambda: False)
    monkeypatch.setattr(cookies_mod, "auth_cookie_samesite", lambda: "lax")
    monkeypatch.setattr(cookies_mod, "auth_cookie_domain", lambda: "example.local")

    response = JSONResponse(content={"ok": True})
    cookies_mod.set_auth_cookie(response, "jwt")
    header = response.headers.get("set-cookie", "")
    assert "auth=jwt" in header
    assert "Domain=example.local" in header

    response2 = JSONResponse(content={"ok": True})
    cookies_mod.clear_auth_cookie(response2)
    header2 = response2.headers.get("set-cookie", "")
    assert "auth=" in header2
    assert "expires=" in header2.lower()


def test_set_session_cookie(monkeypatch):
    monkeypatch.setattr(cookies_mod, "session_cookie_name", lambda: "sess")
    monkeypatch.setattr(cookies_mod, "auth_cookie_http_only", lambda: True)
    monkeypatch.setattr(cookies_mod, "auth_cookie_secure", lambda: True)
    monkeypatch.setattr(cookies_mod, "auth_cookie_samesite", lambda: "none")
    monkeypatch.setattr(cookies_mod, "auth_cookie_domain", lambda: "example.local")

    response = JSONResponse(content={"ok": True})
    cookies_mod.set_session_cookie(response, "k1")
    header = response.headers.get("set-cookie", "")
    assert "sess=k1" in header
    assert "SameSite=none" in header
