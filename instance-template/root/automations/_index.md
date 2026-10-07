---
type: index
tags: [os, automations, layer1]
---
# Automations

The scheduled / triggered half of Layer 1. A skill is invoked on demand; an automation
runs itself — on a **schedule** (cron / launchd / cloud routine) or on an **event** (git
hook, session start, file change).

| Automation | Trigger | Cadence | Runs | Status |
|------------|---------|---------|------|--------|
| Framework upgrade check | schedule (weekly) | @weekly | `scripts/upgrade.sh --check` — reports how far behind the framework's `main` this instance is, changes nothing | candidate |
| Pre-commit fetch | event (before any commit) | — | [[hooks/_index\|hooks/]] `pre-commit-fetch.sh` — names the checkouts that are behind before a figure is derived from them; enable per the hooks index, never auto-wired | candidate |
| Graph refresh | file change / pre-sprint | — | [[skills/graphify/SKILL\|graphify]] `--update` / `--watch` | candidate |
| Daily standup / retro | schedule (daily) | @daily | the agile pack's `agile-process` cadence — mount it first (`scripts/packs.sh add agile`) | candidate |
| OS heartbeat | schedule (daily) | @daily | [meta-os-dashboard](https://github.com/meta-agentic/meta-os-dashboard) `scripts/heartbeat.mjs` — lint + stale-raw + never-run checks → files a [[templates/heartbeat\|heartbeat]] note to `memory/raw/` | candidate |

Executions append one JSON line to `automations/runs.jsonl`
(`{"automation": "<table name>", "ts": "<ISO-8601>", "outcome": "ok|fail", "note": "…"}`);
the [meta-os-dashboard](https://github.com/meta-agentic/meta-os-dashboard) derives last-run from
it (see [[systems/ontology.yaml|ontology.yaml]]'s `automations:` contract). The log is
machine-local and gitignored.

## Two kinds

- **Local** — cron / git hooks / Claude Code hooks on this machine. Configure in the
  relevant repo's `.claude/settings.json` or `.githooks/`, or a `launchd` plist.
- **Remote** — cloud scheduler routines (survive machine sleep).

## Classifying a workflow

When you codify a skill, decide: on-demand (stays a skill) or scheduled/triggered (also
gets an automation row here). Record the trigger, cadence, what it runs, and its status.
