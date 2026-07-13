"""Admin login/logout and the critical "no auth => 401" security guarantee."""

import uuid

import pytest

from app import config, ratelimit


@pytest.fixture(autouse=True)
def _reset_admin_login_limiter():
    """Each login test brute-forces from the same TestClient IP; clear both windows
    before and after so tests don't bleed into each other's rate-limit counters."""
    ip = "testclient"
    ratelimit._limiter.clear(ratelimit._admin_login_rate, "admin_login", ip)
    ratelimit.reset_admin_login_lockout(ip)
    yield
    ratelimit._limiter.clear(ratelimit._admin_login_rate, "admin_login", ip)
    ratelimit.reset_admin_login_lockout(ip)


def test_admin_login_wrong_password_returns_401(client):
    resp = client.post("/admin/login", json={"password": "definitely-wrong"})
    assert resp.status_code == 401


def test_admin_login_locks_out_after_five_failures(client):
    for _ in range(5):
        resp = client.post("/admin/login", json={"password": "definitely-wrong"})
        assert resp.status_code == 401

    # 6th attempt is blocked by the lockout window even with the correct password.
    resp = client.post("/admin/login", json={"password": config.ADMIN_PASSWORD})
    assert resp.status_code == 429
    assert "too many" in resp.json()["error"].lower()


def test_admin_login_success_resets_the_lockout_counter(client):
    for _ in range(4):
        resp = client.post("/admin/login", json={"password": "definitely-wrong"})
        assert resp.status_code == 401

    resp = client.post("/admin/login", json={"password": config.ADMIN_PASSWORD})
    assert resp.status_code == 200

    # The successful login cleared the failure count, so 4 more wrong guesses
    # don't trip the lockout that a run of 8 straight failures would have.
    for _ in range(4):
        resp = client.post("/admin/login", json={"password": "definitely-wrong"})
        assert resp.status_code == 401


def test_admin_login_rate_limited_after_ten_calls_per_minute(client):
    for _ in range(10):
        resp = client.post("/admin/login", json={"password": config.ADMIN_PASSWORD})
        assert resp.status_code == 200

    resp = client.post("/admin/login", json={"password": config.ADMIN_PASSWORD})
    assert resp.status_code == 429


def test_admin_login_correct_password_sets_cookie(client):
    resp = client.post("/admin/login", json={"password": config.ADMIN_PASSWORD})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert config.ADMIN_SESSION_COOKIE in resp.cookies
    cookie = client.cookies.get(config.ADMIN_SESSION_COOKIE)
    assert cookie


def test_admin_logout_clears_cookie(admin_client):
    assert admin_client.cookies.get(config.ADMIN_SESSION_COOKIE)
    resp = admin_client.post("/admin/logout")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    # After logout, the previously-authenticated client should be rejected.
    resp2 = admin_client.get("/admin/conversations")
    assert resp2.status_code == 401


@pytest.mark.parametrize(
    "method,path_suffix",
    [
        ("GET", "conversations"),
        ("POST", "conversations/{id}"),
        ("POST", "conversations/{id}/messages"),
        ("POST", "conversations/{id}/resolve"),
    ],
)
def test_admin_routes_require_auth_no_cookie(client, method, path_suffix):
    conversation_id = str(uuid.uuid4())
    path = "/admin/" + path_suffix.format(id=conversation_id)
    if method == "GET":
        resp = client.get(path)
    else:
        resp = client.post(path, json={"content": "hello"})
    assert resp.status_code == 401


@pytest.mark.parametrize(
    "method,path_suffix",
    [
        ("GET", "conversations"),
        ("POST", "conversations/{id}"),
        ("POST", "conversations/{id}/messages"),
        ("POST", "conversations/{id}/resolve"),
    ],
)
def test_admin_routes_succeed_with_valid_cookie(admin_client, method, path_suffix):
    conversation_id = str(uuid.uuid4())
    path = "/admin/" + path_suffix.format(id=conversation_id)
    if method == "GET":
        resp = admin_client.get(path)
    else:
        resp = admin_client.post(path, json={"content": "hello from admin auth test"})
    assert resp.status_code != 401


def test_admin_routes_reject_garbage_cookie(client):
    client.cookies.set(config.ADMIN_SESSION_COOKIE, "garbage-not-a-real-token")
    resp = client.get("/admin/conversations")
    assert resp.status_code == 401
