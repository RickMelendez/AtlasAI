@echo off
:: Atlas AI - One-click dev environment
:: Opens two terminal windows: backend (auto-reload) + frontend (HMR)
:: Just double-click this file, or run it from the terminal.

echo Starting Atlas AI dev environment...

:: ── Backend ─────────────────────────────────────────────────────────────────
:: Activates the venv and runs uvicorn with --reload.
:: Any .py file change → uvicorn auto-restarts in ~1s, no manual kill needed.
start "Atlas Backend" cmd /k "cd /d %~dp0backend && call venv\Scripts\activate && python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8001"

:: Give the backend a moment to bind the port first
timeout /t 2 /nobreak >nul

:: ── Frontend ─────────────────────────────────────────────────────────────────
:: Vite dev server with Hot Module Replacement (HMR).
:: Any .tsx/.ts/.css change → updates in the browser instantly, no restart needed.
start "Atlas Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo Both services started in separate windows.
echo   Backend:  http://localhost:8001   (auto-reloads on .py changes)
echo   Frontend: http://localhost:5173   (hot-reloads on .tsx/.css changes)
echo.
echo To stop: just close both windows.
