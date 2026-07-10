"""Admin login/logout and the critical "no auth => 401" security guarantee."""

import uuid

import pytest

from app import config


def test_admin_login_wrong_password_returns_401(client):
    resp = client.post("/admin/login", json={"password": "definitely-wrong"})
    assert resp.status_code == 401


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
        ("GET", "conversations/{id}"),
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
        ("GET", "conversations/{id}"),
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
