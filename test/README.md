# Avatar — Test Plans

Three layers, per SPEC-AVATAR.md "Testing": backend unit tests, Playwright frontend tests, and a Docker
end-to-end pass. All three ran against real infrastructure (Supabase, OpenRouter with the cheap
`openai/gpt-5.4-nano` model, and Pushover) — nothing here is mocked at the infra level except where
noted. Test conversations and screenshots are deleted after a full pass (see "Cleanup" below).

A fourth, lighter layer (1b, below) covers frontend logic in isolation with Vitest + jsdom — added once
enough browser-API-touching modules (`markdown.ts`, `cookies.ts`, `theme.ts`) existed with no unit-test
harness at all, previously testable only indirectly through the full Playwright layer.

Voice (SPEC-VOICE.md) is covered inline in each layer below rather than as a separate file, following
SPEC-AVATAR.md's single test-plan convention: `test_voice.py` in layer 1, `e2e/voice.spec.ts` in layer 2,
and a dedicated voice checklist in layer 3. Per SPEC-VOICE.md's own testing section, real ElevenLabs
STT/TTS/WebRTC round trips are billed per call-minute, so the routine suite (layers 1-2) never drives a
full successful connection — it exercises the free error/UI paths (mic-permission-denied, rate limiting,
mocked webhook payloads) instead, and reserves a real live call for a sparing, deliberate Docker
end-to-end pass (not yet run — see layer 3 below).

## 1. Backend unit tests (`backend/tests/`)

Run: `cd backend && uv run pytest -v`

- [x] `test_supabase_connection.py` — env present, `messages` table reachable, insert/read/delete
      round-trip with the expected columns (pre-existing, required by SPEC "Setup and Validation").
- [x] `test_config.py` — `/api/config` returns `owner_name` with no DB hit; `/api/conversation/{id}`
      validates the id and returns an empty list for an unseen conversation.
- [x] `test_admin_auth.py` — login success/failure, logout, and the critical security property:
      every `/admin/*` route returns 401 with no/garbage session cookie and succeeds with a valid one.
      Also: `/admin/login` is rate-limited (10/minute per client IP, 429 on the 11th call) and locks
      out after 5 wrong-password attempts (429 on the 6th, even with the correct password) until the
      window rolls off; a successful login resets the failure count so it doesn't carry into later
      attempts.
- [x] `test_voice.py` — SPEC-VOICE.md coverage: webhook HMAC signature verification (valid, wrong
      secret, stale timestamp, missing/malformed header, no secret configured), the ElevenLabs
      agent-config payload shape, `/api/voice/session` (invalid id, 503 when unconfigured, 5/minute
      rate limit, token minted when configured, 502 on an ElevenLabs API failure), the `faq_tool`/
      `push_tool` webhooks (shared-secret auth, identical answers to the text `faq_tool` for the same
      FAQ number, Pushover call + `needs_attention`), and `/api/voice/webhook` (signature rejection,
      non-transcript events skipped, idempotent on a redelivered/unknown claim, transcript rows
      inserted with `channel="voice"` and the last avatar turn flagged `needs_attention`). Three
      tests are `@pytest.mark.voice_live` (need the real `channel`/`voice_sessions` migration
      applied — see SPEC-VOICE.md "Setup and Validation"): the session-mapping round trip, claim
      idempotency against the real table, and a full webhook-to-Supabase persistence check.
- [x] `test_admin_conversations.py` — inbox listing; opening a conversation marks its rows read and
      clears `needs_attention` (verified in the response and via a fresh DB read); posting a human
      message inserts `role=human, read=true`; resolve clears `needs_attention` without a reply.
- [x] `test_chat.py` — `Qn`/`qn` instant-answer shortcuts fire with **no LLM call** (enforced by a
      monkeypatch that fails the test if `Runner.run_streamed` is invoked); unknown `Qn` fallback;
      >20,000-char messages truncated with the exact note appended (byte-checked), and the
      20,000-char boundary is *not* truncated; mocked full agent runs (token streaming, tool-call SSE
      events, `needs_attention` set when `push_tool` fires); invalid `conversation_id` → 400; the
      20/minute rate limit returns 429 on the 21st call *before* any LLM call, isolated per
      conversation_id. 2 tests are `@pytest.mark.llm` (real calls through `openai/gpt-5.4-nano`).

**Result:** 62 tests, 2 `llm`-marked (real calls), 3 `voice_live`-marked (need the Supabase voice
migration applied), all passing: `62 passed` (`pytest -v`, migration already applied on the
reference DB) — run `pytest -v -m "not voice_live"` for a pass that doesn't need it (59 passed).
(Grown since — see individual RECS.md fixes for what's been added; not re-tallied here.)

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
- [x] Abuse guard: a >20,000-char message is truncated server-side with the exact note appended
      (checked via the stored row, not just the UI).

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

**Result:** 75 tests (25 × 3 projects), 1 skipped by design (the mobile-only master/detail test
skips itself on the `desktop` project via `test.skip`), all others passing.

## 3. Docker end-to-end (single container)

Run: `./scripts/start_mac.sh` (builds the multi-stage image, runs it on `:8000`), then
`./scripts/stop_mac.sh` to tear down.

**Status: passed.** (First attempt hit a transient Docker Desktop VM networking stall right after a
fresh restart — `docker pull` hung with zero progress on every image. Confirmed host networking was
fine and it was Docker-VM-specific; a `docker pull hello-world` retry later succeeded once the VM
had settled, and the real build/run/test pass below went through cleanly on the same machine.)

- [x] Image builds cleanly (Vite frontend stage + FastAPI/uv backend stage) — multi-stage build via
      `./scripts/start_mac.sh`, ~2 min including `npm install` and `uv sync`.
- [x] Container starts; `GET /api/config` returns `{"owner_name":"Alex Haupt"}`, 200, no DB hit.
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
- [x] `/`, `/admin`, `/api/config`, `/tokens.css`, `/icons.svg`, `/assets/*.png`, JS/CSS bundles —
      all `200`.
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
