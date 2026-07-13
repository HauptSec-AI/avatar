# Avatar Voice — Spec

## Introduction

This is a companion spec to [SPEC-AVATAR.md](SPEC-AVATAR.md). It adds a **voice** channel to the Avatar digital
twin: a visitor can speak to the twin — in the owner's own cloned voice — and hear it speak back,
in addition to (not instead of) the existing text chat. The split mirrors SPEC-AVATAR.md's own convention:
**this document governs voice behaviour and its backend; SPEC-AVATAR.md remains the source of truth for
text chat, the admin dashboard, auth, and shared infrastructure (Supabase, config, deployment).**
Where the two overlap (the `messages` table, the owner's knowledge, the design system), this spec
extends SPEC-AVATAR.md rather than restating it.

The core technical decision is to let **ElevenLabs' Agents platform** (their hosted Conversational
AI product — see the naming note below) own the real-time loop: speech-to-text, the LLM turn, and
text-to-speech, all orchestrated inside ElevenLabs' infrastructure over a single WebRTC/WebSocket
session. Our backend is deliberately kept **out of the per-token hot path** — it only participates
at session start (minting a connection credential), when the agent calls a tool mid-call, and once
at the end (a post-call webhook with the full transcript). This is what "ElevenLabs-orchestrated"
means in practice, and it's the reason this design keeps latency as low as the platform allows,
rather than proxying every token through our own server.

**A naming note:** ElevenLabs has renamed this product more than once — their own docs currently
live under `/docs/eleven-agents/`, `/docs/conversational-ai/`, and `/docs/agents-platform/`
interchangeably, and their help center calls it "ElevenLabs Agents (formerly Conversational AI)."
This spec uses "ElevenLabs Agents platform" throughout. Whoever implements this should check
ElevenLabs' current dashboard/doc naming before wiring things up — the underlying API has been
stable even as the marketing name moved around, but exact doc URLs will drift.

## User Experiences

### The Voice Chat Experience

A visitor can talk to the twin in two places, both backed by the same voice module:

1. **A dedicated `/voice` page** — a voice-first landing experience for anyone who wants to talk
   rather than type (e.g. a link shared specifically for voice).
2. **Inline from the main chat page** — a "Talk live" control near the composer opens the same
   voice experience in place, without navigating away from the text thread the visitor may already
   be reading.

Starting a voice session requests microphone permission, then connects. While connected, the UI
shows: a live audio-activity visualizer (Matrix-styled — green, code-trail aesthetic, not a generic
chatbot waveform), an indicator of who's speaking (visitor / twin), and a live, scrolling caption
of the conversation so far (tentative text while the visitor is still talking, finalized once ASR
settles) — reusing the same message-bubble and tool-status visual language as text chat, so voice
doesn't look like a bolted-on widget. A visitor can mute, or end the call, at any time.

If the visitor asks to get in touch, or asks something the twin can't answer, the same two
situations from SPEC-AVATAR.md's `push_tool` apply — the twin notifies the owner immediately, live, mid-
call (not just at the end), and tells the visitor honestly that it's flagged for follow-up.

**Human-in-the-loop is async, by design and by platform constraint.** SPEC-AVATAR.md's text chat lets the
owner post directly into a conversation the Avatar is having with a visitor. True live 3-way *voice*
— the owner speaking into an in-progress call — is not just out of scope for v1, it isn't something
the ElevenLabs Agents platform exposes for browser sessions today: the only built-in call-transfer
mechanism (`transfer_to_number`) is telephony-only (a phone number over Twilio/SIP), not a way to
inject a human into a live WebRTC/WebSocket session. So: every voice turn is transcribed into the
**same conversation thread** as text (same `conversation_id`, same admin inbox row), the owner reads
and replies from the existing admin dashboard exactly as they do today, and the visitor sees or
hears that reply the next time they interact — on their next voice turn (the twin has the reply in
its transcript context) or if they switch to text. This is the same "next interaction, not
instant" characteristic text chat's async handoff already has; voice doesn't make it worse, it just
doesn't make it live either. If true live 3-way voice is wanted later, see **Q&A** below for what
that would actually require.

### The Human Admin Experience (additions)

No new screen. The existing admin inbox and thread view (SPEC-AVATAR.md) gain one small addition: a
message that originated as a spoken turn carries a small mic-icon channel badge (mirroring the
existing `Qn` instant-tag treatment), so the owner can tell at a glance which parts of a thread were
typed and which were spoken. Everything else — read/unread, needs-attention, replying, keyboard
navigation, mobile master/detail — is unchanged, because voice turns land in the same `messages`
rows the admin UI already renders.

## Implementation Decisions

- **Voice cloning is already done.** The owner has an existing ElevenLabs cloned voice; this spec
  does not cover the cloning step. The voice is referenced by `ELEVENLABS_VOICE_ID` (see below).
- **ElevenLabs' managed LLM, not Custom LLM/OpenRouter — a platform constraint, not a preference.**
  The original plan (see **Q&A** #2 below for the superseded reasoning) was Custom LLM pointed at
  OpenRouter, matching text chat's `MODEL`. Building against a real account surfaced a hard
  restriction: ElevenLabs rejects Custom LLM on any agent using an Instant Voice Clone (the exact
  error: *"Custom LLM is not allowed when using agents with Instant Voice Clones"*) — not documented
  up front, only discovered via a live 400. Since the owner's voice is an Instant Voice Clone, voice
  uses one of ElevenLabs' own managed models instead, configured via `ELEVENLABS_LLM` (default
  `gpt-4o-mini`) — a separate choice from text chat's `MODEL`/`OPENROUTER_API_KEY`, which are
  unaffected. A Professional Voice Clone would lift this restriction and let voice route through
  OpenRouter too, if that's ever wanted (re-cloning is a bigger ask than a config change, so this
  spec doesn't assume it).
- **One shared system prompt, synced, not hand-copied.** The voice agent must not drift from the
  text agent's persona, knowledge, style, and safety rules. Rather than pasting the prompt into the
  ElevenLabs dashboard once and letting it rot, the backend exposes a small sync step that pushes
  `knowledge.build_instructions()` — the exact same function that already builds the text agent's
  system prompt from the topic files in `knowledge/` (`WORK.md`, `SKILLS.md`, `PROJECTS.md`,
  `EDUCATION.md`, `PERSONAL.md`, `CONTACT.md`, `PERSONALITY.md`) and `knowledge/faq.jsonl` — to
  the ElevenLabs agent's prompt field via their agent-update API. Run it once to provision the agent
  and again any time `knowledge/` changes (see **Setup and Validation**). No second knowledge base
  is attached on the ElevenLabs side for this reason: the prompt already carries the full knowledge,
  and a second, separately-synced copy would just be another place for drift.
- **Tools mirror `faq_tool` and `push_tool` exactly**, exposed as ElevenLabs "server tools" (webhook-
  based) rather than the OpenAI Agents SDK's `@function_tool` decorator, since ElevenLabs' agent
  calls our backend directly over HTTP rather than through that SDK. Both webhook handlers call the
  *same* underlying helpers `find_faq` / `format_faq_answer` (`knowledge.py`) and `_pushover`
  (`agent_runner.py`) that the text tools already use, so the two channels can never give different
  answers to the same FAQ number or behave differently when flagging the owner.
- **Tool webhooks get our `conversation_id` directly, via the SDK's `dynamicVariables` — verified,
  not guessed.** Inspecting `@elevenlabs/client`'s own type definitions (not just docs) confirmed
  `startSession()` accepts a `dynamicVariables: Record<string, string | number | boolean>` map; the
  frontend passes `{ conversation_id: ourConversationId }` there, and the agent's tool config
  interpolates `{{conversation_id}}` into the `faq_tool`/`push_tool` webhook body. So the two tool
  endpoints just read `conversation_id` off the request — no lookup, no dependency on any ElevenLabs
  *system* variable we'd have to hope exists.
- **The post-call webhook still needs a mapping row**, because it only knows ElevenLabs' *own*
  `conversation_id`, not ours. The client SDK exposes that id once a session connects (`onConnect`);
  the browser immediately posts it, plus our own `conversation_id`, to a small backend endpoint that
  records the pairing *before* the visitor's first spoken turn, so the post-call webhook can look
  ours up when it arrives.
- **One unified conversation per visitor, across text and voice.** A `/voice` session — whether
  reached via the dedicated page or the inline launcher — uses the *same* `conversation_id` cookie
  SPEC-AVATAR.md's text chat already sets (subject to the same "Keep chat" toggle). A visitor who types,
  then talks, then types again is one thread in the admin inbox, not three. If "Keep chat" is off,
  voice gets a fresh `conversation_id` exactly like a fresh text session would.
- **The `messages` table gains one nullable column: `channel`** (`'text'` default, or `'voice'`).
  Nothing else about the schema changes — voice turns still use `role` in
  (`visitor`, `avatar`, `human`), still respect `needs_attention` / `read`, still flow through the
  exact same admin APIs. See **Tech stack decisions** for the migration.
- **The post-call webhook is the source of truth for the full transcript; live tool calls are the
  source of truth for `needs_attention`.** The moment `push_tool` fires mid-call, the backend sets
  `needs_attention` on the conversation immediately (via the same Pushover call the text tool
  makes) — the owner doesn't wait for the call to end to be notified. The complete, finalized
  transcript (all turns, correctly ordered) is written once, when the post-call webhook arrives,
  rather than being reconstructed from partial live events.
- **Abuse guards extend, not duplicate — and are honestly client-side where they have to be.**
  SPEC-AVATAR.md's per-`conversation_id` rate limit and message-length clamp exist to protect the
  OpenRouter key from a runaway *text* loop; voice's cost surface is different (ElevenLabs bills per
  minute of call time, separately from the LLM). Two guards, with different enforcement points:
  `POST /api/voice/session` (minting a connection credential) is rate-limited the same way
  `/api/chat` is — that's a real server-side gate, since it's the one place our backend is actually
  in the request path. The maximum-session-duration cap, by contrast, is enforced *client-side*
  (the frontend calls `endSession()` once the timer fires): our backend is deliberately not in the
  live call's media path at all, and no API surfaced during implementation lets it forcibly end an
  in-progress ElevenLabs session. Treat the duration cap as a UX safeguard against an accidentally
  open-ended call, not an abuse defense — the real abuse backstops are the rate-limited session
  minting above and ElevenLabs' own account-level spend/concurrency caps, the same way SPEC-AVATAR.md
  relies on OpenRouter's spend cap rather than a hard token limit for text.

### Use of the ElevenLabs Agents Platform

Be sure to use ElevenLabs' current, idiomatic integration surface: the `@elevenlabs/client` headless
JS SDK for the browser connection (not the pre-built `<elevenlabs-convai>` widget — it isn't styled
to the Matrix design system), a server-minted signed connection credential (never expose the raw
ElevenLabs API key to the browser), `ELEVENLABS_LLM` for the managed-LLM config (Custom LLM isn't
available on Instant Voice Clone agents — see above), "server tools" (webhook) for
`faq_tool`/`push_tool`, and the documented post-call webhook (HMAC-verified via the
`ElevenLabs-Signature` header) for transcript logging. Confirm current parameter names and payload
shapes against ElevenLabs' own docs at implementation time — see the naming note above.

### Tech stack decisions

**New env vars** (added to `.env`, alongside SPEC-AVATAR.md's existing list):
- `ELEVENLABS_API_KEY` — server-side only; used to mint connection credentials, call the agent-
  update (prompt sync) API, and register webhook endpoints. Never sent to the browser.
- `ELEVENLABS_AGENT_ID` — the agent created once (dashboard or the sync script below) that this
  deployment talks to.
- `ELEVENLABS_VOICE_ID` — the owner's already-cloned voice, assigned to that agent.
- `ELEVENLABS_WEBHOOK_SECRET` — used to verify the `ElevenLabs-Signature` header on the post-call
  webhook, the same way `ADMIN_PASSWORD`/session-signing already protect admin routes.
- `VOICE_MAX_SESSION_SECONDS` (optional, sensible default e.g. `600`) — the abuse-guard session cap
  from **Implementation Decisions**.
- `ELEVENLABS_LLM` (optional, default `gpt-4o-mini`) — which ElevenLabs-managed model voice uses.
  Separate from text chat's `MODEL`/`OPENROUTER_API_KEY` (see above); not an OpenRouter identifier.

**Backend additions** (`backend/app/`), following the existing module boundaries in SPEC-AVATAR.md's
`backend/app/` (`knowledge.py`, `agent_runner.py`, `main.py`, `db.py`):
- `voice.py` — new module: mints connection credentials from `ELEVENLABS_API_KEY` +
  `ELEVENLABS_AGENT_ID`; the sync function that pushes `knowledge.build_instructions()` plus the
  managed-LLM/voice config to the ElevenLabs agent-update API; HMAC verification for the post-call
  webhook.
- New public routes in `main.py`:
  - `POST /api/voice/session` — mints and returns a short-lived connection credential for the
    browser to open its ElevenLabs session with. Subject to the same per-`conversation_id` rate-
    limiting posture as `/api/chat` (a moving-window limiter; voice sessions are heavier than a
    single chat message, so this should be its own, stricter limit rather than sharing the 20/min
    text budget).
  - `POST /api/voice/session/started` — records the `{our_conversation_id, elevenlabs_conversation_id}`
    mapping described above, called by the frontend immediately after the SDK reports a connected
    session.
  - `POST /api/voice/tools/faq`, `POST /api/voice/tools/push` — the webhook targets for the two
    server tools, doing exactly what `agent_runner.faq_tool`/`push_tool` do, reusing the same
    helpers, looking up `our_conversation_id` from the mapping so `push_tool`'s notification and
    `needs_attention` update land on the right row.
  - `POST /api/voice/webhook` — the post-call transcript webhook target. Verifies the signature,
    looks up `our_conversation_id`, and inserts one `messages` row per transcript turn
    (`role='visitor'` for their `role: "user"` turns, `role='avatar'` for `role: "agent"` turns,
    `channel='voice'`), skipping any turn number already present for that conversation (webhooks can
    retry) so a redelivery doesn't duplicate the transcript.
- `db.py` — `insert_message` gains an optional `channel` parameter (default `"text"`), threaded
  through the same insert path text chat already uses; no other function changes.
- A one-off provisioning script (`backend/scripts/sync_voice_agent.py`, run manually via `uv run`)
  that creates the ElevenLabs agent on first setup (or updates it thereafter) with the current
  `MODEL`, `OPENROUTER_API_KEY`, `ELEVENLABS_VOICE_ID`, the two tool webhook URLs, and the freshly-
  built system prompt. This is the "sync," not a live per-request call — re-run it by hand whenever
  `knowledge/`, `MODEL`, or the deployed backend's public URL changes.

**Supabase migration** (extends SPEC-AVATAR.md's `create table public.messages`):
```sql
alter table public.messages
  add column channel text not null default 'text' check (channel in ('text', 'voice'));

create table public.voice_sessions (
  elevenlabs_conversation_id text primary key,
  conversation_id             uuid not null,
  started_at                  timestamptz not null default now(),
  transcript_saved            boolean not null default false,
  push_tool_used              boolean not null default false
);

grant select, insert, update, delete on public.voice_sessions to service_role;
```

**Frontend additions** (`frontend/`, following SPEC-AVATAR.md's vanilla TypeScript + Vite structure):
- `@elevenlabs/client` added as a dependency (the headless SDK — SPEC-AVATAR.md's "no framework" rule is
  unaffected; this is a small vanilla-JS client library, not a UI framework).
- `voice.html` + `voice.ts` — the dedicated `/voice` page, added as a third Vite build entry
  alongside `index.html`/`admin.html` in `vite.config.ts`.
- A shared `voiceSession.ts` module (mic permission, `Conversation.startSession`/`endSession`,
  transcript/tool/status event handling, the audio-visualizer data feed) used by *both* `voice.ts`
  and a small inline launcher wired into `chat.ts`'s existing composer area — one implementation,
  two mount points, matching how `render.ts` is already shared between `chat.ts` and `admin.ts`.
- Reuses `tokens.css`/`components.css` from the design system per SPEC-AVATAR.md; the audio visualizer and
  any voice-specific classes (e.g. speaking/listening state, mic button, live-caption line) get
  added to `components.css` (kept in sync with `design-system/components.css`, per SPEC-AVATAR.md's
  existing dual-file convention) rather than a one-off stylesheet, so voice inherits the Matrix
  dark theme and the light theme's green system-accent automatically.

## UI

Voice inherits every rule in SPEC-AVATAR.md's UI section: sharp and modern, no gradients, no left-edge
accent bars, no emoji, dark theme in the Matrix palette, light theme with the green system-accent —
and it must look and work great on mobile and desktop, in both themes, exactly like text chat does.

Additions specific to voice:
- **Audio visualizer**: driven by the SDK's input/output level and frequency data, rendered as a
  Matrix-styled bar/pulse visualization (green, code-trail aesthetic) rather than a generic chatbot
  waveform — this is the one place voice gets a genuinely new visual element, and it should feel
  like an extension of the existing "HUD grid" background texture, not a bolted-on widget.
  Different visual states for "twin speaking" vs. "listening to visitor" vs. "idle/connecting."
  Human replies keep SPEC-AVATAR.md's existing yellow-ring / stronger-glow treatment in the caption feed.
- **Live captions**: rendered in the same bubble/typography language as text chat (tentative text
  faint/lighter while still resolving, finalized text solid), and tool-status lines reuse the exact
  same `tool-status` component text chat already has for "Looking up the FAQ…" / "Notified the
  human…".
- **Mic permission and error states**: a denied/unavailable microphone, a dropped connection, and
  the session-duration cap ending a call all need clear, non-alarming inline messaging (styled like
  SPEC-AVATAR.md's existing rate-limit banner), not a bare browser permission-denial screen.
- **Entry points**: the `/voice` page's own hero (mirroring the intro screen's tone: "Talk to my
  digital twin"), and a compact "Talk live" control on the main chat page near the composer, both
  launching the same shared voice module.

## Testing

Testing follows SPEC-AVATAR.md's three-part structure (backend unit tests, Playwright frontend tests,
full Docker end-to-end), with adjustments for voice's cost and realism constraints:

1. **Backend unit tests**: webhook signature verification (valid/invalid/missing signature), the
   conversation-mapping lookup (found/not-found), transcript-insert idempotency (a redelivered
   post-call webhook must not duplicate rows), the `channel` column threading through
   `insert_message`, the two tool webhook handlers returning identical answers to their text-chat
   counterparts for the same FAQ number, and the session-duration cap actually terminating a
   session. These don't need a real ElevenLabs call — webhook payloads are fixtures.
2. **Frontend Playwright tests**: ElevenLabs' real STT/TTS/WebRTC loop is impractical (and, unlike
   OpenRouter, not something SPEC-AVATAR.md's "call the LLM freely for tests" note applies to — ElevenLabs
   Agents is billed per minute) to exercise on every test run. Use Chromium's fake-media-device flag
   (`--use-fake-device-for-media-stream`, plus a synthetic input file) to drive the *connect →
   visualizer renders → mute → end call* UI flow without a real voice round trip, and mock or
   short-circuit the SDK's session object for transcript/tool-status rendering states (mirroring how
   `chat.ts`'s streaming states were tested without needing every test to hit a real LLM). Reserve a
   *small* number of genuinely live voice smoke tests (real mic-less connect using a pre-recorded
   audio file ElevenLabs actually transcribes) for the full end-to-end pass, not the routine suite —
   run these sparingly, the same spirit as SPEC-AVATAR.md's guidance to switch to the cheap model for
   routine LLM-calling tests, but here the throttle is *call minutes*, not tokens.
3. **Full Docker end-to-end**: at least one real, live voice conversation exercised manually or via
   a scripted smoke test against the built container — visitor speaks, twin answers, a contact-
   capture flow triggers `push_tool` and a real Pushover notification, the call ends, the admin
   dashboard shows the full transcript in the same thread as any prior text messages, with the mic
   channel badge on the voice turns.

Document this as its own checklist file in `test/`, per SPEC-AVATAR.md's convention, and check items off
as they pass. When testing concludes, delete the test conversation threads (both `messages` rows and
the corresponding `voice_sessions` mapping rows) and any recorded test audio, per SPEC-AVATAR.md's existing
cleanup instruction.

## Setup and Validation

Building on SPEC-AVATAR.md's setup flow (which must already be complete and passing):

1. Confirm the owner's ElevenLabs voice clone (already done) and note its `ELEVENLABS_VOICE_ID`.
2. Add `ELEVENLABS_API_KEY`, `ELEVENLABS_AGENT_ID` (leave blank until step 3 creates it),
   `ELEVENLABS_VOICE_ID`, `ELEVENLABS_WEBHOOK_SECRET`, and (optionally) `VOICE_MAX_SESSION_SECONDS`
   to `.env`.
3. Run `backend/scripts/sync_voice_agent.py` once to create the ElevenLabs agent (or point
   `ELEVENLABS_AGENT_ID` at one created via their dashboard first, then run the script to configure
   it) with the managed-LLM config (`ELEVENLABS_LLM`), the cloned voice, the two tool webhooks, and
   the synced system prompt. Set `ELEVENLABS_AGENT_ID` in `.env` from the script's output if it created
   the agent.
4. Run the Supabase migration in **Tech stack decisions** (the `channel` column and the
   `voice_sessions` table), the same way SPEC-AVATAR.md's setup instructions run the original `messages`
   table SQL.
5. Register `POST /api/voice/webhook` as the post-call webhook URL in the ElevenLabs dashboard for
   this agent, using `ELEVENLABS_WEBHOOK_SECRET` as the signing secret.
6. **Run a connectivity/smoke check** analogous to SPEC-AVATAR.md's `test_supabase_connection.py`: confirm
   `ELEVENLABS_API_KEY` is valid, `ELEVENLABS_AGENT_ID` resolves to the agent just configured, and a
   connection credential can be minted end-to-end, before relying on the full voice UI.

## Success Criteria

This feature is only successful when: a visitor can open `/voice` (or launch voice inline from the
main chat page), speak to the twin in the owner's cloned voice, get a spoken answer sourced from the
same knowledge/FAQ/style as text chat, trigger `push_tool` mid-call with the owner notified live via
Pushover, end the call, and see/hear the complete transcript show up as ordinary messages in the
same conversation thread the owner already manages from `/admin` — indistinguishable in the admin UI
from a text conversation except for the mic channel badge. It must work on mobile and desktop, in
both themes, matching SPEC-AVATAR.md's existing bar for the text experience. Testing must be documented and
checked off in `test/` per SPEC-AVATAR.md's convention before this is considered done.

## Questions and Answers

Clarifications agreed before starting work on this spec:

1. **Human-in-the-loop for voice.** Async handoff — voice turns land in the same conversation
   thread as text; the owner replies from the existing admin dashboard; the visitor sees/hears the
   reply on their next interaction. Not just the simpler choice: ElevenLabs' Agents platform has no
   documented mechanism to inject a live human into an in-progress browser voice session today (its
   only transfer feature is telephony-only, to a phone number). A true live 3-way voice experience,
   if ever wanted, would require a materially different architecture — most plausibly, the owner
   dialing into the same call over a Twilio/SIP phone leg via `transfer_to_number`, or a hybrid where
   the owner's admin-typed message gets synthesized (via the same cloned voice) and injected into the
   live audio stream — either is a substantial follow-on project, not a variant of this one.
2. **LLM routing — superseded during implementation.** The original decision here was ElevenLabs'
   "Custom LLM" config pointed at OpenRouter, so voice and text would share one `MODEL`. Building
   against a real account found that ElevenLabs rejects Custom LLM outright on any agent using an
   Instant Voice Clone (see **Implementation Decisions** above for the exact error). Since the
   owner's voice is an Instant Voice Clone, voice uses ElevenLabs' own managed LLM
   (`ELEVENLABS_LLM`) instead — a real platform constraint discovered live, not a preference change.
   ElevenLabs still natively orchestrates STT/TTS/turn-taking either way; only the LLM call's
   destination differs from what was originally planned.
3. **Where voice lives.** Both a dedicated `/voice` page and an inline launcher on the main chat
   page, sharing one underlying voice module so there's a single implementation to maintain.
4. **Voice cloning.** Already completed by the owner directly in ElevenLabs; out of scope for this
   spec beyond referencing the resulting `ELEVENLABS_VOICE_ID`.
5. **Conversation identity.** A voice session shares the *same* `conversation_id` (and "Keep chat"
   behavior) as text chat on the same browser, so a visitor's spoken and typed turns land in one
   unified admin thread rather than being split across separate conversations.
6. **Why tool webhooks use `dynamicVariables` instead of a mapping lookup.** The first draft of this
   spec assumed we'd need to look up our `conversation_id` from ElevenLabs' own id on every tool
   call, and flagged "dynamic variables" as an unverified maybe-simplification. During
   implementation, `@elevenlabs/client`'s own TypeScript definitions confirmed `startSession()`
   really does accept a `dynamicVariables` map, and the agent's tool config can interpolate a
   variable from it into the webhook body. So `faq_tool`/`push_tool` get our `conversation_id`
   directly — no lookup, no guessed system-variable name. The `voice_sessions` mapping table is
   still needed, but only for the post-call webhook, which genuinely only knows ElevenLabs' id.

**Resolved against a real ElevenLabs account** (previously flagged here as unverified):
- The agent-config payload shape in `voice.build_agent_config()` — proven out via `sync_voice_agent.py`
  against a real agent, correcting two wrong guesses along the way: the webhook tool schema's
  per-property object can only set ONE of `description`/`dynamic_variable`/etc, not both; and
  Custom LLM's API key isn't inline, it references a workspace "secret" by `secret_id` (moot now
  since voice uses `ELEVENLABS_LLM`, not Custom LLM at all — see **Implementation Decisions**).
- Whether the SDK's `dynamicVariables` mechanism actually works for tool webhooks — confirmed live:
  `faq_tool`/`push_tool` receive our real `conversation_id` correctly.
- Token minting (`mint_conversation_token`) — confirmed live, returns a working LiveKit-backed
  WebRTC credential.

Still open (not blocking the code, which degrades to a clear 503/502 until voice is configured or an
ElevenLabs call fails — see **Setup and Validation**):
- Exact retry/timeout behavior of ElevenLabs' server-tool webhooks (undocumented as of this
  writing) — affects how forgiving `POST /api/voice/tools/*` needs to be, and whether `push_tool`
  could be invoked more than once for one flagged situation.
- The exact request/response envelope `POST /api/voice/webhook` receives (event `type`, the
  transcript turn shape) is built from ElevenLabs' documented post-call webhook format, but hasn't
  been checked against a real payload yet — `main.py`'s handler reads turn text defensively
  (`message`/`text`/`content`, whichever key is present) for exactly this reason; confirm against a
  live test call and simplify once confirmed.
- No API endpoint was found for registering the post-call webhook itself (only for reading current
  settings, `GET /v1/convai/settings`) — it's a workspace-level setting, registered manually in the
  ElevenLabs dashboard for now. Worth a closer look later if this needs to be scripted (e.g. for a
  fresh owner's setup).
- Confirm current published latency/pricing figures directly against ElevenLabs' pricing page at
  build time rather than any figure quoted secondhand while researching this spec.
