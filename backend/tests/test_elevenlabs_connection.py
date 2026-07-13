"""Connectivity check for the ElevenLabs Agents platform (SPEC-VOICE.md "Setup and
Validation" step 6): confirms ELEVENLABS_API_KEY is valid, ELEVENLABS_AGENT_ID
resolves to the configured agent, and a connection credential can be minted
end-to-end -- before relying on the full voice UI. Mirrors
test_supabase_connection.py's role for the messages table.

Marked elevenlabs_live (not run by default the way the Supabase check is,
since ELEVENLABS_* is optional -- SPEC-VOICE.md's voice channel is opt-in on
top of the base app): run with `-m elevenlabs_live` once voice is configured,
or omit `-m "not elevenlabs_live"` to include it in a full pass.
"""

import pytest

from app import config, voice


@pytest.mark.elevenlabs_live
def test_env_present():
    # Unlike SUPABASE_*, ELEVENLABS_* is optional (voice is opt-in on top of the
    # base app -- SPEC-VOICE.md), so this is marked elevenlabs_live too rather
    # than always-on like test_supabase_connection.py's equivalent.
    assert config.ELEVENLABS_API_KEY, "ELEVENLABS_API_KEY not set"
    assert config.ELEVENLABS_AGENT_ID, "ELEVENLABS_AGENT_ID not set"


@pytest.mark.elevenlabs_live
def test_mint_conversation_token_succeeds():
    """A single successful call validates all three things SPEC-VOICE.md step 6
    asks for at once: ELEVENLABS_API_KEY is valid, ELEVENLABS_AGENT_ID resolves
    (it's passed as a param to this same request), and a connection credential
    can be minted end-to-end."""
    token = voice.mint_conversation_token()
    assert isinstance(token, str)
    assert token
