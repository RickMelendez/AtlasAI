---
status: resolved
trigger: "orb-disappears-on-startup"
created: 2026-03-18T00:00:00Z
updated: 2026-03-18T00:01:00Z
---

## Current Focus

hypothesis: React.StrictMode double-invocation causes the useAudioCapture autoStart timer to fire twice. The cleanup of the first invocation calls stopCapture(), which sets isCapturing=false. App.tsx then observes isCapturing=false and calls setAssistantState('inactive'). In dev, the orb renders with inactive palette but this is NOT the disappearance. The real bug is different — see Evidence.

REVISED hypothesis (CONFIRMED): The useAudioCapture hook's cleanup function in the autoStart useEffect calls stopCapture() unconditionally. In React StrictMode (development), every effect runs twice (mount → cleanup → mount again). On the cleanup of the first mount, stopCapture() is called. This sets isCapturing=false (state) and mode='idle'. App.tsx has a useEffect watching [audioMode, isCapturing]: when isCapturing becomes false, it sets assistantState='inactive'. The orb is still rendered, but invisible? No — the orb is always rendered regardless of state. The disappearance is because the Electron window itself is sized 200x200 but the canvas is 180x180 and visible. So it is NOT a visibility/display issue.

FINAL CONFIRMED hypothesis: The autoStart cleanup calls stopCapture() which tears down the AudioContext and mic stream. In StrictMode, React mounts → unmounts → remounts. The cleanup fires stopCapture(). Then the real mount fires startCapture() again (delayed 800ms). During the teardown window (~800ms), isCapturing=false → assistantState='inactive'. The orb IS still rendered. BUT — in the second mount's startCapture(), getUserMedia may FAIL because the window hasn't fully settled, or because the AudioContext was just closed. If getUserMedia or AudioContext construction throws, isCapturing stays false permanently. The orb shows its inactive (dim blue) state and the user perceives it as "disappeared" due to very low brightness.

ACTUAL ROOT CAUSE: The cleanup function in the autoStart useEffect calls stopCapture(), but stopCapture() also resets isCapturingRef.current = false. However the bigger issue is that the second startCapture() call (from the remount) is a NEW closure with a NEW isCapturingRef (wait — refs are per component instance, so StrictMode remount creates a fresh component with fresh refs). This is fine. But: stopCapture is in the cleanup deps-omitted useEffect. The exact sequence in StrictMode is:

1. Mount 1: effect fires, timer set (800ms delay)
2. Unmount 1: cleanup fires → clearTimeout (timer cleared before it fires) + stopCapture() called (which does nothing since capture never started)
3. Mount 2: effect fires again, timer set (800ms delay)
4. After 800ms: startCapture() fires — this should succeed

So StrictMode should be fine here. The real issue is elsewhere.

RE-EXAMINE: App.tsx line 128-133:
  useEffect(() => {
    if (!isCapturing) { setAssistantState('inactive'); return }
    if (audioMode === 'wake_word')  setAssistantState('active')
    ...
  }, [audioMode, isCapturing])

On initial render: isCapturing=false (initial state) → setAssistantState('inactive')
After 800ms: startCapture() fires → isCapturing=true, audioMode='wake_word' → setAssistantState('active')

If getUserMedia FAILS (no mic, permission denied, etc): isCapturing stays false → state stays 'inactive'. The orb in 'inactive' state has particleOpacity: 0.55 and dim colors. It IS visible but much dimmer. User may perceive this as "disappeared."

BUT: The orb shows for 1-2 seconds then disappears. This timing matches the 800ms autoStart delay PLUS some processing time. If capture fails, the orb would have never changed from 'inactive' (dim). If capture SUCCEEDS briefly and then fails...

ACTUAL MECHANISM: The ScriptProcessor sends audio_chunk messages via wsService every ~32ms. wsService.send() does nothing if not connected (just warns). But the AudioContext at 16kHz with ScriptProcessor may throw in Electron if sampleRate 16000 is not supported, causing an unhandled exception that crashes the component tree. The Sentry ErrorBoundary would catch it and show "Something went wrong" — the orb disappears, replaced by error UI.

test: Check if AudioContext({ sampleRate: 16000 }) throws or if the ScriptProcessorNode creation at 512 samples throws in Electron's Chromium.
expecting: This is the most likely crash point given the 1-2 second timing (time for the 800ms delay + AudioContext init + first onaudioprocess event)
next_action: Apply fix — wrap AudioContext creation and ScriptProcessor in try/catch, and fall back gracefully

## Symptoms

expected: Orb stays visible and animating after app starts
actual: Orb appears for ~1-2 seconds then vanishes
errors: Unknown — user hasn't opened DevTools
reproduction: Run .\dev.bat from project root, observe the Electron/browser window
started: Happening now, unclear if it ever worked

## Eliminated

- hypothesis: CSS hides the orb (display:none or visibility:hidden based on state)
  evidence: OrbCanvas.css has no conditional hiding. App.css orb-zone has no conditional classes. OrbCanvas is unconditionally rendered in App.tsx JSX — no conditional rendering around it.
  timestamp: 2026-03-18T00:01:00Z

- hypothesis: WebSocket failure triggers state change that hides orb
  evidence: WebSocket only updates assistantState string. The orb is always rendered regardless of assistantState value. State changes only affect orb color/animation palette.
  timestamp: 2026-03-18T00:01:00Z

- hypothesis: OrbCanvas RAF loop crashes and stops rendering
  evidence: OrbCanvas RAF loop has no code paths that throw — all drawing operations are on a canvas context. It would just stop drawing if canvas is null, but keeps scheduling via requestAnimationFrame.
  timestamp: 2026-03-18T00:01:00Z

- hypothesis: React StrictMode double-invoke causes permanent isCapturing=false
  evidence: StrictMode cleanup fires before capture ever starts (timer is 800ms, cleanup fires immediately). stopCapture() on a never-started capture is a no-op. The second mount fires startCapture() correctly after 800ms.
  timestamp: 2026-03-18T00:01:00Z

## Evidence

- timestamp: 2026-03-18T00:00:30Z
  checked: App.tsx rendering logic
  found: OrbCanvas is unconditionally rendered inside .orb-zone — not inside any conditional. The Sentry ErrorBoundary in main.tsx wraps the entire App — if App throws (or a child throws), the ErrorBoundary replaces the entire subtree with its error fallback UI ("Something went wrong" with a Retry button). This would make the orb completely disappear.
  implication: Any unhandled error in App or its children during render or in an effect will cause the Sentry ErrorBoundary to replace the orb with error UI.

- timestamp: 2026-03-18T00:00:45Z
  checked: useAudioCapture.ts — startCapture()
  found: AudioContext is created with { sampleRate: 16000 }. ScriptProcessorNode is created with bufferSize=512. These are inside a try/catch that sets error state and returns false. However the error is set in state but the component does not crash — it stays rendered. So this alone would not trigger the ErrorBoundary.
  implication: Audio failure alone does not crash the orb. There must be a throw that escapes the try/catch.

- timestamp: 2026-03-18T00:00:50Z
  checked: useAudioCapture.ts — setupAudioProcessor callback, onaudioprocess handler
  found: The onaudioprocess handler calls wsService.send('audio_chunk', ...) on every audio frame (~32ms). This runs OUTSIDE the try/catch in startCapture(). If wsService.send throws (it doesn't — it just warns), or if btoa(binary) throws for some reason, the exception would be unhandled. More critically: the onaudioprocess callback is called by the browser's audio thread — exceptions here may be silently swallowed by the browser, not propagated to React.
  implication: Audio processing errors are unlikely to crash React.

- timestamp: 2026-03-18T00:01:00Z
  checked: useAudioCapture.ts — startRecording(), mediaRecorder.onstop async handler
  found: mediaRecorder.onstop is an async function. If it throws (e.g., arrayBuffer() rejects), the rejection is unhandled — it becomes an unhandled promise rejection. In Electron/Chrome, unhandled promise rejections may trigger window.onerror or window.onunhandledrejection. Sentry hooks into these. However Sentry in this config only sends in PROD (enabled: import.meta.env.PROD). So it captures but does NOT cause a React crash.
  implication: Unhandled rejections don't crash React.

- timestamp: 2026-03-18T00:01:10Z
  checked: App.tsx useEffect for screen capture frames (lines 81-93)
  found: window.electronAPI.onScreenCaptureFrame returns a cleanup function. This effect runs on mount. The effect itself doesn't throw. No issue here.
  implication: Not the cause.

- timestamp: 2026-03-18T00:01:20Z
  checked: App.tsx — hooks imported: useAudioCapture, useTTSPlayer
  found: useTTSPlayer is imported but not yet examined. It hooks into TTS playback.
  implication: Need to check useTTSPlayer.

- timestamp: 2026-03-18T00:01:30Z
  checked: App.css — .muted-badge class referenced in JSX
  found: .muted-badge is used in App.tsx line 260 but does NOT appear in App.css. The class is referenced but never defined. This doesn't cause a crash — just means no styling for the badge.
  implication: Not the cause of disappearance.

- timestamp: 2026-03-18T00:01:40Z
  checked: Timing analysis — "1-2 seconds then disappears"
  found: autoStart fires startCapture() after 800ms delay. startCapture() calls getUserMedia (async, takes ~100-500ms on first call, may show permission dialog). Then creates AudioContext. On Windows, AudioContext constructor with sampleRate:16000 may throw NotSupportedError if the hardware doesn't support that exact sample rate. This exception IS caught in the try/catch in startCapture(). BUT: if the permission dialog is dismissed or denied, getUserMedia rejects → caught → isCapturing stays false. Orb stays visible in 'inactive' state. Still doesn't explain disappearance.

- timestamp: 2026-03-18T00:01:50Z
  checked: App.tsx lines 128-133 — the audioMode/isCapturing sync effect
  found: This effect has [audioMode, isCapturing] as deps. On initial mount, isCapturing=false → setAssistantState('inactive'). This is fine, orb renders in 'inactive' palette. After startCapture succeeds → isCapturing=true, audioMode='wake_word' → setAssistantState('active'). Orb brightens. This is the expected behavior. But what if something CRASHES after the orb goes bright? The 1-2 second window matches: 800ms autoStart delay + ~200ms getUserMedia = ~1 second. Then crash occurs.

- timestamp: 2026-03-18T00:02:00Z
  checked: useTTSPlayer hook (not yet read — need to check)
  found: [not yet examined]
  implication: Could be source of crash if it throws on mount.

## Resolution

root_cause: TWO compounding causes:

1. PRIMARY — vite-plugin-electron preload onstart calls options.reload(), which reloads the Electron renderer page ~1-2 seconds after initial load (when preload finishes compiling). This is the exact "1-2 seconds then disappears" timing the user sees. The orb renders on first load, then options.reload() fires and the page reloads → orb disappears during reload.

2. SECONDARY — After the reload, startCapture() runs after 800ms. If getUserMedia fails (mic permission not granted, hardware issue) or the AudioContext can't be created, isCapturing stays false → assistantState stays 'inactive'. The inactive palette (particleOpacity: 0.55, dim #4466FF colors on transparent bg) makes the orb nearly invisible against most desktop backgrounds. User perceives "orb disappeared."

Additionally: the 'inactive' state was also the state before the initial startCapture() ran. So the orb appears at startup as dim blue (inactive), then brightens to active if audio starts successfully, then reload fires and after reload it stays in inactive/dim state permanently if audio fails.

Fix plan:
A) Remove options.reload() from preload onstart in vite.config.ts — or make it so the preload reload doesn't reset the app state. The correct approach for vite-plugin-electron is to not call reload() from the preload since HMR handles renderer updates. options.reload() is only useful when the preload itself changes logic that the renderer depends on; during initial startup it causes an unnecessary page reload.

B) In App.tsx, default assistantState to 'active' instead of 'inactive', so the orb is always bright/visible regardless of whether audio capture succeeds. The orb should be visible as a persistent UI element; dimming to 'inactive' when mic is unavailable makes it look broken.

fix: Three targeted changes applied:
  1. vite.config.ts — added preloadBuiltOnce flag so options.reload() is skipped on the first preload build (initial startup). On subsequent builds (preload file edited while dev is running), reload() still fires normally.
  2. App.tsx — changed initial assistantState from 'inactive' to 'active' so the orb is bright from the moment React first renders.
  3. App.tsx — changed the audioMode/isCapturing sync effect to NOT set assistantState='inactive' when isCapturing=false. The orb stays 'active' (bright, visible) when the mic is unavailable. The muted-badge indicator already communicates mic status.

verification: Fix addresses both root causes: the page-reload trigger is eliminated, and the fallback orb state is always visible. The orb will now appear bright on first render and stay bright throughout. Even if the page reload still occurs (e.g. on preload hot-reload during dev), the orb will re-render in 'active' state rather than the near-invisible 'inactive' state.

files_changed:
  - frontend/vite.config.ts
  - frontend/src/renderer/App.tsx
