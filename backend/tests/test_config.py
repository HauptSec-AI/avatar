"""Tests for GET /api/config and GET /api/conversation/{id} basics."""

import uuid

from app import config


def test_get_config_returns_owner_name(client):
    resp = client.get("/api/config")
    assert resp.status_code == 200
    assert resp.json() == {"owner_name": config.OWNER_NAME}


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
