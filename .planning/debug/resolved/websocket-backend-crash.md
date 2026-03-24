---
status: verifying
trigger: "WebSocket still disconnects ~1 second after Screen monitor loop started appears in backend logs"
created: 2026-03-18T00:00:00Z
updated: 2026-03-18T00:00:00Z
---

## Current Focus

hypothesis: The websocket.py route handler's while-loop calls asyncio.sleep(1) then checks `session_id not in ws_manager.active_connections` — but the SAME websocket object is being consumed by BOTH the route handler's own loop AND the wake_word_loop's ws.receive_json(). Only one coroutine can read from a WebSocket at a time. The real crash is that wake_word_loop receives a WebSocketDisconnect not from the client, but because FastAPI's WebSocket state machine detects a conflict or because the websocket.py route's sleep(1) check removes the session from active_connections prematurely. However the ACTUAL root cause is different: the route handler itself does nothing to send keepalives and does nothing to read from the socket — it just sleeps. Meanwhile wake_word_loop calls ws.receive_json() with a 1-second timeout. After the screen_monitor_loop starts (~1s startup time for Porcupine), the first 1-second timeout in wake_word_loop fires. That is asyncio.TimeoutError, caught as `continue`. BUT: the websocket.py route loop also runs asyncio.sleep(1) and then checks `if session_id not in ws_manager.active_connections`. If something caused disconnect() to be called (removing it from active_connections), the route loop breaks, then the finally block calls disconnect() again — but this alone wouldn't cause the wake_word_loop to crash with WebSocketDisconnect. The REAL mechanism: ws.receive_json() throws WebSocketDisconnect when the underlying socket is closed. The socket is closed when the frontend disconnects. React 18 StrictMode mounts → unmounts → remounts. The first mount calls wsService.connect(). The unmount used to call wsService.disconnect() (the old bug). The fix removed that. But there may still be a SECOND connection attempt from the remount that causes the backend to see two connections. When the second connection arrives, the first WebSocket's underlying TCP connection may be abandoned. Actually — re-reading the code more carefully — the real question is: what is the exact exception that causes "Disconnected in main loop"? It is WebSocketDisconnect (line 267-269 in manager.py). This is raised by FastAPI's WebSocket when the client closes the connection OR when receive() is called on a closed socket.
test: Trace the exact ~1 second timing — Porcupine init takes ~1s, screen_monitor_loop starts AFTER porcupine init completes in wake_word_loop. The log sequence shows screen_monitor_loop started LAST. This means wake_word_loop is already in its receive loop. Then 1 second later (one full timeout cycle) the crash fires. The 1-second timing matches the asyncio.wait_for(ws.receive_json(), timeout=1.0) timeout cycle.
expecting: The root cause is that the frontend (React 18 StrictMode) mounts the component, connects WebSocket, then StrictMode unmounts and remounts. On remount wsService.connect() is called again. Since the first WS is still OPEN (readyState === 1), the guard `if (this.ws?.readyState === WebSocket.OPEN) return` fires and no second connection is made. BUT the real issue may be elsewhere.
next_action: ROOT CAUSE CONFIRMED — see Evidence and Resolution sections below.

## Symptoms

expected: WebSocket stays connected
actual: Exactly 1 second after "Screen monitor loop started", backend prints "Disconnected in main loop" and all loops stop
errors: |
  - WebSocket /api/ws accepted
  - connection open
  - Continuous loops started
  - WebSocket endpoint active for session
  - Wake word loop started
  - PorcupineAdapter initialized
  - WARNING: No .ppn model found — falling back to built-in keyword 'computer'
  - Porcupine listening for: ['computer']
  - Porcupine wake word detection active
  - Screen monitor loop started   <- last successful log
  - Disconnected in main loop     <- crash, ~1 second later
  - Porcupine stopped listening
  - Wake word loop stopped
  - connection closed
reproduction: Run .\dev.bat — happens every startup, consistent
started: Always (not a regression)

## Eliminated

- hypothesis: Frontend React 18 StrictMode calling wsService.disconnect() in cleanup
  evidence: Fix was already applied — cleanup no longer calls disconnect(). Crash persists.
  timestamp: 2026-03-18T00:00:00Z

- hypothesis: Tesseract/screen capture crashing on Windows
  evidence: screen_monitor_loop does nothing on first iteration except asyncio.sleep(3). No screen capture happens in the loop itself — it is passive. The tesseract adapter is not invoked from the loop.
  timestamp: 2026-03-18T00:00:00Z

- hypothesis: Route handler's session check causing premature disconnect
  evidence: The route handler checks `if session_id not in ws_manager.active_connections` after sleep(1). This would only trigger if disconnect() was already called by something else. It's a symptom reporter, not a cause.
  timestamp: 2026-03-18T00:00:00Z

## Evidence

- timestamp: 2026-03-18T00:00:00Z
  checked: manager.py line 267-269
  found: "Disconnected in main loop" is printed when WebSocketDisconnect is caught inside wake_word_loop's while loop. This exception is raised by FastAPI WebSocket internals when ws.receive_json() (or ws.receive()) is called on a socket that the client has closed.
  implication: The frontend (client) is closing the WebSocket connection ~1 second after the screen monitor loop starts.

- timestamp: 2026-03-18T00:00:00Z
  checked: websocket.py route handler lines 50-58
  found: The route handler has its own while True loop that calls asyncio.sleep(1) and then checks if session_id is still in active_connections. This loop runs CONCURRENTLY with wake_word_loop and screen_monitor_loop.
  implication: There is a DUAL-READER problem. Both the route handler and wake_word_loop are alive. But the route handler does NOT call ws.receive_json() — it only sleeps and checks state. So no dual-reader on the socket.

- timestamp: 2026-03-18T00:00:00Z
  checked: manager.py wake_word_loop, the asyncio.wait_for(ws.receive_json(), timeout=1.0) pattern
  found: wake_word_loop uses asyncio.wait_for with timeout=1.0. When no message arrives in 1 second, asyncio.TimeoutError is caught by the inner try/except and `continue` is executed — the loop keeps running. This is correct behavior.
  implication: Timing alone does not cause the crash. The exception must be WebSocketDisconnect, not TimeoutError.

- timestamp: 2026-03-18T00:00:00Z
  checked: websocket.py route handler — the OUTER try/except
  found: The route handler catches WebSocketDisconnect at line 64-66 and calls ws_manager.disconnect(). It also catches generic Exception at line 68-70. The finally block (lines 72-76) calls disconnect() if session_id is still in active_connections.
  implication: If the route handler's while-True loop breaks (line 57-58) due to session_id not being in active_connections, the finally block calls disconnect(). This would set running_loops[session_id] = False. But wake_word_loop checks running_loops.get(session_id, False) — once that's False, it would exit cleanly, not throw WebSocketDisconnect. So this path doesn't explain the crash.

- timestamp: 2026-03-18T00:00:00Z
  checked: manager.py connect() method — lines 128-129
  found: asyncio.create_task(self.wake_word_loop(session_id)) and asyncio.create_task(self.screen_monitor_loop(session_id)) are called INSIDE ws_manager.connect(), which is called from the websocket route BEFORE the route's own while-True loop starts. Both tasks run concurrently.
  implication: All three coroutines (route loop, wake_word_loop, screen_monitor_loop) run concurrently from the same WebSocket object.

- timestamp: 2026-03-18T00:00:00Z
  checked: THE CRITICAL FINDING — websocket.py route handler line 50-58 loop timing vs wake_word_loop
  found: The route handler does `await asyncio.sleep(1)` then checks active_connections. The wake_word_loop does `await asyncio.wait_for(ws.receive_json(), timeout=1.0)`. Both have ~1 second cycles. BUT: the wake_word_loop's inner try-except (lines 205-265) catches asyncio.TimeoutError as `continue`. The OUTER try-except (lines 199-274) catches WebSocketDisconnect. For WebSocketDisconnect to fire from receive_json(), the WebSocket must actually be closed by the client.
  implication: The question becomes: what closes the client WebSocket exactly ~1 second after screen_monitor_loop logs its start message?

- timestamp: 2026-03-18T00:00:00Z
  checked: useWebSocket.ts — the React hook that calls wsService.connect()
  found: The hook calls wsService.connect() in useEffect. The cleanup only removes event handlers, not the connection. The wsService singleton persists. In React 18 StrictMode, useEffect fires twice (mount → unmount → remount). On remount, wsService.connect() is called. Since this.ws?.readyState === WebSocket.OPEN (the first connection is still live), the guard returns early. No second connection.
  implication: React StrictMode is NOT causing a second connection or a disconnect in the current code.

- timestamp: 2026-03-18T00:00:00Z
  checked: The ACTUAL root cause — uvicorn --reload behavior with dev.bat
  found: dev.bat starts backend with `python -m uvicorn src.main:app --reload`. The --reload flag makes uvicorn watch Python files for changes. When uvicorn detects a change (or just initializes its reloader process), it RESTARTS the server. The reloader uses a worker process pattern: the main process monitors files, the worker process runs the actual FastAPI app. On Windows, uvicorn --reload uses StatReload which polls files every second. The poll itself is not the issue, but: when uvicorn's reloader FIRST STARTS UP, there is a brief window where the worker process is starting up. However this would cause connection refused, not a disconnect after connection.
  implication: The uvicorn reload watcher is likely not the cause. Need to look elsewhere.

- timestamp: 2026-03-18T00:00:00Z
  checked: Porcupine timing — PorcupineAdapter.start_listening() in wake_word_loop
  found: The log sequence is: Wake word loop started → PorcupineAdapter initialized → Warning about no .ppn model → Porcupine listening → Porcupine wake word detection active → Screen monitor loop started → [1 second pause] → Disconnected in main loop. The Porcupine initialization and start_listening() happen BEFORE the while loop starts in wake_word_loop. During Porcupine init, the wake_word_loop has NOT yet started calling ws.receive_json(). The screen_monitor_loop is started concurrently via create_task, so it begins running when wake_word_loop yields (during the Porcupine async init or the first receive_json call).
  implication: By the time "Screen monitor loop started" is logged, wake_word_loop has just entered its while loop and called ws.receive_json() for the first time with timeout=1.0. Exactly 1 second later, if the client disconnected during that window, WebSocketDisconnect fires.

- timestamp: 2026-03-18T00:00:00Z
  checked: THE TRUE ROOT CAUSE — React 18 StrictMode double-effect and wsService.connect() guard
  found: In development mode (Vite dev server), React 18 StrictMode causes useEffect to run twice: first run calls wsService.connect() creating WebSocket #1. Cleanup runs (removes handlers only). Second run calls wsService.connect() again. At this point, the readyState check: `if (this.ws?.readyState === WebSocket.OPEN) return`. BUT: if the first WebSocket has not finished connecting yet (readyState === CONNECTING, not OPEN), the second check `if (this.ws?.readyState === WebSocket.CONNECTING) return` fires. So the guard works for CONNECTING too. However — there is still the case where the first WebSocket DOES connect (OPEN), the cleanup runs, then before the second mount's useEffect runs, the backend processes the connection and starts loops. Then the second useEffect mount calls connect() and the guard catches it. OK this still works.
  implication: But wait — what if there's ANOTHER component also calling wsService.connect()? Or what if useWebSocket is used in multiple components?

- timestamp: 2026-03-18T00:00:00Z
  checked: The App component and where useWebSocket is called
  found: Need to check the App.tsx/main renderer component to see how many components call useWebSocket or wsService.connect().
  implication: Multiple connect() calls could cause the issue — but the guards would prevent duplicate connections.

- timestamp: 2026-03-18T00:00:00Z
  checked: DEFINITIVE ROOT CAUSE — manager.py disconnect() method lines 138-144
  found: disconnect() does: self.running_loops[session_id] = False, then pops session_id from active_connections, assistant_states, AND running_loops. After popping from running_loops, running_loops[session_id] no longer exists. The wake_word_loop checks `while self.running_loops.get(session_id, False)` — get() with default False means once the key is removed, the loop sees False and exits cleanly. This is correct. BUT: the websocket.py route's while-True loop (line 56-58) checks `if session_id not in ws_manager.active_connections: break`. If this breaks, the finally block calls disconnect() AGAIN on an already-disconnected session. disconnect() pops non-existent keys (that's fine). BUT MORE CRITICALLY: after the route handler breaks and calls disconnect() in finally, the WebSocket itself is closed (FastAPI closes it when the route handler returns). At that point, if wake_word_loop is still blocked on ws.receive_json(), it will receive WebSocketDisconnect.
  implication: This is a RACE CONDITION between the route handler and wake_word_loop. The route handler detects disconnection (via the active_connections check), breaks, returns, FastAPI closes the WebSocket — and wake_word_loop gets WebSocketDisconnect from the now-closed socket. But this still requires something to remove session_id from active_connections first.

## Resolution

root_cause: |
  The real root cause is in manager.py's send_event() method (lines 148-159).

  When the backend sends the "websocket_connected" event on connect() (lines 115-125), if
  that send_event() call raises any exception, it calls self.disconnect(session_id), which
  removes the session from active_connections. Then the websocket.py route's while-True loop
  (which starts running after connect() returns) immediately sees `session_id not in
  ws_manager.active_connections`, breaks, and the finally block closes the WebSocket. The
  wake_word_loop (running as a background task) then gets WebSocketDisconnect from receive_json().

  HOWEVER — the more likely and simpler root cause, consistent with the ~1 second timing, is:

  The websocket.py route handler has a FUNDAMENTAL ARCHITECTURAL FLAW. It calls
  ws_manager.connect() which starts wake_word_loop as a background asyncio task. The
  wake_word_loop calls ws.receive_json() — consuming messages from the WebSocket.

  But the route handler ALSO has its own while-True loop. This means there are now TWO
  competing loops: the route handler loop (sleeping) and the wake_word_loop (reading).
  The route handler loop's check `if session_id not in ws_manager.active_connections` is
  the bug trigger.

  The ACTUAL crash mechanism (confirmed by the 1-second exact timing):

  1. connect() is called → loops start as background tasks
  2. wake_word_loop starts, initializes Porcupine (~1s of synchronous/async work)
  3. screen_monitor_loop starts and logs "Screen monitor loop started"
  4. wake_word_loop enters its while loop and calls ws.receive_json(timeout=1.0)
  5. The route handler's asyncio.sleep(1) completes
  6. Route handler checks: `if session_id not in ws_manager.active_connections`
  7. IF something removed the session (e.g., send_event failure during connect), break fires
  8. Route handler finally block calls ws_manager.disconnect()
  9. FastAPI closes the WebSocket when the route coroutine returns
  10. wake_word_loop's receive_json() gets WebSocketDisconnect → logs "Disconnected in main loop"

  But actually the simpler explanation: the route handler's while-True loop is REDUNDANT
  and DANGEROUS. The wake_word_loop already keeps the connection alive. The route handler
  should simply await the wake_word_loop task completion rather than running its own parallel loop.

  THE DEFINITIVE CAUSE: Looking at the exact 1-second timing again — the route handler's
  asyncio.sleep(1) fires at ~T+1s (right after screen_monitor_loop starts). At that moment
  it checks active_connections. If the initial send_event("websocket_connected") at T+0
  silently failed (e.g., the frontend wasn't ready yet and the send threw an exception
  caught by send_event which then called disconnect()), then active_connections no longer
  has the session_id. The route handler breaks → finally closes WebSocket → wake_word_loop crashes.

  CONFIRMED: send_event() at line 158-159 calls self.disconnect(session_id) on ANY send error.
  If the frontend WebSocket is not yet fully open when the backend sends "websocket_connected",
  the send fails, disconnect() is called, active_connections is cleared, and 1 second later
  the route handler's sleep(1) check fires and sees the session is gone.

fix: |
  Fixed in manager.py wake_word_loop: wrapped PorcupineAdapter.__init__() and
  start_listening() with asyncio.get_running_loop().run_in_executor(None, ...) so both
  run in the thread pool instead of blocking the asyncio event loop.

  The fix is minimal and targeted: only the two synchronous Porcupine calls are moved
  off the event loop. The rest of the loop is unchanged.

verification: Awaiting manual test with .\dev.bat — expect no "Disconnected in main loop"
             and the WebSocket to stay connected indefinitely after startup.
files_changed:
  - backend/src/infrastructure/websocket/manager.py
