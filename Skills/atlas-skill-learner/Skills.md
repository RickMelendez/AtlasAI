---
name: atlas-skill-learner
description: >
  Continuously learns from AtlasAI development work and creates new skills to capture that
  knowledge. Use this skill after solving a hard problem, discovering a pattern, or learning
  something that should be preserved for future sessions. Also use when you notice a recurring
  task that could be automated into a skill, or when the user says "remember this", "save this
  as a skill", "turn this into a skill", or "we keep doing X, make a skill for it".
---

# Atlas Skill Learner

You watch what happens during development, extract reusable patterns, and encode them as skills so the team never has to rediscover the same solution twice.

## When to Create a New Skill

Create a skill when:
- A problem took >30 minutes to solve and the solution is non-obvious
- A multi-step workflow was performed more than once
- A pattern is specific to AtlasAI architecture (not general knowledge)
- The user explicitly says to remember something
- A debugging session revealed a reliable diagnostic procedure

Don't create a skill for:
- Things in CLAUDE.md (already documented)
- One-off tasks that won't recur
- General programming knowledge (already in Claude's training)

## Skill Creation Process

### 1. Extract the Pattern

After completing work, review what happened:
- What was the input/trigger?
- What steps were taken?
- What decisions were made and why?
- What mistakes were avoided?
- What would make this faster next time?

### 2. Write the Skill

Skills live in: `c:\Users\Rickm\Personal-Projects\AtlasAI\Skills\[skill-name]\Skills.md`

Frontmatter format:
```yaml
---
name: skill-name
description: >
  One-paragraph description. What it does, when to trigger it.
  Be specific about trigger phrases so Claude knows when to use it.
---
```

Body should contain:
- Context specific to this project
- Step-by-step process
- Code snippets for common patterns
- Gotchas and edge cases discovered during work
- Links to relevant files

### 3. Validate the Skill

Before saving, check:
- Does the description clearly say WHEN to trigger it?
- Is it specific enough to be useful but general enough to apply next time?
- Does it include the WHY behind decisions, not just WHAT to do?
- Are file paths and code snippets accurate to the current codebase?

## Pattern Library

Track patterns discovered during AtlasAI development:

### Electron + Vite Patterns
- Spurious HMR reload: patch `server.hot.send` AND `server.ws.send` with time guard
- StrictMode WS: never `disconnect()` in useEffect cleanup for singletons
- Renderer console: `webContents.on('console-message', ...)` forwards logs to main
- Media permissions: `session.defaultSession.setPermissionRequestHandler`

### Python AsyncIO Patterns
- Blocking C extensions (Porcupine, PIL): always `run_in_executor`
- WebSocket timeout pattern: `asyncio.wait_for(ws.receive_json(), timeout=1.0)` + catch TimeoutError to continue loop

### AtlasAI-Specific Patterns
- New feature → check which clean architecture layer it belongs to first
- Wake word fallback: "computer" keyword when no .ppn file in backend/models/
- PCM buffer: use `deque` for O(1) popleft, not list slicing

## Skill Update Process

When an existing skill needs updating:
1. Read the current skill file
2. Add the new knowledge to the relevant section
3. Update any stale information (file paths, versions, etc.)
4. Note the date of the update in a comment if significant

## Output

When creating a skill, say:
```
Created: Skills/[skill-name]/Skills.md
Captures: [one sentence about what knowledge is encoded]
Trigger: [example phrases that would invoke this skill]
```
