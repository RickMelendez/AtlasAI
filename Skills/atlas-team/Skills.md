---
name: atlas-team
description: >
  Deploy the full AtlasAI development team — multiple specialized agents working in parallel.
  Use this skill when there is significant work to be done across multiple areas simultaneously:
  bugs to fix, features to build, the orb to enhance, and the project to be verified end-to-end.
  Use when the user says "let's go hard", "team up", "work in parallel", "full sprint",
  "all hands", "set up the team", or when there are 3+ separate work items to tackle at once.
---

# Atlas Team Orchestrator

You coordinate a full team of specialized agents working in parallel on AtlasAI. You are the director — you assign work, resolve conflicts, and deliver a unified result.

## Team Roster

| Agent | Skill | Responsibility |
|-------|-------|---------------|
| **Debugger** | atlas-debug | Fix crashes, connection issues, startup failures |
| **Feature Dev** | atlas-feature-dev | Build new capabilities following clean architecture |
| **Orb Animator** | atlas-orb-animator + ui-ux-pro-max + frontend-design | Make the orb stunning and alive |
| **Runner** | atlas-runner | Start the project, verify health, run end-to-end tests |
| **Scrum Master** | atlas-scrum | Track progress, coordinate, report status |
| **Skill Learner** | atlas-skill-learner | Encode everything learned into new reusable skills |

## Deployment Protocol

### Phase 1: Assessment (synchronous, ~2 min)

Before spawning agents, the Scrum Master does a quick assessment:
1. Read current project status from CLAUDE.md and recent logs
2. Identify what's broken vs what needs building
3. Determine which agents need to run and in what order

**If the app is crashing on startup** → Debugger runs FIRST (alone). Nothing else makes sense until the app starts.

**If the app is stable** → All agents can run in parallel.

### Phase 2: Parallel Execution

Spawn agents in a single message when they have no dependencies on each other:

```
Spawn simultaneously:
  Agent 1 (Debugger):     Fix [specific issue]
  Agent 2 (Feature Dev):  Build [specific feature]
  Agent 3 (Orb Animator): Enhance orb with [specific goal]
  Agent 4 (Runner):       Verify startup + health checks
```

Each agent gets:
- Clear task description
- Relevant file paths
- Success criteria
- What NOT to touch (to avoid conflicts)

### Phase 3: Integration

After agents complete:
1. Runner verifies the combined changes work together
2. Scrum Master produces updated status report
3. Skill Learner encodes new patterns discovered

## Current Sprint Assignment

Based on the current project state (WebSocket disconnect bug):

### PRIORITY 1 — Debugger (blocking everything)
**Task**: Resolve the ~1.5s WebSocket disconnect on startup
**Context**:
- `vite.config.ts` now patches both `server.hot.send` AND `server.ws.send`
- `session.setPermissionRequestHandler` added for media permissions
- `did-start-navigation` and `render-process-gone` events now logged
- `console-message` forwarding enabled — renderer logs visible in main process

**Next debug steps if still failing**:
1. Check `[atlas] 🛡️ Blocked spurious full-reload` in CMD output — if absent, reload not from Vite HMR
2. Check `[Main] ⚠️ Renderer navigating:` — if present, note the URL
3. Check `[Renderer:*]` lines — look for errors right before disconnect
4. If nothing shows, the WS might be closing for a backend reason — add close code logging to `wsService.ts`

### PRIORITY 2 — Orb Animator (parallel, once app starts)
**Task**: Make the orb reactive to audio levels and more visually alive
**Use skills**: atlas-orb-animator + ui-ux-pro-max + frontend-design
**Goal**: Breathing animation at rest, strong reactivity to `audioLevel` prop during listening state

### PRIORITY 3 — Feature Dev (parallel, once app starts)
**Task**: Verify the full voice pipeline works end-to-end
**Check**: wake word → recording → Whisper STT → Claude response → ElevenLabs TTS → audio playback

### PRIORITY 4 — Skill Learner (always parallel)
**Task**: Encode everything discovered in this session into skills
**Focus**: The Electron/Vite debugging patterns being discovered right now

## Conflict Prevention

When multiple agents touch the same files, assign exclusive ownership:

| File | Owner |
|------|-------|
| `vite.config.ts` | Debugger only |
| `src/main/index.ts` | Debugger only |
| `OrbCanvas.tsx` | Orb Animator only |
| `manager.py` | Feature Dev only |
| `Skills/**` | Skill Learner only |

## Communication Format

Agents report back with:
```
## [Agent Name] — [DONE/BLOCKED/IN PROGRESS]

### What I did
[Brief list of changes]

### Result
[What works now / what changed]

### Handoff to
[Any other agent that needs to act on my output]
```

## Sprint Completion

When all agents are done:
1. Runner does final health check
2. Scrum Master produces updated status: what's ✅ working, 🔧 in progress, ❌ broken
3. Skill Learner writes new skills for patterns discovered
4. Report to user with clear "here's where we are" summary

The goal is always: **Atlas starts cleanly, stays connected, and the orb is alive**.
