"""Tests for GET /api/config, GET /api/health, and GET /api/conversation/{id} basics."""

import uuid

from app import config, db


def test_get_config_returns_owner_name(client):
    resp = client.get("/api/config")
    assert resp.status_code == 200
    assert resp.json() == {"owner_name": config.OWNER_NAME}


def test_get_health_returns_ok_when_supabase_reachable(client):
    """RECS.md: 'Fly health check never touches Supabase' -- /api/config alone
    can't catch a DB outage since it never queries the database."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_get_health_returns_503_when_supabase_unreachable(client, monkeypatch):
    def _boom():
        raise RuntimeError("simulated Supabase outage")

    monkeypatch.setattr(db, "health_check", _boom)
    resp = client.get("/api/health")
    assert resp.status_code == 503


def test_get_conversation_invalid_id_returns_400(client):
    resp = client.get("/api/conversation/not-a-uuid")
    assert resp.status_code == 400


def test_get_conversation_unknown_id_returns_empty_list(client):
    conversation_id = str(uuid.uuid4())
    resp = client.get(f"/api/conversation/{conversation_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["conversation_id"] == conversation_id
    assert body["messages"] == []
