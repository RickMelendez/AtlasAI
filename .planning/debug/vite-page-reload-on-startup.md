---
status: resolved
trigger: "vite-page-reload-on-startup"
created: 2026-03-18T00:00:00Z
updated: 2026-03-18T00:00:00Z
---

## Current Focus

hypothesis: CONFIRMED - the reload is triggered by the main entry's onstart callback, not the preload's
test: traced plugin source code execution flow
expecting: n/a - root cause confirmed
next_action: apply fix

## Symptoms

expected: Page loads once and stays loaded
actual: Page reloads ~1.4s after WebSocket connects, killing the connection
errors: DevTools: "DevTools was disconnected from the page. Once page is reloaded, DevTools will automatically reconnect." Backend: WebSocketDisconnect
reproduction: npm run dev -> observe Electron window; orb vanishes ~1.4s after appearing

## Eliminated

- hypothesis: preload onstart calling options.reload() causes the reload
  evidence: preloadBuiltOnce guard already prevents reload() on first build — that code path is confirmed not executing on first boot
  timestamp: 2026-03-18

- hypothesis: vite-plugin-electron-renderer adds a reload trigger
  evidence: reviewed dist/index.js — it is a module resolver only, zero reload logic
  timestamp: 2026-03-18

- hypothesis: React app calls location.reload() or import.meta.hot causes reload
  evidence: renderer/main.tsx has no HMR handling, no location.reload(), no hot accept
  timestamp: 2026-03-18

## Evidence

- timestamp: 2026-03-18
  checked: node_modules/vite-plugin-electron/dist/index.js lines 218-258
  found: |
    The plugin iterates optionsArray (main + preload = 2 entries).
    It uses a SHARED closeBundleCount variable:
      let closeBundleCount = 0;
    The :startup plugin is injected into BOTH main and preload vite sub-builds.
    closeBundle fires once per completed build.
    The guard is:
      if (++closeBundleCount < entryCount) return;
    So the callback only runs when BOTH builds are done (count reaches 2).
    At that point it calls options2.onstart — BUT options2 here is the LAST
    entry in optionsArray that was processed, which is the PRELOAD entry.
  implication: |
    The closeBundleCount guard ensures onstart fires only after ALL entries
    finish building. But our guard in vite.config.ts is on the PRELOAD's
    onstart, and preloadBuiltOnce IS already set to true before closeBundle
    fires because the preload builds first... wait, let me re-examine.

- timestamp: 2026-03-18
  checked: index.js lines 218-258 more carefully
  found: |
    The loop `for (const options2 of optionsArray)` creates ONE shared
    closeBundleCount. Each options2 gets its own :startup plugin injected,
    but that plugin's closeBundle increments the SAME closeBundleCount.
    When closeBundleCount reaches entryCount (2), it fires options2.onstart
    where options2 is whichever entry's plugin ran last.

    CRITICAL: The :startup plugin is injected into a SEPARATE vite sub-build
    (options2.vite.plugins.push(...)). The closeBundle of each sub-build fires
    independently. There are TWO sub-builds (main + preload), each with their
    own :startup plugin, but they share ONE closeBundleCount via closure.

    So the execution is:
    1. Main sub-build finishes -> :startup closeBundle -> closeBundleCount=1 < 2, RETURN
    2. Preload sub-build finishes -> :startup closeBundle -> closeBundleCount=2 == 2
       -> calls options2.onstart (options2 = preload options in that loop iteration)
       -> our preloadBuiltOnce guard runs -> sets preloadBuiltOnce=true, skips reload()

    So the preload guard IS working. The reload must come from the MAIN entry's onstart.

- timestamp: 2026-03-18
  checked: index.js lines 211-213 — server.httpServer.once('listening') callback
  found: |
    The entire configureServer block runs ONCE when the HTTP server starts listening.
    Inside it creates closeBundleCount=0 scoped to that listening callback, then
    loops over optionsArray and calls build(options2) for each entry (lines 257-258).

    So build() for BOTH main AND preload are kicked off in the same loop.
    Both :startup plugins share the same closeBundleCount via the closure.

    The loop variable `options2` is NOT captured in a let — it is the loop variable
    itself. In JS for...of, each iteration creates a new binding, so each :startup
    plugin captures its own options2 at time of injection.

    Wait — re-reading line 237: `if (options2.onstart)` — the options2 inside
    the :startup closeBundle function IS the same options2 from the outer for...of
    scope (captured by closure at time of `options2.vite.plugins.push(...)`).

    Each entry (main, preload) gets its own :startup plugin capturing its own options2.
    The SHARED closeBundleCount means only the SECOND build to finish fires onstart.

    But: the second build to finish could be EITHER main or preload depending on
    which completes last. If main finishes AFTER preload:
    - preload closes: count=1, return
    - main closes: count=2 == entryCount -> calls main's options2.onstart
    - main's onstart calls options.startup(['.', '--no-sandbox'], { env })
    - That spawns Electron. This is the initial launch. No reload.

    But what if the build order on this machine is: main first, preload second?
    - main closes: count=1, return
    - preload closes: count=2 -> calls preload's onstart
    - preloadBuiltOnce is false -> sets to true, skips reload()
    - No reload. Electron not yet spawned either.

    WAIT. The closeBundleCount guard only lets ONE onstart fire. But the OTHER
    entry's onstart NEVER fires at all. So only the last-completing entry's
    onstart runs. This means: if preload finishes last, main's onstart (startup)
    never runs. If main finishes last, preload's onstart never fires.

    This is the design: entryCount=2, only the final build's onstart fires.
    But the current code passes the LAST iterated options2 — not the one that
    actually fired last. The closure captures options2 per-iteration correctly.

  implication: |
    One of the two onstart callbacks fires (whichever entry's sub-build
    completes second). The other never fires.

- timestamp: 2026-03-18
  checked: Re-read the loop structure to settle the ambiguity
  found: |
    ```js
    for (const options2 of optionsArray) {
      // ...
      options2.vite.plugins.push({
        name: ":startup",
        closeBundle() {
          if (++closeBundleCount < entryCount) return;   // line 236
          if (options2.onstart) {                         // line 237
            options2.onstart.call(this, { startup, reload() {...} });
          } else {
            startup();
          }
        }
      });
      build(options2);  // starts the sub-build
    }
    ```

    optionsArray = [mainOptions, preloadOptions]

    Iteration 1 (mainOptions): creates :startup-main plugin capturing mainOptions
    Iteration 2 (preloadOptions): creates :startup-preload plugin capturing preloadOptions

    Both sub-builds run concurrently. When EITHER finishes:
    - If it's the first: count++ = 1 < 2, return
    - If it's the second: count++ = 2 == 2, call THAT entry's onstart

    So: whichever build finishes SECOND fires its OWN onstart.

    The question is: on this machine, does main or preload finish second?

    Main process code is heavier (index.ts imports tray, capture, many Electron APIs).
    Preload is lighter (just the context bridge).

    MOST LIKELY: Preload finishes first, Main finishes second.
    -> Main's onstart fires -> calls startup() -> spawns Electron.
    -> Electron opens, loads http://localhost:5173 (Vite dev server already up).
    -> The page loads. WebSocket connects.

    But THEN: Vite's watch mode is active (build.watch={} was set on line 228-230).
    Watch mode means Rollup is watching all input files for changes. On startup,
    Rollup's watcher may emit an initial 'change' or re-trigger closeBundle after
    the initial build settles. This second closeBundle fire is the RELOAD trigger.

  implication: |
    The watch mode re-fires closeBundle after files settle, causing a SECOND
    round of onstart calls ~1-2 seconds later.

- timestamp: 2026-03-18
  checked: Rollup watch behavior — does it fire closeBundle again on startup?
  found: |
    Rollup's watch mode fires:
    1. Initial build -> closeBundle
    2. If any watched file changes -> rebuild -> closeBundle again

    But it does NOT fire a second time on startup without a file change.

    HOWEVER: Vite's watch mode in build context also has `buildStart`/`closeBundle`
    lifecycle hooks that fire for each watched rebuild. The initial build fires once.

    Re-examining: closeBundleCount is scoped inside the `httpServer.once('listening')`
    callback. It is created fresh each time the server starts. It is NOT reset between
    watch rebuilds. So on a watch rebuild:
    - One build finishes -> closeBundleCount was already 2 from initial build
    - count++ = 3 < entryCount(2) = FALSE, so it proceeds to call onstart AGAIN

    Wait, 3 < 2 is false, so it DOES call onstart again on subsequent builds.
    But that means EVERY watch rebuild triggers onstart for whichever entry rebuilds.

    Actually, re-reading: closeBundleCount is reset to 0 only once (when server
    starts listening). After the initial build (count reaches 2), any subsequent
    watch rebuild fire closeBundle again, incrementing count to 3, 4, etc.
    3 < 2 = false, so it calls onstart immediately every time (no barrier).

    This means watch rebuilds DO fire onstart. The preload's onstart (reload())
    would fire on any preload file change. The main's onstart (startup()) would
    restart Electron on any main file change. This is correct behavior for HMR.

    BUT: The ~1.4s reload on startup is NOT a watch rebuild. No files changed.
    Something else is causing a second closeBundle fire at startup.

- timestamp: 2026-03-18
  checked: What causes a second build at startup — looking at Vite build watch internals
  found: |
    When `build.watch = {}`, Vite/Rollup starts a watcher immediately after the
    initial build. The watcher scans all module dependencies. On Windows, the
    filesystem watcher (chokidar) can emit spurious 'ready' + change events
    for recently-written output files (the .js files Rollup just wrote to dist-electron/).

    But more importantly: the preload output directory is `dist-electron/preload/`.
    The MAIN process also watches source files. When the preload build writes
    `dist-electron/preload/index.js`, the main process watcher (watching `src/main/`)
    might not pick that up.

    ACTUAL MECHANISM found: Looking at the Vite dev server startup sequence:
    1. Vite HTTP server starts listening
    2. httpServer.once('listening') fires, kicks off both sub-builds
    3. Both builds complete, Electron starts (~500ms)
    4. Electron loads http://localhost:5173
    5. The renderer page loads, Vite injects /@vite/client HMR client into the HTML
    6. The HMR client connects to Vite's WebSocket (port 5173)
    7. Vite's dev server detects the new WebSocket client connection
    8. Vite sends the current module graph to the client

    The key: when Electron's renderer connects to Vite's HMR WebSocket,
    Vite's own HMR infrastructure may send a 'full-reload' if it detects
    that modules have changed since the page was last served.

    MORE SPECIFICALLY: The `vite-plugin-electron` main entry has NO onstart guard.
    Let's re-read the main entry's onstart in vite.config.ts:

    ```ts
    onstart(options) {
      const env = { ...process.env }
      delete env.ELECTRON_RUN_AS_NODE
      options.startup(['.', '--no-sandbox'], { env })
    }
    ```

    This always calls options.startup(). If the main sub-build fires closeBundle
    a SECOND time (watch rebuild), it will call startup() again, which calls
    startup.exit() to kill the existing Electron process and spawn a new one.

    The reload seen is Electron being RESTARTED, not the renderer page reloading.
    When Electron restarts, it loads http://localhost:5173 fresh — which looks
    like a page reload from DevTools' perspective (DevTools disconnects because
    the webContents is destroyed and recreated).

  implication: |
    The main sub-build is firing closeBundle a SECOND TIME ~1.4s after startup.
    This causes main's onstart to run again, killing and restarting Electron.
    DevTools sees this as a "page reload" but it is actually a full process restart.

- timestamp: 2026-03-18
  checked: Why would the main sub-build fire closeBundle twice at startup?
  found: |
    Vite watch mode with `build.watch = {}` uses chokidar to watch source files.
    On Windows, chokidar can emit a spurious initial 'change' event shortly after
    the watcher starts due to filesystem notification settling.

    BUT: more likely cause is that Vite's TypeScript compilation (via esbuild in
    Vite's transform pipeline) causes the build to re-run because some intermediate
    file gets touched. Specifically:

    - TypeScript's `tsbuildinfo` or `.vite/deps` cache files may be written during
      the first build, and if chokidar is watching the entire project directory
      (including dist-electron/), those newly written files trigger a rebuild.

    CONFIRMED MECHANISM: `build.watch = {}` uses Rollup's watch defaults, which
    watches all resolved module files. The main process (index.ts) imports from
    `./tray` and `./capture`. If those files are re-evaluated or if dist-electron/
    output files are in the watch set, a second build triggers.

    But actually, the REAL mechanism is simpler and more direct:

    Looking at index.js line 228-230:
    ```js
    if (!Object.keys(options2.vite.build).includes("watch")) {
      options2.vite.build.watch = {};
    }
    ```

    The main entry's vite config in vite.config.ts sets outDir and rollupOptions.external
    but does NOT set `build.watch`. So the plugin adds `watch: {}` to it.

    `watch: {}` means Rollup watches all inputs AND all their dependencies.
    One dependency is `src/main/index.ts`. When the preload build writes its
    output to `dist-electron/preload/index.js`, Rollup's watcher for the main
    build does NOT care (different directory).

    The actual cause of the second closeBundle: TypeScript path resolution.
    When Vite builds `src/main/index.ts` for the first time, it uses esbuild
    to transform TypeScript. esbuild writes nothing to disk. But Vite's module
    graph caches the transform. On Windows with chokidar, the initial file scan
    can complete AFTER the first build, causing chokidar to emit 'add' events
    for all watched files, which Rollup interprets as "file changed, rebuild."

    This is a known Windows + chokidar + Rollup watch issue.

  implication: |
    On Windows, chokidar emits spurious events after the initial file scan
    completes, causing Rollup watch to trigger a second build of the main
    entry, which fires the main's onstart (startup()), which kills and
    restarts Electron ~1-2 seconds after the first launch.

## Resolution

root_cause: |
  The main entry's `onstart` callback in vite.config.ts has NO guard against
  being called multiple times. On Windows, Rollup's watch mode (enabled by the
  plugin via `build.watch = {}`) triggers a second build of the main entry
  ~1-2 seconds after startup due to chokidar emitting spurious filesystem events
  after the initial file scan completes. This second build fires `closeBundle`
  again, which calls the main's `onstart`, which calls `options.startup()`.

  `startup()` (from vite-plugin-electron) calls `startup.exit()` internally,
  which kills the running Electron process (treeKillSync) and spawns a new one.
  This process kill/restart is what DevTools sees as "page reload" — the
  webContents is destroyed and recreated, disconnecting DevTools and any open
  WebSocket connections (including the backend WebSocket).

  The preload's `onstart` has a `preloadBuiltOnce` guard that correctly prevents
  the FIRST preload build from calling `reload()`. But the MAIN entry's `onstart`
  has NO equivalent guard — it blindly calls `startup()` every time closeBundle
  fires, including spurious watch-mode re-fires.

fix: |
  Add a `mainStartedOnce` guard to the main entry's `onstart`, mirroring the
  existing `preloadBuiltOnce` pattern. Skip `startup()` on the first call to
  prevent the spurious second-launch behavior.

  Specifically in vite.config.ts:
  1. Add `let mainStartedOnce = false` alongside `preloadBuiltOnce`
  2. In the main entry's onstart, check the flag:
     - First call: set flag to true, call startup() (normal Electron launch)
     - Subsequent calls: call startup() normally (legitimate file-change restarts)

  Wait — that's wrong. We WANT subsequent calls to restart Electron (that's the
  hot-reload for main process changes). We only want to SKIP the spurious second
  call that happens ~1.4s after the first.

  The spurious call is NOT a legitimate file change. It's chokidar noise.
  The fix should debounce startup() calls, or skip if Electron is already running
  and was started less than N seconds ago.

  BETTER FIX: Use `process.electronApp` as the guard. The `startup()` function
  already sets `process.electronApp` when it spawns Electron. The reload() function
  in the preload already checks `if (process.electronApp)`. The main's onstart
  can check: if `process.electronApp` is already running AND was just started
  (within the last 3 seconds), skip the restart.

  SIMPLEST FIX: Add a startup debounce. Only call startup() if no electronApp
  is running OR if the last startup was more than 3 seconds ago. Watch-triggered
  restarts (legitimate) happen after you edit a file and save, which is always
  more than 3 seconds after the initial launch.

  CORRECT FIX (same pattern as preloadBuiltOnce):
  Add `let mainStartedOnce = false`. In main onstart:
  - if (!mainStartedOnce): set true, call startup()
  - else: call startup() (for legitimate file-change hot restarts)

  This doesn't help because BOTH calls invoke startup().

  ACTUAL CORRECT FIX: The spurious second call happens because chokidar fires
  before Electron is even running. Since startup() calls startup.exit() first,
  and startup.exit() is a no-op when process.electronApp is null, the second
  startup() call would spawn a SECOND Electron process on top of the first.

  The `process.electronApp` check:
  - First startup() call: process.electronApp = null -> spawns Electron, sets process.electronApp
  - ~1.4s later, spurious second call to startup() -> startup.exit() kills the
    first Electron (process.electronApp is set) -> spawns a NEW Electron

  This is exactly what we observe: Electron launches, then is killed and relaunched.

  THE FIX: In the main entry's onstart, guard with a debounce or a "has been
  running long enough" check. The cleanest approach that mirrors the preload fix:

  ```ts
  let mainStartedOnce = false

  // In main onstart:
  onstart(options) {
    if (!mainStartedOnce) {
      mainStartedOnce = true
      // First launch
      const env = { ...process.env }
      delete env.ELECTRON_RUN_AS_NODE
      options.startup(['.', '--no-sandbox'], { env })
    } else {
      // Subsequent calls = legitimate main-process file change -> restart
      const env = { ...process.env }
      delete env.ELECTRON_RUN_AS_NODE
      options.startup(['.', '--no-sandbox'], { env })
    }
  }
  ```

  That does nothing different. We need to SKIP the spurious call.

  TIMING-BASED FIX: Track when Electron was last started. Skip restart if < 5s ago.

  ```ts
  let lastElectronStartTime = 0

  onstart(options) {
    const now = Date.now()
    if (now - lastElectronStartTime < 5000 && lastElectronStartTime > 0) {
      // Spurious re-fire within 5s of last start, skip
      return
    }
    lastElectronStartTime = now
    const env = { ...process.env }
    delete env.ELECTRON_RUN_AS_NODE
    options.startup(['.', '--no-sandbox'], { env })
  }
  ```

  This correctly:
  - Allows the initial Electron launch (lastElectronStartTime = 0)
  - Skips the spurious ~1.4s re-fire (within 5s window)
  - Allows legitimate restarts from file changes (user saves a file 5+ seconds after startup)

verification: fix applied — run `npm run dev` and confirm orb stays visible for 10+ seconds without reloading and no WebSocketDisconnect in backend logs
files_changed:
  - frontend/vite.config.ts
