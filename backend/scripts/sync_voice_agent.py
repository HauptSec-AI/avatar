"""Create or update the ElevenLabs voice agent from the current project config.

Run this once to provision the agent, and again any time knowledge/, MODEL, or
this deployment's public URL changes (see SPEC-VOICE.md "Setup and Validation").
Not run automatically on every request -- provisioning is a deliberate, occasional
step, not part of the live request path.

Usage:
    cd backend && uv run python scripts/sync_voice_agent.py --base-url https://avatar-alex.fly.dev
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config, voice  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        required=True,
        help="This deployment's public URL (e.g. https://avatar-alex.fly.dev or an ngrok URL for local testing).",
    )
    args = parser.parse_args()

    creating = not config.ELEVENLABS_AGENT_ID
    action = "Creating" if creating else "Updating"
    print(f"{action} ElevenLabs voice agent for {config.OWNER_NAME} (model={config.MODEL})...")

    result = voice.sync_agent(args.base_url)

    agent_id = result.get("agent_id") or config.ELEVENLABS_AGENT_ID
    print(f"Done. agent_id = {agent_id}")
    if creating:
        print(
            "\nThis agent didn't exist yet, so it was just created. Add this to .env:\n"
            f"  ELEVENLABS_AGENT_ID={agent_id}\n"
            "then re-run this script once more so the tool webhook URLs (which depend on\n"
            "ELEVENLABS_AGENT_ID being set) are confirmed, and register the post-call\n"
            "webhook URL in the ElevenLabs dashboard for this agent:\n"
            f"  {args.base_url.rstrip('/')}/api/voice/webhook\n"
            "using ELEVENLABS_WEBHOOK_SECRET as the signing secret."
        )


if __name__ == "__main__":
    main()
