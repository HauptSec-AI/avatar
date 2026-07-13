# Avatar — Test Plans

Three layers, per SPEC-AVATAR.md "Testing": backend unit tests, Playwright frontend tests, and a Docker
end-to-end pass. All three ran against real infrastructure (Supabase, OpenRouter with the cheap
`openai/gpt-5.4-nano` model, and Pushover) — nothing here is mocked at the infra level except where
noted. Test conversations and screenshots are deleted after a full pass (see "Cleanup" below).

A fourth, lighter layer (1b, below) covers frontend logic in isolation with Vitest + jsdom — added once
enough browser-API-touching modules (`markdown.ts`, `cookies.ts`, `theme.ts`) existed with no unit-test
harness at all, previously testable only indirectly through the full Playwright layer. So: four layers
in total now, though the numbering below (1, 1b, 2, 3) keeps SPEC-AVATAR.md's original three-layer
framing intact rather than renumbering everything.

Voice (SPEC-VOICE.md) is covered inline in each layer below rather than as a separate file, following
SPEC-AVATAR.md's single test-plan convention: `test_voice.py` (plus `test_elevenlabs_connection.py`) in
layer 1, `e2e/voice.spec.ts` in layer 2, and a dedicated voice checklist in layer 3. Per SPEC-VOICE.md's
own testing section, real ElevenLabs STT/TTS/WebRTC round trips are billed per call-minute, so the
routine suite (layers 1-2) never drives a full successful connection — it exercises the free error/UI
paths (mic-permission-denied, rate limiting, mocked webhook payloads) instead, and reserves a real live
call for a sparing, deliberate Docker end-to-end pass (not yet run — see layer 3 below).

Two pytest markers gate tests that need more than the base `.env` setup — both run by default in
`pytest -v` (no addopts filter excludes them), so a fresh clone missing either prerequisite should
explicitly pass `-m "not voice_live and not elevenlabs_live"`:
- `voice_live` — needs the `channel`/`voice_sessions` Supabase migration applied.
- `elevenlabs_live` — needs real `ELEVENLABS_API_KEY`/`ELEVENLABS_AGENT_ID` configured; hits the real
  ElevenLabs API (credential validation only, not a billed call).

## 1. Backend unit tests (`backend/tests/`)

Run: `cd backend && uv run pytest -v` (add `-m "not voice_live and not elevenlabs_live"` on a fresh
clone that hasn't run the voice migration / configured ElevenLabs yet).

- [x] `test_supabase_connection.py` — env present, `messages` table reachable, insert/read/delete
      round-trip with the expected columns (pre-existing, required by SPEC "Setup and Validation").
- [x] `test_config.py` — `/api/config` returns `owner_name` with no DB hit; `/api/health` returns
      `{"ok": true}` when Supabase is reachable and 503 when it isn't (the actual Fly health-check
      target — `/api/config` alone can't catch a DB outage); `_derive_secret()` (the helper behind
      `SESSION_SECRET`'s and `ELEVENLABS_TOOL_SECRET`'s silent-fallback warnings) returns the
      explicit value with no warning, or falls back and warns; `/api/conversation/{id}` validates
      the id and returns an empty list for an unseen conversation.
- [x] `test_admin_auth.py` — login success/failure, logout, and the critical security property:
      every `/admin/*` route returns 401 with no/garbage session cookie and succeeds with a valid one.
      Also: `/admin/login` is rate-limited (10/minute per client IP, 429 on the 11th call) and locks
      out after 5 wrong-password attempts (429 on the 6th, even with the correct password) until the
      window rolls off; a successful login resets the failure count so it doesn't carry into later
      attempts.
- [x] `test_admin_conversations.py` — inbox listing (including `scan_truncated`, mocking the Supabase
      client directly to trigger the `INBOX_SCAN_LIMIT` boundary cheaply); opening a conversation
      marks its rows read and clears `needs_attention` (verified in the response and via a fresh DB
      read, and that the old `GET` now 405s); posting a human message inserts `role=human, read=true`;
      resolve clears `needs_attention` without a reply.
- [x] `test_agent_runner.py` — `send_pushover_notification`'s not-configured path, the happy path, and
      the coarse **global** (not per-conversation) rate limit that stops a script minting fresh
      conversation ids from flooding Pushover past the per-conversation chat limit.
- [x] `test_transcript.py` — `build_transcript`'s three-way role labeling, and the prompt-injection
      defense: a visitor message with an embedded newline followed by `[` can't forge a fake
      `[Owner (the human, joined live)]: ...` line once flattened, while ordinary mid-sentence
      brackets are left alone.
- [x] `test_chat.py` — `Qn`/`qn` instant-answer shortcuts fire with **no LLM call** (enforced by a
      monkeypatch that fails the test if `Runner.run_streamed` is invoked); unknown `Qn` fallback;
      >20,000-char messages truncated with the exact note appended (byte-checked), the 20,000-char
      boundary is *not* truncated, and the schema rejects a body past `MAX_MESSAGE_BODY_CHARS` (422)
      or `MAX_REQUEST_BODY_BYTES` (413); mocked full agent runs (token streaming, tool-call SSE
      events, `needs_attention` set when `push_tool` fires, and a two-tool turn's "done" events are
      labeled by the SDK's own `call_id` rather than call order); invalid `conversation_id` → 400;
      the 20/minute rate limit returns 429 on the 21st call *before* any LLM call, isolated per
      conversation_id. 2 tests are `@pytest.mark.llm` (real calls through `openai/gpt-5.4-nano`).
- [x] `test_voice.py` — SPEC-VOICE.md coverage: webhook HMAC signature verification (valid, wrong
      secret, stale timestamp, missing/malformed header, no secret configured — and that a failed
      check logs only header names/booleans, never the body or header values); the ElevenLabs
      agent-config payload shape; `/api/voice/session` (invalid id, 503 when unconfigured, 5/minute
      rate limit, token minted when configured, 502 on an ElevenLabs API failure); `/api/voice/session/started`
      (requires a valid, conversation-scoped `session_nonce` — rejects a missing one, a garbage one,
      and one minted for a *different* conversation_id; 10/minute rate limit); the `faq_tool`/
      `push_tool` webhooks (a dedicated `ELEVENLABS_TOOL_SECRET` bearer auth, independent of the
      webhook's HMAC key; identical answers to the text `faq_tool` for the same FAQ number; Pushover
      call + `needs_attention` flagged live on the most recent existing row, not just at call-end);
      and `/api/voice/webhook` (signature rejection, missing-`conversation_id` 400, non-transcript
      events skipped, idempotent on a redelivered/unknown claim, 30/minute rate limit, transcript rows
      inserted with `channel="voice"` and the last avatar turn flagged `needs_attention`, and — the
      key correctness property — a mid-loop insert failure releases the claim and a redelivery
      completes only the missing rows instead of duplicating or permanently losing anything). 4
      tests are `@pytest.mark.voice_live` (need the real `channel`/`voice_sessions` migration
      applied): the session-mapping round trip, claim idempotency, a full webhook-to-Supabase
      persistence check, and the partial-failure-then-retry recovery against the *real* tables.
- [x] `test_elevenlabs_connection.py` — mirrors `test_supabase_connection.py`'s role for ElevenLabs
      (SPEC-VOICE.md "Setup and Validation" step 6): confirms `ELEVENLABS_API_KEY` is valid,
      `ELEVENLABS_AGENT_ID` resolves, and a connection credential mints end-to-end (one successful
      mint call proves all three at once). Both tests `@pytest.mark.elevenlabs_live`.

**Result:** 95 tests — 2 `llm`-marked (real calls), 4 `voice_live`-marked, 2 `elevenlabs_live`-marked,
87 with none of those markers — all passing: `95 passed` (`pytest -v`, voice migration applied and
ElevenLabs configured on the reference setup).

## 1b. Frontend unit tests (`frontend/src/*.test.ts`)

Run: `cd frontend && npm run test:unit`

Vitest + jsdom, for the browser-API-touching logic that doesn't need a real browser
(`markdown.ts`, `cookies.ts`, `theme.ts`) — distinct from the Playwright e2e layer below, which
drives the actual app in a real browser. `vitest.config.ts` sets `--localstorage-file` via
`NODE_OPTIONS` since Node 22+ gates `localStorage` behind that flag and jsdom no longer polyfills
it itself.

- [x] `markdown.test.ts` — `escapeHtml` escapes all five HTML-significant characters;
      `renderMarkdown`'s paragraph/line-break splitting, `**bold**` and `[label](url)` conversion
      (http/https/mailto only — unsafe schemes like `javascript:` are never linkified), and that
      HTML is escaped *before* markdown is applied (a visitor message can't inject markup).
- [x] `cookies.test.ts` — `getCookie`/`setCookie`/`deleteCookie` round-trip; a missing cookie
      returns `null`; values with special characters survive URL-encoding; distinct cookie names
      don't collide.
- [x] `theme.test.ts` — `currentTheme()` defaults to dark and only reports light for the exact
      string `"light"`; `setupThemeToggle()` toggles `data-theme` and persists to `localStorage`
      on click, swaps the moon/sun icon, and doesn't throw if the button id isn't found.

**Result:** 22 tests, all passing.

## 2. Playwright frontend tests (`test/e2e/`)

Run: `cd test && npx playwright test` across three projects — `desktop` (1440×900 Chromium),
`mobile-chrome` (Pixel 7 emulation), and `mobile-safari` (real WebKit via iPhone 14 emulation, added
because Safari doesn't honor styles defined inside an externally-referenced SVG pulled in via
`<use>`, which Chrome's mobile emulation alone wouldn't catch).
Screenshots land in `test/screenshots/` (deleted after review — see "Cleanup").

### Visitor chat (`e2e/visitor.spec.ts`)

- [x] Intro state: composer auto-focused, 3 suggestion chips, dark is default; theme toggle to
      light and back; screenshotted in both themes × both viewports.
- [x] `Qn` instant-answer shortcut: no LLM call, tagged `instant · Q2`, visitor bubble renders.
- [x] Deep link `?q=N`: opens, auto-submits, answer tagged, query param cleared from the URL.
- [x] Suggestion chip click submits immediately.
- [x] Normal message: real streamed LLM reply renders, composer re-enables and **re-focuses** on
      completion (hard SPEC requirement).
- [x] Keep chat (default on): reload restores the conversation from the `avatar_conversation_id`
      cookie.
- [x] Reset: clears the visible thread, issues a fresh conversation id; survives reload.
- [x] Keep chat off: conversation does **not** persist across reload.
- [x] Rate limit: 21st message in a minute (all `Qn`, no LLM cost) shows the friendly slow-down
      banner.
- [x] Dropped connection mid-stream: a `fetch` stub whose body stream errors immediately shows a
      "lost connection" banner and leaves the composer usable, instead of disabling it forever.
- [x] Resetting mid-stream: a gated/delayed `/api/chat` response released *after* Reset is clicked
      never renders — the stale reply's tokens don't leak into the freshly-cleared conversation.
- [x] Abuse guard: a >20,000-char message is truncated server-side with the exact note appended
      (checked via the stored row, not just the UI).
- [x] Poll slowdown: `pollIntervalMs` (pure logic, imported directly — no need for a real 5-minute
      wait) is fast at/before the 5-minute idle boundary and slow just past it.

### Admin dashboard (`e2e/admin.spec.ts`)

- [x] Login gate: wrong password shows an error and keeps the gate; correct password enters.
- [x] Dark/light theme on the dashboard.
- [x] `needs_attention` (from a real contact-capture flow — 2 real LLM turns ending in `push_tool`,
      which also sends a live Pushover notification): shows in the inbox, thread opens, flag clears.
- [x] Admin reply → visitor sees it as the "live" human bubble via polling (two real browser
      contexts, one visitor + one admin, cross-verified within the 10s poll window).
- [x] Mobile master/detail: selecting a conversation opens the full thread and shows a back
      control; back returns to the inbox (mobile viewport only).
- [x] Keyboard `↑`/`↓` moves the active-conversation selection.
- [x] "Mark resolved" clears `needs_attention` without replying — proven by re-triggering the flag
      via a direct API call after the thread is already open, then resolving without reopening.
- [x] Poll doesn't silently re-clear `needs_attention`: opening a thread clears the flag (expected),
      re-triggering it via a real 2nd contact-capture flow while the thread stays open survives a
      real 10s poll cycle instead of the next poll tick clearing it again.
- [x] Switching admin threads mid-fetch doesn't leak the stale thread's rows into the new one: a
      gated/delayed fetch for conversation A, switched away from before it resolves, never gets
      applied once released. Desktop only — mobile's master/detail layout hides the inbox once a
      thread is open, so clicking a second `.convo-item` isn't the same interaction there.
- [x] Inbox shows a "may be more" banner when the scan was truncated (mocked `scan_truncated`
      response, since seeding 3000+ real rows to trigger it for real isn't practical).
- [x] Logout returns to the login gate.

### Voice (`e2e/voice.spec.ts`)

- [x] `/voice` hero renders (heading, start-call button, keep-chat switch, name field, reset),
      dark-default, theme toggle to light; screenshotted in both themes.
- [x] Starting a call with no mic permission granted shows a dismissible, non-alarming banner (the
      real free error path — a genuine `POST /api/voice/session` token mint, then a real failed
      WebRTC handshake since Playwright's default context has no mic access); "Back to chat" returns
      to the hero.
- [x] Reset tears down an active call and issues a fresh `conversation_id` cookie.
- [x] Inline "Talk live" launcher on the main chat page swaps the composer for the voice panel and
      back; composer re-focuses on return.
- [x] Voice session minting is rate-limited at 5/minute per `conversation_id` (429 on the 6th call).
- [x] `/api/voice/session` rejects an invalid `conversation_id` (400).
- [x] Admin: a `channel="voice"` message renders the mic-icon channel badge (mocked admin API
      responses, no backend hit).
- [x] Session-duration cap: `scheduleSessionCap`/`clearSessionCap` (pure timer logic, imported
      directly — `onConnect`, which schedules the real cap, only ever fires on a genuine WebRTC
      connection this suite deliberately never drives) actually fire and actually cancel.

**Result:** 99 tests (33 × 3 projects), 9 skipped by design — the mobile-only master/detail test
skips on `desktop`; the desktop-only switching-threads-mid-fetch test skips on both mobile projects
(master/detail hides the inbox list there); the three pure-logic tests (session-cap × 2, poll
slowdown) skip on both mobile projects since they don't need to run per browser engine — all others
passing (90 passed, 0 failed).

## 3. Docker end-to-end (single container)

Run: `./scripts/start_mac.sh` (builds the multi-stage image, runs it on `:8000`), then
`./scripts/stop_mac.sh` to tear down.

**Status: passed.** (First attempt hit a transient Docker Desktop VM networking stall right after a
fresh restart — `docker pull` hung with zero progress on every image. Confirmed host networking was
fine and it was Docker-VM-specific; a `docker pull hello-world` retry later succeeded once the VM
had settled, and the real build/run/test pass below went through cleanly on the same machine.)

- [x] Image builds cleanly (Vite frontend stage + FastAPI/uv backend stage) — multi-stage build via
      `./scripts/start_mac.sh`, ~2 min including `npm install` and `uv sync`.
- [x] Container starts; `GET /api/config` returns `{"owner_name":"Alex Haupt"}`, 200, no DB hit;
      `GET /api/health` returns `{"ok":true}` (the actual Fly health-check target — touches Supabase
      for real). Re-verified in a later pass after the Dockerfile added a non-root `USER`:
      `docker exec avatar whoami` → `appuser` (uid 1000, not root), and a real `Q1` chat round-trip
      persisted to Supabase correctly with the container running unprivileged.
- [x] `/` and `/admin` both 200; static assets `tokens.css`, `components.css`, `icons.svg`,
      `/assets/avatar-human.png`, `/assets/avatar-robot.png`, `/assets/avatar-robot-round.png`,
      all bundled JS/CSS — all 200 (also confirms the `avatar-human.PNG`→`.png` case-sensitivity
      fix actually mattered: this is the first test against a case-sensitive Linux filesystem).
- [x] Full visitor flow against the container: `Qn` instant answer (no LLM), a real streamed LLM
      reply to a normal question — both verified via direct SSE parsing of `/api/chat`.
- [x] Full admin flow against the container: wrong password → 401; no-cookie guard on
      `/admin/conversations` → 401; correct login → session cookie; inbox listing; opening a thread
      (marks read); posting a human reply (`role=human`); mark resolved; logout; guard re-applies
      post-logout (401 again).
- [x] Three-way flow end-to-end inside the container: contact-capture conversation (2 real LLM
      turns) → `push_tool` fires (visible as SSE `tool` events, real Pushover notification sent) →
      stored avatar row has `needs_attention: true` → admin sees it in the inbox → admin posts a
      reply → `GET /api/conversation/{id}` (the visitor's own polling endpoint) shows the human
      row appended, tagged appropriately.
- [x] `docker logs avatar` — clean throughout: every request logged at the expected status (200s,
      plus the two *intentional* 401s from the auth-guard checks above), no tracebacks, no errors.
- [x] Visual spot-check via Playwright against the running container — visitor page renders
      correctly (new digital-twin avatar included).

### Voice (SPEC-VOICE.md) — not yet run against the container

- [ ] A genuinely live voice smoke test: visitor speaks (pre-recorded audio ElevenLabs actually
      transcribes), twin answers in the owner's cloned voice, a contact-capture flow triggers
      `push_tool` mid-call with a real Pushover notification, the call ends, and the admin dashboard
      shows the complete transcript in the same thread as any prior text messages with the mic
      channel badge — per SPEC-VOICE.md "Success Criteria". Deliberately not run as part of this
      pass (bills real ElevenLabs call-minutes; SPEC-VOICE.md's own testing section reserves this
      for a sparing, deliberate run, not the routine suite) — layers 1-2 above already cover the
      webhook/tool/UI logic without a live call. Run this manually once against a container with
      `ELEVENLABS_*` configured before relying on voice in production; see also the separate,
      lower-priority finding in `RECS.md` about adding voice checks to `DEPLOY.md`'s smoke checklist.

### Local end-to-end smoke test (ran in place of Docker, same code path minus containerization)

- [x] `cd backend && uv run uvicorn app.main:app --port 8000 --app-dir .` serving the Vite-built
      `frontend/dist` (same static-serving code path `main.py` uses in the container).
- [x] `/`, `/admin`, `/api/config`, `/api/health`, `/tokens.css`, `/icons.svg`, `/assets/*.png`,
      JS/CSS bundles — all `200`.
- [x] Full visitor + admin + three-way flows verified via the Playwright suite above, against this
      server.

## Cleanup (after a full pass)

- [x] Deleted `test/screenshots/*` (captured for review during this build; not committed).
- [x] Deleted all test conversation threads from Supabase — 804 rows the first pass, plus smaller
      batches after each later verification round (backend test reruns, avatar-asset visual
      checks, the Docker e2e pass) — every row was test data; the table has no real visitor
      traffic yet.
- [x] Deleted the corresponding `voice_sessions` mapping rows alongside their `messages` rows, per
      SPEC-VOICE.md's cleanup instruction (no real audio was recorded — the live voice smoke test
      above hasn't been run yet, so there's no test audio to delete).
- [x] `./scripts/stop_mac.sh` — container stopped and removed after the Docker e2e pass.
