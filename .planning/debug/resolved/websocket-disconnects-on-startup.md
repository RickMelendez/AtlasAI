---
status: resolved
trigger: "WebSocket connection drops ~2 seconds after connecting, printing 'Disconnected in main loop' and shutting down all loops"
created: 2026-03-18T00:00:00.000Z
updated: 2026-03-18T00:01:00.000Z
---

## Current Focus

hypothesis: React 18 StrictMode double-mount causes useWebSocket cleanup to call wsService.disconnect() immediately after connecting, which closes the WebSocket from the frontend and triggers "Disconnected in main loop" on the backend
test: Confirmed by reading main.tsx (React.StrictMode wraps App) and useWebSocket.ts (cleanup calls wsService.disconnect() on unmount)
expecting: Removing the wsService.disconnect() call from the useWebSocket cleanup will keep the connection alive through the StrictMode double-mount cycle
next_action: Fix useWebSocket.ts cleanup — do NOT call wsService.disconnect() on unmount since wsService is a singleton that outlives any single component mount

## Symptoms

expected: WebSocket stays connected indefinitely
actual: WebSocket connects, loops start, then "Disconnected in main loop" appears ~2s later, connection closes, all loops stop
errors: |
  - WebSocket /api/ws accepted
  - connection open
  - Continuous loops started
  - WebSocket endpoint active for session: 1b3c1ca0-...
  - Wake word loop started
  - PorcupineAdapter initialized (pvporcupine unknown version)
  - WARNING: No .ppn model found in backend/models/ — falling back to built-in keyword 'computer'
  - Porcupine listening for: ['computer']
  - Porcupine wake word detection active
  - Screen monitor loop started
  - **Disconnected in main loop**  <- CRASH HERE
  - Porcupine stopped listening
  - Wake word loop stopped
  - connection closed
reproduction: Run .\dev.bat, watch backend CMD window
started: Every startup, consistent ~2s after connect

## Eliminated

- hypothesis: Screen monitor loop crashes immediately (missing Tesseract / screenshot API error)
  evidence: screen_monitor_loop is trivially simple — it just logs and sleeps, no calls to Tesseract or screenshot API. The loop itself cannot crash.
  timestamp: 2026-03-18T00:00:30.000Z

- hypothesis: Porcupine adapter throws and propagates up
  evidence: Porcupine errors are caught and only logged as warnings inside wake_word_loop. Any porcupine exception is caught at line 196 of manager.py and does NOT propagate to kill the WebSocket.
  timestamp: 2026-03-18T00:00:40.000Z

- hypothesis: Backend exception kills connection
  evidence: "Disconnected in main loop" is printed from the WebSocketDisconnect exception handler in wake_word_loop (manager.py line 267-269). WebSocketDisconnect is only raised by FastAPI when the *client* closes the connection — meaning the frontend initiated the close.
  timestamp: 2026-03-18T00:00:50.000Z

## Evidence

- timestamp: 2026-03-18T00:00:20.000Z
  checked: manager.py wake_word_loop (line 267-269)
  found: '"Disconnected in main loop" is printed when WebSocketDisconnect is caught. WebSocketDisconnect is a FastAPI exception raised when the client closes the connection.'
  implication: The frontend is closing the WebSocket, not the backend crashing.

- timestamp: 2026-03-18T00:00:35.000Z
  checked: frontend/src/renderer/hooks/useWebSocket.ts (line 119-124)
  found: 'The useEffect cleanup function calls wsService.disconnect() on unmount. wsService is a module-level singleton.'
  implication: If the component unmounts, the entire WebSocket singleton is disconnected.

- timestamp: 2026-03-18T00:00:45.000Z
  checked: frontend/src/renderer/main.tsx (line 29-61)
  found: 'App is wrapped in React.StrictMode. In React 18 development mode, StrictMode intentionally mounts, unmounts, then remounts every component to detect side effects.'
  implication: The App component (which uses useWebSocket) is unmounted by StrictMode ~1-2s after initial mount, triggering the cleanup which calls wsService.disconnect(), sending a close frame to the backend.

- timestamp: 2026-03-18T00:00:55.000Z
  checked: frontend/src/renderer/hooks/useWebSocket.ts (line 110-125)
  found: 'The useEffect also registers handlers for "connected"/"disconnected" on wsService and calls wsService.connect(). Because wsService is a singleton, the connect() call on remount works — but only after the disconnect from the first mount's cleanup fires.'
  implication: The connection lifecycle is: mount → connect → (StrictMode unmount) → disconnect → remount → reconnect. The disconnect is the ~2s gap in the logs. After remount, auto-reconnect fires 3s later per scheduleReconnect(). This means the orb "disappears" for a window because the loops stopped.

## Resolution

root_cause: |
  React 18 StrictMode mounts App, then immediately unmounts it (intentional StrictMode behavior for detecting side effects), then remounts. The useWebSocket hook's useEffect cleanup calls wsService.disconnect() on unmount. Since wsService is a module-level singleton shared across all mounts, this disconnect call sends a WebSocket close frame to the backend exactly during the StrictMode remount cycle (~1-2s after startup). The backend's wake_word_loop catches WebSocketDisconnect and prints "Disconnected in main loop", then stops all loops.

fix: |
  Remove wsService.disconnect() from the useWebSocket hook's useEffect cleanup.
  The singleton wsService should NOT be managed by individual component mount/unmount cycles.
  The singleton lives for the entire app lifetime and should only be explicitly disconnected via the disconnect() function returned from the hook when the user intentionally wants to disconnect.

  Additionally, make wsService.isIntentionalClose reset to false on reconnect so that after the StrictMode cycle the auto-reconnect path still works. (It currently resets reconnectAttempts in onopen but isIntentionalClose was set to true by disconnect() and will suppress future auto-reconnects if it stays true.)

verification: |
  Fix verified by code inspection:
  1. useWebSocket.ts cleanup no longer calls wsService.disconnect() — StrictMode unmount cycle cannot kill the singleton connection.
  2. wsService.connect() now resets isIntentionalClose = false — explicit disconnect() followed by reconnect() works correctly.
  3. The backend "Disconnected in main loop" can no longer be triggered by StrictMode remounting because the frontend no longer sends a WebSocket close frame during the unmount cycle.
files_changed:
  - frontend/src/renderer/hooks/useWebSocket.ts
  - frontend/src/renderer/services/websocket.ts
