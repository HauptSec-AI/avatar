# Avatar — Test Plans

Three layers, per SPEC-AVATAR.md "Testing": backend unit tests, Playwright frontend tests, and a Docker
end-to-end pass. All three ran against real infrastructure (Supabase, OpenRouter with the cheap
`openai/gpt-5.4-nano` model, and Pushover) — nothing here is mocked at the infra level except where
noted. Test conversations and screenshots are deleted after a full pass (see "Cleanup" below).

## 1. Backend unit tests (`backend/tests/`)

Run: `cd backend && uv run pytest -v`

- [x] `test_supabase_connection.py` — env present, `messages` table reachable, insert/read/delete
      round-trip with the expected columns (pre-existing, required by SPEC "Setup and Validation").
- [x] `test_config.py` — `/api/config` returns `owner_name` with no DB hit; `/api/conversation/{id}`
      validates the id and returns an empty list for an unseen conversation.
- [x] `test_admin_auth.py` — login success/failure, logout, and the critical security property:
      every `/admin/*` route returns 401 with no/garbage session cookie and succeeds with a valid one.
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

**Result:** 35 tests, 2 LLM-marked, all passing (`35 passed`).

## 2. Playwright frontend tests (`test/e2e/`)

Run: `cd test && npx playwright test` (desktop = 1440×900 Chromium, mobile = Pixel 7 emulation).
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

**Result:** 36 tests (18 × 2 viewports), 1 skipped by design (desktop project skips the
mobile-only master/detail test), all others passing.

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
- [x] `./scripts/stop_mac.sh` — container stopped and removed after the Docker e2e pass.
