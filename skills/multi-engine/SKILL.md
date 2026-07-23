---
name: multi-engine
description: "Fan-out headless agent runs across claude/gemini/grok (and other adapters) via meta-cli, then collect results into memory/raw. Use for cross-provider review/diversity, parallel research, or same-provider worker batches — not for every task. The standing multi-provider surface."
---

# Multi-Engine

Cross-provider (and multi-worker) headless runs using **[meta-cli](https://github.com/meta-agentic/meta-cli)** (`meta`). Implements the contract in [[systems/engine]].

**Scope:** process fan-out only. In-session swarms, shared AgentDB memory, and SendMessage coordination stay with Ruflo / the host engine — see [[skills/swarm-orchestration/SKILL|swarm-orchestration]].

**Two lanes.** Each run picks *how* the engine process runs, via `--engine`:

| `--engine` | Lane | Session |
|------------|------|---------|
| `cli` | Spawn the provider CLI (default behaviour) | Cold per run |
| `acp` | [Agent Client Protocol](https://agentclientprotocol.com) agent over stdio | **Warm, persistent** — state resumes across runs |
| `auto` *(default)* | ACP if its prerequisites pass, else CLI with a recorded diagnostic | Whichever lane ran |

The lane is orthogonal to fan-out — `meta fan --engine acp` warm-fans, `meta run --engine cli` is a one-shot. The full contract (capability set, selection semantics, prerequisites) is [[systems/engine]].

## When to use

| Use multi-engine | Do not |
|------------------|--------|
| Independent reviews of the same change (Claude + Gemini + Grok) | Default everyday coding (use one engine) |
| Parallel research / brainstorm with different priors | One feature rewritten by N models into the same tree |
| Same-provider N workers on **independent** slices | Anything that needs shared memory mid-flight without a collect step |

## Prerequisites

1. `meta` on `PATH` (`ln -sf <repo>/bin/meta ~/.local/bin/meta`)
2. At least one adapter binary installed (`claude`, `gemini`, `grok`, …)
3. For vault collect: run from the **instance** root (or pass an absolute `--to`)
4. For the **ACP lane** only: Node ≥ 22.12 and the provider's ACP agent command
   (`claude-code-acp` for claude, override with `META_<PROVIDER>_ACP`). Absent → `auto`
   uses CLI; explicit `--engine acp` fails loudly.

```bash
meta which   # shows each provider's CLI status and whether its ACP lane is available
```

## Workflow

### 1. Single provider

```bash
meta run -p claude -C . -- "Summarize the risk of this PR's auth changes"
```

### 2. Cross-provider fan-out

```bash
meta fan -p claude,gemini,grok -C . -- \
  "Review security of the auth module. List findings with severity."
```

### 3. Same-provider workers

```bash
meta fan -p claude --workers 3 -C . -- \
  "Worker: pick a distinct subsystem and list top risks. Do not edit files."
```

Prefer **worktree isolation** for code-writing workers (engine `--worktree` or [[systems/swarm-harness]]).

### 3b. Warm ACP session (persistent lane)

```bash
# auto: uses ACP when Node ≥ 22.12 + the agent are present, else CLI (recorded)
meta run --engine auto -p claude -C . -- "Start the audit; keep the session warm."

# explicit ACP; fails loudly if prerequisites are missing
meta run --engine acp  -p claude -C . -- "Continue where the last run left off."
```

The ACP lane keeps the agent warm and serializes the session under the run's `state/`.
On collect, the session summary and its `session_id` land in `memory/raw/` — cross-tick
state becomes OS memory, not opaque adapter storage (the memory-as-state-store model in
[[systems/engine]]). The next run resumes from that handle.

### 4. Dry-run (plan only)

```bash
meta fan -p claude,gemini --dry-run -- "…"
```

### 5. Collect → `memory/raw/`

From the instance vault root (or any path where `memory/raw` exists):

```bash
# run prints the run directory; collect by id or dir
meta collect --run-id <id> --to memory/raw
# or
meta collect --dir .meta-runs/<id> --to memory/raw
```

This writes `memory/raw/meta-run-<id>.md` with front-matter (`run_id`, `providers`, `status`, `ts`). **Do not cite raw** — promote deliberately to `wiki/` when the synthesis is durable ([[systems/memory-layer]]).

### 6. Promote (human / follow-up skill)

1. Read the raw capture.
2. Merge agreements, call out disagreements, drop noise.
3. Write a cleaned note under `memory/wiki/` with links to projects/systems.
4. Leave the raw file as the audit trail.

## Agent instructions

When the user asks to “run this on claude and gemini” or “fan out to all engines”:

1. Confirm intent is diversity/parallel research, not silent triple spend on one edit.
2. Prefer `meta fan` with an explicit provider list.
3. Use `--dry-run` first if the prompt is large or providers are uncertain.
4. After completion, `meta collect --to memory/raw` when working inside an instance.
5. Summarize differences between providers in the chat; do not paste entire stdout dumps unless asked.
6. Never enable `--yolo` unless the user explicitly wants auto-approve and understands the risk.
7. Leave `--engine auto` unless the user wants a specific lane. Reach for `--engine acp`
   only when a run should resume warm state from a prior run; use `--engine cli` to force
   the subprocess lane. Explicit `acp` fails loudly if prerequisites are absent — that is
   intended, not a bug to work around.

## Artifacts

See [[systems/engine]] for `run.json` / per-slot `meta.json` layout. Default run parent: `./.meta-runs` or `$META_RUNS_DIR`.
