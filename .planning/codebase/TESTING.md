# TESTING.md — Atlas AI Testing State

## Summary

Testing is minimal — approximately **15% complete** (per STATUS.md). The test suite is largely a scaffold. Most verification is manual or via the integration script.

---

## Backend Testing

### Framework
- **pytest** (configured, empty suite)
- **pytest-cov** — coverage reporting (not yet used)

### Test Structure
```
backend/tests/
└── __init__.py    (empty scaffold — no test files yet)
```

### Integration Script
`backend/test_claude.py` — manual integration test, not part of pytest.

Run:
```bash
cd backend
venv\Scripts\activate
python test_claude.py
```
Requires real `ANTHROPIC_API_KEY` in `.env`. Tests end-to-end Claude response.

### Mock Mode
For offline testing without API keys:
```bash
ANTHROPIC_MOCK=1 pytest
```
`ClaudeAdapter` substitutes a full in-process mock when `ANTHROPIC_MOCK=1` or `api_key='mock'`.

Mock behavior:
- Detects "analiz"/"error_analysis" in system → returns JSON error analysis
- Detects "proactiv"/"proactive" in system → returns suggestion text
- Default → returns `"[MOCK] Reply to: {last_user_message}"`

### What Needs Tests

| Area | Priority | Notes |
|---|---|---|
| `AssistantState` entity | 🔴 High | State transitions, edge cases |
| `ProcessChatMessageUseCase` | 🔴 High | Mock AIService, verify output |
| `ProcessVoiceCommandUseCase` | 🔴 High | Mock all services |
| `ClaudeAdapter` | 🟡 Med | Use mock mode, test tool use loop |
| `ToolExecutor` | 🟡 Med | Test dangerous command blocking |
| `WebSocketManager` | 🟡 Med | Fast router, language detection |
| `EventBus` | 🟢 Low | Simple pub/sub, easy to test |

---

## Frontend Testing

No test framework configured. No test files exist.

Potential stack (not yet added): `vitest` + `@testing-library/react`

---

## What Has Been Manually Verified

Per STATUS.md:
- ✅ Backend starts without errors
- ✅ `/health` endpoint responds
- ✅ Orb animation at 60 FPS
- ✅ System tray icon working
- ✅ State machine transitions correct
- ✅ WebSocket endpoint listening

Pending manual tests:
- ⏳ WebSocket connection from frontend
- ⏳ Voice recording + Whisper transcription
- ⏳ Screen capture pipeline
- ⏳ Full conversation flow end-to-end
- ⏳ Wake word detection (Porcupine key needed)

---

## Running Tests

```bash
cd backend
venv\Scripts\activate

# Run suite (currently empty)
pytest

# With coverage
pytest --cov=src tests/

# Code quality
black .
isort .
mypy src/
```

---

## Notes

- No mocking of database — the project uses real SQLite (aiosqlite). If tests were written, they should use a temp DB (`:memory:` or temp file) not mocks.
- Whisper/ElevenLabs/Claude adapters have no test doubles other than the `ANTHROPIC_MOCK` pattern. Consider extracting similar mock patterns for other adapters.
- The `loops/` directory in infrastructure is an empty scaffold — note that loop logic lives in `manager.py`, not in separate loop files.
