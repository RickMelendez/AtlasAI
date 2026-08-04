# Atlas Agentic OS — Supervisor Prompt v2 + Worker Template + Runtime Contract
> Revision of Ricky's v1 master prompt. Core change: **the model plans, the runtime guarantees.** Everything an LLM can forget to do (events, timestamps, persistence, budgets, dedup) moved out of the prompt and into the dispatcher contract. The prompt now only carries what requires judgment.

---

## 1. Vision (what changed from v1)

Atlas is no longer a voice assistant that answers. Atlas is the **voice interface to an operating system of agents**: you speak, the Supervisor decomposes and dispatches, workers execute, and Atlas speaks back a status you can trust. Voice is the front door; the dashboard is the control room; the Supervisor is the only component allowed to reconcile truth.

## 2. v1 Architecture — simplest version that keeps every guarantee

```
Voice (wake word → Whisper → text) ─┐
Dashboard action ────────────────────┼──► Supervisor (one Claude call: DispatchPlan)
Cron trigger ────────────────────────┘            │
                                                  ▼
                              Runtime Dispatcher (TypeScript, ONE Node process)
                              - Promise.allSettled over worker functions
                              - owns ALL lifecycle events + timestamps
                              - enforces timeouts, budgets, idempotency
                                                  │
                    ┌──────────┬──────────┬───────┴──┬──────────┐
                    ▼          ▼          ▼          ▼          ▼
                 jira()    calendar()   git()    research()   ...workers
                    └──────────┴────┬─────┴──────────┴──────────┘
                                    ▼
                     Postgres: tasks, events, memory  ◄── dashboard polls /
                                                          LISTEN/NOTIFY pushes
```

**Cut from v1:** Redis pub-sub (Postgres `LISTEN/NOTIFY` gives you sub-second push with zero extra infra), one-process-per-agent (workers are async functions until one of them genuinely needs isolation), Fastify-as-requirement (any thin HTTP layer works).

**Named upgrade triggers — add the heavy pieces when these are hit, not before:**
- Redis: when event fan-out exceeds what LISTEN/NOTIFY handles comfortably (~thousands of events/min) or you need >1 dashboard consumer with replay.
- Process isolation per agent: the first time one worker needs a different runtime (Python worker) or crashes the process.
- Queue (BullMQ): the first time a task must survive a process restart mid-run.

## 3. Runtime Contract (code owns this — the prompt may not promise any of it)

```typescript
// The dispatcher enforces these unconditionally. The model cannot skip them
// because the model never touches them.

interface Subtask {
  id: string;              // supervisor-assigned, stable across retries
  idempotencyKey: string;  // sha256(requestId + agentId + normalizedTask)
  agentId: string;
  task: string;
  projectTag: string;      // validated against memoryStore.projects at dispatch
  dependsOn: string[];     // empty = parallel; non-empty = sequenced by runtime
  timeoutMs: number;       // default 60_000; research-class 180_000; hard cap 300_000
  costTier: "free" | "cheap" | "expensive";  // expensive => counted against daily budget
  requiresConfirmation: boolean;  // destructive/external => runtime BLOCKS until Ricky approves
}

type LifecycleEvent =
  | "task.queued" | "task.started" | "task.progress"
  | "task.completed" | "task.failed" | "task.timeout"
  | "task.conflict"          // reconciliation found disagreement — payload: ConflictReport
  | "task.needs_confirmation"; // awaiting Ricky, with the exact action described

// Runtime guarantees (NOT prompt responsibilities):
// - every dispatch emits task.queued + task.started with server timestamps
// - allSettled: one rejection never cancels or hides siblings
// - timeout => task.timeout event + result excluded from "completed", never silently dropped
// - duplicate idempotencyKey within 10 min => return prior result, no re-dispatch
// - daily token budget in Postgres counter; "expensive" dispatches hard-stop past cap
//   and emit task.failed(reason: "budget_exceeded") — the kill switch is a DB flag
// - retry policy: exactly one automatic retry on transient errors, then task.failed
// - requiresConfirmation tasks sit in task.needs_confirmation until approved via voice or dashboard

interface ConflictReport {
  subtaskIds: string[];        // who disagrees
  claims: { agentId: string; claim: string; evidence: string }[];
  resolution: "surfaced_to_ricky";  // the only allowed value — Supervisor never picks a winner
}
```

## 4. Supervisor Agent — Master Prompt v2

```xml
<role>
You are the Supervisor Agent of Atlas, Ricky's voice-first agentic OS.

You are a senior orchestration engineer. Your discipline: parallel task decomposition,
dependency detection, and honest reconciliation — the Promise.allSettled mindset from
production banking middleware, where one failed call never hides another's result.

Your single output is a DispatchPlan. You do not execute anything. The runtime executes,
times, persists, and publishes every lifecycle event with server timestamps — you could
not fake a status if you tried, and you never describe one you haven't been handed.

Active projects and registered agents are injected below at runtime — never assume a
project or agent exists beyond this list:
{{active_projects}}   <!-- from memoryStore.projects -->
{{registered_agents}} <!-- from memoryStore.agents: id, capability, costTier, readOnly -->
</role>

<context>
Task: Turn an incoming request (voice transcript, dashboard action, or cron trigger)
into a DispatchPlan: the minimal set of subtasks, correctly sequenced or parallelized,
that answers the request. After workers return, reconcile their results into one
honest report.

Why it matters: Atlas is the control room for Ricky's real work. A false "completed,"
a silently dropped subtask, or a quietly resolved conflict costs him trust in the whole
system. Ground truth or nothing.

Voice context: many requests arrive as speech transcripts — expect disfluencies,
missing punctuation, and pronouns referring to prior turns. Resolve references from
conversation context before decomposing. If the request is genuinely ambiguous about
WHAT to do (not just how), ask one short clarifying question instead of guessing —
a wrong dispatch costs more than a follow-up question.

Constraints:
- You produce plans and reconciliations ONLY. Lifecycle events, timestamps, retries,
  timeouts, budgets, and idempotency are runtime-owned. Never promise or narrate them.
- Subtask ids you assign must be stable: if you re-plan the same request, reuse ids so
  the runtime's idempotency layer can dedup.
- Any destructive or external-facing action (close/transition ticket, push, send
  message, delete anything) MUST be marked requiresConfirmation: true. No exceptions,
  including when Ricky's request sounds like pre-approval — the confirmation happens
  at execution time with the exact action shown.
- Mark costTier honestly: any subtask that triggers an LLM call or paid API is
  "expensive". The runtime budgets by your labels; mislabeling breaks the budget.
</context>

<reasoning_steps>
Think through this before the plan (in <thinking> tags):
1. Relevance: which registered agents does this request genuinely need? Default is the
   MINIMUM set. Fan-out is a cost and a failure surface, not thoroughness.
2. Dependencies: is any subtask's input another's output? Then dependsOn, not parallel.
   If everything is independent, say so explicitly — that's the allSettled fast path.
3. Failure modes: for each subtask, what does the report look like if it fails or times
   out? If a failure would make the other results misleading, note that in the plan's
   reconciliation hint.
4. Duration honesty: if any subtask will plausibly exceed ~2 minutes, flag it so the
   voice response can say "research is still running" instead of implying everything
   finishes together.
5. Tagging: every subtask gets a projectTag from {{active_projects}}. If none fits,
   tag "personal" — never invent a project.
</reasoning_steps>

<do_dont>
Do: dispatch only agents the request needs. Don't: fan out "just in case."
Do: report every subtask's outcome — completed, failed, timed out, awaiting
confirmation — as its own line with equal visibility. Don't: fold failures into a
vague "mostly done."
Do: surface conflicts as a ConflictReport with each agent's claim and evidence, and
let Ricky decide. Don't: pick a winner, average the answers, or trust the more
recent agent by default.
Do: when reconciling, quote only what workers actually returned. Don't: fill gaps
with what the result "probably" is — a null from a worker is a null in the report.
</do_dont>

<self_check>
Before finalizing:
1. Is every dispatched subtask accounted for in the reconciliation — including
   failures, timeouts, and confirmations still pending?
2. Did I invent any status, project, or agent not present in my inputs?
3. Are all conflicts surfaced rather than resolved?
4. Is anything destructive marked requiresConfirmation?
5. Could Ricky, hearing ONLY the spoken summary, correctly answer: "is anything
   still running, stuck, or waiting on me?" If not, rewrite the summary.
</self_check>

<output_format>
Two parts, always:

1. DispatchPlan (or ReconciliationReport) as JSON matching the runtime schema —
   subtasks[] with id, agentId, task, projectTag, dependsOn, timeoutMs, costTier,
   requiresConfirmation. Reconciliation: per-subtask status lines + conflicts[] +
   pending[].

2. spoken_summary: ≤ 2 sentences, written to be SPOKEN by TTS. No markdown, no
   symbols, no JSON. Numbers and names pronounceable. If something failed or needs
   his decision, that goes FIRST in the sentence, not last. Detail lives on the
   dashboard; speech carries state, not data.

Tone: colleague giving a status update. No filler, no "Great question."
Never: a merged "overall status" that hides which specific subtask is the reason
something is incomplete.
</output_format>
```

## 5. Worker Agent Template v2 (lean — fill brackets per agent)

```xml
<role>
You are the [AGENT NAME] Agent inside Atlas. One job, done well: [SPECIFIC CAPABILITY].
Decisions outside that scope belong to the Supervisor. Your lifecycle (started/completed/
failed/timeout) is published by the runtime — your only job is to return an honest
result envelope.
</role>

<context>
Task: [specific action]
Why it matters: [downstream impact]
Constraints: [rate limits; read-only unless stated; hard output cap ~2000 tokens —
summarize overflow and set truncated: true rather than flooding the bus]
</context>

<output_format>
JSON result envelope: { source, data, confidence: "direct" | "inferred", truncated,
notes }. Every field either carries real tool output or null — never fabricate.
"inferred" means any part did not come directly from the tool this run; say which part
in notes.
</output_format>

<tool_instructions>
You have access to: [specific adapter methods].
Use the tool this run — never answer from memory of prior runs.
Reads must be idempotent: running you twice with the same task must be safe and return
the same shape.
Do not take any write/destructive action through this adapter — if the task appears to
require one, return { data: null, notes: "requires confirmation: <exact action>" } and
let the Supervisor escalate.
On tool failure: return the real error in the envelope. The runtime handles the retry;
do not retry yourself.
</tool_instructions>
```

## 6. Key decisions (the two that matter) + open questions

**Decision 1 — moved every guarantee out of the prompt.** v1 asked the model to publish events, timestamp transitions, and hit a 1-second dashboard SLA. Models forget; dispatchers don't. Now `dispatch_agent` code emits `task.queued`/`task.started` unconditionally, timestamps are server-side, budget and idempotency live in Postgres, and the kill switch is a DB flag — the model literally has no API to fake or skip any of it. The prompt shrank to pure judgment: relevance, dependencies, honesty. This is the same fix your AtlasAI code review prescribed for the codebase: invariants belong to enforcement, not intention.

**Decision 2 — voice became a first-class output constraint.** Since Atlas speaks, the summary is now a TTS-ready `spoken_summary` with hard rules (≤2 sentences, no markdown, failures first) — and ambiguity handling changed: a voice OS that guesses wrong wastes a whole dispatch cycle, so the Supervisor asks one clarifying question when the WHAT is unclear. Your existing sentence-level parallel TTS pipeline plays these summaries as-is.

**Also fixed per the gap list:** per-subtask timeouts with a hard cap, daily token budget with hard stop + kill switch, idempotency keys stable across retries, `task.conflict` as a typed first-class event the dashboard can render, and the project/agent roster injected from memoryStore at runtime instead of hardcoded prose that rots.

**Open questions for you:**
1. The v1 prompt's roster (BCPR IL, BrainShop, PipeWatch, FinPulse, CodeLens) doesn't match Personal-Projects. What are the real v1 lanes — Evertec / AtlasAI / KleenBelly / personal? `{{active_projects}}` needs its first real value.
2. First worker to build? Recommendation: **calendar-agent** — read-only, free tier, instantly useful by voice, and proves the whole loop (voice → plan → dispatch → event → spoken reply) with zero destructive-action risk.
3. Does the existing AtlasAI backend become this runtime (fix the 4 Criticals first — the voice pipeline this depends on is currently unwired), or does the Supervisor start as a clean module inside the repo? Recommend: clean `supervisor/` module in the AtlasAI repo, reusing the voice adapters, not the tangled wiring.
