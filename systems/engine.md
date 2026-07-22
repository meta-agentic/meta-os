---
type: system
tags: [os, system, engine]
---
# Engine Layer — Pluggable Headless Runtimes

The OS needs a process that can take a prompt and produce work. That process is the
**engine**. Claude Code is the **default adapter**, not the only one.

This note is the contract. The process multiplexer that implements it is the sibling
tool **[meta-cli](https://github.com/meta-aos/meta-cli)** (`meta`). In-session multi-agent
coordination (swarms, memory, hooks) stays with Ruflo / the host engine — `meta` only
decides *which CLI process* runs.

## Principles

- **Engine is pluggable.** Skills and the dashboard trigger “run a prompt headless”;
  they do not hard-code a single binary forever. Claude remains the default.
- **Adapters, not forks.** Each provider is a thin adapter over an installed CLI
  (`claude`, `gemini`, `grok`, optional `codex`, …). No reimplementation of their
  agent loops inside meta-os.
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

## Adapter contract

Every adapter MUST support:

| Capability | Contract |
|------------|----------|
| **Detect** | Resolve binary on `PATH` (or configured path); report version if cheap |
| **Headless run** | Non-interactive: prompt in → stdout/stderr + exit code out |
| **Working directory** | Optional `cwd` for the child process |
| **Timeout** | Parent may kill after N seconds; record as failure |
| **Identity** | Stable provider id: `claude`, `gemini`, `grok`, `codex`, … |

Nice-to-have (not required for v0):

| Capability | Notes |
|------------|-------|
| Session / resume id | Pass-through when the CLI supports it |
| Permission / yolo mode | Opt-in flags; never default to full auto in docs |
| Streaming | For dashboard SSE later; v0 may capture full stdout |
| Usage JSONL | Tokens/cost if the engine logs them locally |

### Known adapters (v0)

| Provider | Binary | Headless shape (illustrative) |
|----------|--------|-------------------------------|
| `claude` | `claude` | `claude -p "<prompt>"` |
| `gemini` | `gemini` | `gemini -p "<prompt>"` |
| `grok` | `grok` | `grok -p "<prompt>"` (or `grok --single`) |
| `codex` | `codex` | Adapter stub until installed/verified |

Exact flags live in meta-cli; this table is the OS-facing vocabulary.

## Run artifact layout

One run id, one directory (default under `META_RUNS_DIR` or `./.meta-runs/<run-id>/`):

```text
<run-id>/
├── run.json          # schema_version, prompt hash, providers, started_at, status
├── prompt.txt        # exact prompt sent
└── <provider>[@n]/   # e.g. claude, gemini, claude@1
    ├── meta.json     # cmd, exit_code, started_at, ended_at, duration_ms
    ├── stdout.txt
    └── stderr.txt
```

`run.json` status: `running` | `ok` | `partial` | `failed`. Fan-out is `partial` if any
worker fails and at least one succeeds.

## Collect → memory

From an instance vault root:

1. `meta collect --run-id <id>` (or the multi-engine skill) reads the run dir.
2. Writes one capture note (or one note per provider) into `memory/raw/` with
   front-matter: `type`, `tags`, `engine`, `run_id`, `providers`, `ts`.
3. Promotion to `wiki/` is still deliberate — same discipline as every other raw capture.

See [[skills/multi-engine/SKILL|multi-engine]].

## Interface layer impact

The dashboard trigger surface stays **one mechanism**: headless engine run + stream.
The implementation becomes:

```text
meta run -p <default|configured> -- "<prompt>"
```

instead of a permanent hard-code of only `claude -p`. Claude remains the default
provider in config. See [[systems/interface-layer]].

## What does *not* belong here

| Concern | Belongs in |
|---------|------------|
| Shell aliases `mrun` / `mfan` | zsh-suite (thin wrappers only) |
| Swarm topology, memory_search, hooks | Ruflo / host engine |
| Domain process (Scrum, pack skills) | packs + skills |
| Dashboard UI | meta-os-dashboard |
