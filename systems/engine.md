---
type: system
tags: [os, system, engine]
---
# Engine Layer — Pluggable Headless Runtimes

The OS needs a process that can take a prompt and produce work. That process is the
**engine**. Claude Code is the **default adapter**, not the only one.

This note is the contract. The process multiplexer that implements it is the sibling
tool **[meta-cli](https://github.com/meta-agentic/meta-cli)** (`meta`). In-session multi-agent
coordination (swarms, memory, hooks) stays with Ruflo / the host engine — `meta` only
decides *which CLI process* runs.

## Principles

- **Engine is pluggable.** Skills and the dashboard trigger “run a prompt headless”;
  they do not hard-code a single binary forever. Claude remains the default.
- **Adapters, not forks.** Each provider is a thin adapter over an installed runtime —
  a **CLI** subprocess (`claude`, `gemini`, `grok`, optional `codex`, …) or that
  provider's **ACP** agent. No reimplementation of their agent loops inside meta-os.
- **Two lanes, one contract.** Every adapter can run via the **CLI lane** (spawn the
  provider CLI) or the **ACP lane** ([Agent Client Protocol](https://agentclientprotocol.com);
  a persistent JSON-RPC session over stdio). Same capability surface; the lane is a
  runtime choice (`engine: auto | cli | acp`), not a different adapter.
- **Interoperate, don't reinvent.** Speaking ACP makes a meta-os engine usable by any
  ACP host (Zed, Paperclip, …) and vice-versa — a standard surface instead of a
  meta-cli-only one. We borrow the *contract shape* from proven prior art; we do not
  rebuild anyone's orchestration/dashboard/budget plane (see *What does not belong here*).
- **Artifacts land in the vault.** Headless runs write a run directory; when used from
  an instance, collect into `memory/raw/` (then promote deliberately). The dashboard
  and skills read artifacts — they never own a parallel task store.
- **Fan-out is opt-in.** Default is one engine, one run. Fan-out is for diversity
  (review/debate), parallel research, or same-provider N workers on independent slices —
  not every task × N models.
- **Ruflo owns coordination inside a session.** `meta fan` does not replace swarm
  topology, SendMessage, or AgentDB. Use both when needed: `meta` to spawn providers,
  Ruflo skills to coordinate *within* Claude (or another host).

## Default vs. multi-engine

| Mode | Mechanism | Use when |
|------|-----------|----------|
| **Default** | `claude -p "<prompt>"` (or `meta run -p claude`) | Everyday work, skills, dashboard prompt console |
| **Single alternate** | `meta run -p gemini\|grok\|…` | Provider-specific strength, cost, or availability |
| **Cross-provider fan-out** | `meta fan -p claude,gemini,grok` | Independent opinions / research diversity |
| **Same-provider workers** | `meta fan -p claude --workers N` | Parallel independent slices (prefer worktrees for code) |
| **In-session swarm** | Ruflo / swarm skills | Coordinated multi-agent with shared memory |

Orthogonal to the mode is the **lane** (`--engine auto\|cli\|acp`): *how* each process is
run — a one-shot CLI subprocess or a warm ACP session. See *Execution lanes* below.

## Adapter contract

An adapter is identified by a stable provider id (`claude`, `gemini`, `grok`, `codex`, …)
and implements a **fixed capability set**. This is the surface every meta-cli engine
targets; the CLI and ACP lanes are two ways to satisfy `execute`, not two contracts.

**MUST** — required to be a usable engine:

| Capability | Contract |
|------------|----------|
| `execute` | Run one unit of work headless: prompt (+ optional session, cwd) in → stdout/stderr, exit code, and — when resumable — a session handle out. Backed by the CLI lane, the ACP lane, or both. |
| `testEnvironment` | Cheap readiness probe: is the runtime resolvable and runnable? Resolves the binary/agent on `PATH` (or configured path), reports version if cheap, and states which lanes are available. Drives `meta which` and `auto` lane selection. |
| `models` / `modelProfiles` | The model ids this engine can target, and any named profiles (e.g. default vs. deep). |
| `sessionCodec` | Serialize/deserialize a session handle so state survives across runs (see *Session persistence*). CLI-only engines may implement this as a resume-id pass-through; ACP engines carry real warm-session state. |
| `getConfigSchema` | Declare the adapter's own config knobs (binary path override, lane prefs, workspace strategy, confinement) so hosts can validate before running. |

**OPTIONAL** — implement when the runtime supports it; absence degrades gracefully:

| Capability | Notes |
|------------|-------|
| `getQuotaWindows` | Report remaining quota / rate-limit windows as a **probe** (see *Quota & budget*). Enforcement is a control-plane concern, not the adapter's. |
| `listSkills` / `syncSkills` | Enumerate / push skills the engine should have available. |
| Permission / yolo mode | Opt-in auto-approve flags; never default to full auto in docs. |
| Streaming | Incremental output for dashboard SSE; otherwise capture full stdout. |
| Usage JSONL | Tokens/cost if the engine logs them locally. |

### Known adapters (v0)

| Provider | CLI lane | ACP agent (lane) |
|----------|----------|------------------|
| `claude` | `claude -p "<prompt>"` | `claude-code-acp` (`META_CLAUDE_ACP`) — first ACP lane demonstrated end-to-end |
| `gemini` | `gemini -p "<prompt>"` | ACP agent when published (`META_GEMINI_ACP`) |
| `grok` | `grok -p "<prompt>"` (or `grok --single`) | — (CLI lane only for now) |
| `codex` | `codex exec "<prompt>"` (stub until verified) | — |

Exact flags and ACP agent commands live in meta-cli; this table is the OS-facing
vocabulary. An engine with no ACP agent simply has one lane — `auto` resolves to CLI.

## Execution lanes — CLI and ACP

Every run picks a lane via `--engine` (default `auto`):

| Lane | Mechanism | Session |
|------|-----------|---------|
| `cli` | Spawn the provider CLI as a subprocess (today's behaviour). | Cold per run; resume only if the CLI itself supports a resume id. |
| `acp` | Speak the [Agent Client Protocol](https://agentclientprotocol.com) to the provider's ACP agent over stdio (JSON-RPC): `initialize → session/new` (or `session/load`) `→ session/prompt`, stream `session/update`. | Warm, persistent: `mode: persistent`, an optional `stateDir`, and `warmHandleIdleMs` keep the agent alive between ticks; state travels via `sessionCodec`. |
| `auto` | Pick ACP when its prerequisites pass (`testEnvironment`), else fall back to CLI **with a recorded diagnostic**. | Whatever the chosen lane provides. |

**Selection semantics (mirror across meta-cli and any host):**

- `auto` — prefer ACP; on any failed prerequisite, silently fall back to CLI but record
  `engine: cli` and a `lane_fallback` reason in `meta.json`. Never fail because ACP is
  merely absent.
- `acp` (explicit) — **fail loudly** if prerequisites are missing; do not silently
  downgrade. The operator asked for warm sessions on purpose.
- `cli` (explicit) — always the subprocess lane, even where ACP is available.

**Prerequisites for the ACP lane** (checked by `testEnvironment`):

1. **Node ≥ 22.12** on `PATH` (the ACP agent packages target it).
2. The provider's **ACP agent command** resolvable — e.g. `claude-code-acp` for `claude`,
   overridable via `META_<PROVIDER>_ACP`. Absent → that engine is CLI-only under `auto`.

## Session persistence

The ACP lane's value is not the protocol, it is **state that survives across runs** — no
cold subprocess per tick. meta-os makes that state **first-class OS memory** rather than
opaque adapter storage:

- The adapter's `sessionCodec` serializes the session handle. The ACP lane writes it under
  the run's `state/` dir (or a configured `stateDir`) so the next run can `session/load`.
- On **collect**, the resolved session summary lands in `memory/raw/` alongside the run
  capture — the same `raw → wiki → output` pipeline as any other capture. Cross-tick
  memory is the framework's differentiator; the adapter stores only the resume handle, the
  vault stores the knowledge.
- Promotion to `wiki/` stays deliberate. Nothing auto-promotes from a warm session.

## Quota & budget

Adapters MAY expose `getQuotaWindows` — a **probe** reporting remaining quota / rate-limit
windows. That is the entire engine-layer responsibility.

**Enforcement is not here.** Hard-stops, auto-pause, and per-project budgets are a
**control-plane** concern — the interface layer / automations read the probe and decide.
`engine.md` documents the probe surface so the control plane has something to read; it does
not implement budgets. (This is the deliberate line between borrowing Paperclip's *contract
shape* and rebuilding its governance app — see *What does not belong here*.)

## Workspace & confinement

An adapter's `getConfigSchema` MAY declare, and a host MAY set:

- `workspaceStrategy: { type: "git_worktree", baseRef?, branchTemplate? }` — meta-os's
  existing isolation model for parallel code workers ([[systems/swarm-harness]]); the ACP
  lane inherits it unchanged.
- Optional **fs/network confinement** (`filesystemScope`, `networkScope` / allowlist).
  meta-os documents these as adapter config it can pass through; it does not ship a sandbox
  runtime. Enable per host/OS where available.

## Run artifact layout

One run id, one directory (default under `META_RUNS_DIR` or `./.meta-runs/<run-id>/`):

```text
<run-id>/
├── run.json          # schema_version, prompt hash, providers, started_at, status
├── prompt.txt        # exact prompt sent
└── <provider>[@n]/   # e.g. claude, gemini, claude@1
    ├── meta.json     # cmd, exit_code, started_at, ended_at, duration_ms,
    │                 #   engine (cli|acp), lane_fallback?, session_id?
    ├── stdout.txt
    ├── stderr.txt
    └── state/        # ACP lane only: sessionCodec output for session/load next run
```

`run.json` status: `running` | `ok` | `partial` | `failed`. Fan-out is `partial` if any
worker fails and at least one succeeds. `meta.json.engine` records the lane actually used
(after any `auto` fallback); `session_id` is present when the lane produced a resumable
handle.

## Collect → memory

From an instance vault root:

1. `meta collect --run-id <id>` (or the multi-engine skill) reads the run dir.
2. Writes one capture note (or one note per provider) into `memory/raw/` with
   front-matter: `type`, `tags`, `engine` (lane), `run_id`, `providers`, `session_id?`,
   `ts`. A `session_id` is the resume handle for the next warm run.
3. Promotion to `wiki/` is still deliberate — same discipline as every other raw capture.

See [[skills/multi-engine/SKILL|multi-engine]].

## Interface layer impact

The dashboard trigger surface stays **one mechanism**: headless engine run + stream.
The implementation becomes:

```text
meta run --engine <auto|cli|acp> -p <default|configured> -- "<prompt>"
```

instead of a permanent hard-code of only `claude -p`. Claude remains the default
provider in config, `auto` the default lane. A warm ACP run is still just a run whose
result lands in the vault. See [[systems/interface-layer]].

## What does *not* belong here

| Concern | Belongs in |
|---------|------------|
| Shell aliases `mrun` / `mfan` | zsh-suite (thin wrappers only) |
| Swarm topology, memory_search, hooks | Ruflo / host engine |
| Domain process (Scrum, pack skills) | packs + skills |
| Dashboard UI | meta-os-dashboard |
| Budget **enforcement** / hard-stops / auto-pause | interface layer / automations (engine only *probes* quota) |
| Orchestration / governance / multi-tenant "company" plane | out of scope — we borrow the contract shape, not the app |
| ACP JSON-RPC client & agent packages | meta-cli (implementation) + the provider's ACP agent |

## Prior art & provenance

The two-lane contract, the fixed capability set (`execute` / `testEnvironment` /
`models` / `sessionCodec` / `getConfigSchema` / `getQuotaWindows`), and the
`workspaceStrategy` / confinement config are **shaped after** the MIT-licensed
[Paperclip](https://github.com/paperclipai/paperclip) adapter registry and the
[Agent Client Protocol](https://agentclientprotocol.com) — concept attribution, not
copied code. meta-os keeps its own differentiators (skill backbone, `raw → wiki → output`
memory as the session state store, packs, provenance) and deliberately does **not** adopt
Paperclip's orchestration/dashboard/budget-enforcement plane.
