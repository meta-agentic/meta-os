---
type: index
tags: [os, hooks, layer1]
---
# Hooks

Event-triggered scripts the **harness** executes — not the agent. That is the whole
point of the layer: a hook fires whether or not the agent remembers to.

A skill is invoked on demand; a hook runs itself. Both are Layer 1
([[skills/_index|skills/]] is the on-demand half), and the same authoring bar applies:
if you rely on the agent remembering it more than once, it should stop being a habit and
become a mechanism.

| Hook | Event | What it does |
|------|-------|--------------|
| `pre-commit-fetch.sh` | `PreToolUse` · `Bash` | Before any commit, fetch every tracked repo's default branch and name the checkouts that are behind. Reports; never blocks. |
| `error-handler.sh` | *(called by hooks)* | Observability sink — counters, gauges and an event log. Not a hook itself; hooks invoke it. |

## Staged, never auto-wired

**A hook is executable code, so enabling one is an explicit, per-hook user decision —
always.** The framework *ships* hooks; it does not switch them on. This is the same rule
[[systems/packs]] states for pack hooks (staged at `.claude/hooks/<pack>/`, never written
into `settings.json`), and the framework holds itself to it rather than making an
exception for its own.

"Ships by default" and "runs by default" are different claims. Only the first is true
here.

## Enabling one

Copy the script somewhere stable and reference it from `settings.json`. User settings
(`~/.claude/settings.json`) apply to **every** project, which is what a cross-repo hook
needs — a per-project `.claude/settings.json` would have to be copied into each repo and
would still miss the next one added.

```bash
cp hooks/pre-commit-fetch.sh ~/.claude/pre-commit-fetch.sh
chmod +x ~/.claude/pre-commit-fetch.sh
```

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/pre-commit-fetch.sh",
            "timeout": 60,
            "statusMessage": "Fetching repos before commit"
          }
        ]
      }
    ]
  }
}
```

Hook arrays **merge** across settings sources — adding this does not displace hooks
already configured elsewhere. Open `/hooks` once afterwards, or restart, so the settings
watcher picks the file up.

---

## `pre-commit-fetch.sh`

### The failure it prevents

An agent working across several repos accumulates stale checkouts without noticing.
Committing into one is usually harmless. **Deriving a figure from one is not.**

A count, a total, or a status roll-up computed over a tree that is missing commits is
arithmetically correct and factually wrong — and it is *indistinguishable* from a correct
one. Nothing downstream catches it, because the reasoning over the visible data is sound.
The data was the problem.

That is why the mitigation cannot be analytical. No amount of care while reading the
wrong tree produces the right answer. It has to be mechanical: **fetch before you
compute.**

### Behaviour

Runs on every `Bash` call and exits immediately unless the command actually commits. Then
it fetches the default branch of every git repo directly under the repos root, in
parallel, and reports only the ones that are behind. **Silence means everything is
current.**

It never blocks. Being behind is often fine; being behind *silently* is not.

### Configuration

| Variable | Default | Meaning |
|---|---|---|
| `METAOS_REPOS_ROOT` | probed | Directory holding the repo checkouts |
| `METAOS_PREFETCH_TTL` | `90` | Seconds before a repo is re-fetched |
| `METAOS_PREFETCH_OFF` | unset | Set to `1` to disable entirely |

**The root is probed, never assumed.** It tries `METAOS_REPOS_ROOT`, the parent of
`CLAUDE_PROJECT_DIR`, the parent of the payload `cwd`, the parent of `$PWD`, then `$HOME`
— taking the first that actually contains `*/.git`. `$HOME` is deliberately last:
containers and CI images routinely run as a user whose `$HOME` is nowhere near the
checkouts, and a `$HOME` default then scans an empty directory and reports nothing, which
reads exactly like "everything is current". Requiring evidence before accepting a
candidate is what stops the hook from failing in the shape it exists to prevent.

### Matching

`git` must sit in **command position** — start of a line, or after `;` `&&` `||` `|` `&`
`(` `{` — with an optional wrapper word (`sudo`, `env`, `time`, `nice`, `xargs`).

| Fires | Silent |
|---|---|
| `git commit -m x` | `git log` · `git status` · `git diff` |
| `git -C <dir> commit -m x` | `echo git commit is a phrase in prose` |
| `git add . && git commit -q` | `grep -rn "git commit" docs/` |
| `cd <dir>; git commit --amend` | a heredoc body quoting the phrase |
| `git add a b && git commit -F - <<EOF …` | |

The matcher is **deliberately biased toward firing**: a false positive costs one fetch, a
false negative costs a commit made against a stale tree.

### Cost

Measured over 13 repos: **6.6 s cold, 0.08 s warm.** The per-repo TTL means a run of
commits in one turn pays the fetch once. A repo whose fetch *fails* is reported as
`FETCH-FAILED` rather than skipped — offline is *unknown*, not *current*.

### Requirements

`bash`, `git`, `jq`. Without `jq` the hook exits silently rather than guessing at the
payload.

---

## `error-handler.sh` — the observability sink

Hooks are the one part of the OS that runs with nobody watching. They fire inside someone
else's tool call, their output is consumed by a machine, and **a hook that quietly stops
working looks exactly like a hook with nothing to say.** This sink makes the difference
visible.

It is not a hook. Hooks call it.

### Two rules, both absolute

1. **Never write to stdout.** A `PreToolUse` hook's stdout is parsed as JSON by the
   harness. One stray byte from the sink corrupts its caller's contract and turns an
   observability tool into an outage. Diagnostics go to stderr; data goes to files.
2. **Never fail the caller.** It exits `0` unconditionally. A telemetry sink that can break
   the thing it measures is worse than no telemetry — it adds a failure mode to a path that
   previously had none.

Callers hold up their half too: the invocation is `|| true` and its stdout is redirected to
`/dev/null` at every call site. The sink promises not to write there; the caller does not
rely on the promise.

### Usage

```
error-handler.sh --hook NAME --event KIND [--code N] [--line N] [--cmd STR] [--detail STR]
                 [--counter NAME[=N]]... [--gauge NAME=VALUE]...
```

Series names are namespaced by the calling hook, so two hooks cannot silently share a
series and average each other's behaviour away.

### Wiring it into a hook

```bash
set -Euo pipefail            # -E so the trap is inherited by functions and subshells

HOOK_NAME="my-hook"
_OBS_SH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/error-handler.sh"
obs() { [ -x "$_OBS_SH" ] || return 0
        "$_OBS_SH" --hook "$HOOK_NAME" "$@" >/dev/null 2>&1 || true; return 0; }

on_err() { obs --event error --code "$1" --line "$2" --cmd "$3" \
               --counter errors --counter "error_line_${2}"; }
trap 'on_err "$?" "$LINENO" "$BASH_COMMAND"' ERR
```

### The error channel must be silent when nothing is wrong

This is the design constraint that costs the most to honour, and the one worth stating.

`ERR` fires on any unguarded non-zero. Shell semantics exempt guarded failures — `cmd ||
fallback`, `[ … ] && …`, anything inside a conditional — so an `ERR` event means genuinely
unexpected **only if every expected non-zero in the script is explicitly guarded.**

The first version of this instrumentation was not, and a healthy run logged **25 errors**:
`ref=$(git symbolic-ref …)` returns non-zero whenever a clone has no `origin/HEAD`, which is
both common and fully handled. A channel that fires two dozen times on the happy path is
alarm fatigue, and alarm fatigue is how the one real error goes unread. Guarding those paths
took the count to zero.

The same bug bit the sink itself: `pipefail` turned a benign "key not yet present" read into
a failure, the `ERR` net swallowed it, and the result was an event log that worked while no
counter was ever written. **`pipefail` is deliberately not set** in `error-handler.sh`, and
the `ERR` trap there is a net, not control flow.

If you add a hook and its error counter climbs on healthy runs, the hook is wrong, not the
sink.

### Storage

`$METAOS_OBS_DIR`, defaulting to `$XDG_STATE_HOME/meta-os` (or `~/.local/state/meta-os`) —
never inside a repo, so telemetry cannot be committed.

| File | Shape |
|---|---|
| `events.ndjson` | one JSON object per event; rotated at `METAOS_OBS_MAX_BYTES` (1 MiB) |
| `counters.tsv` | `name <TAB> value` — monotonic, incremented under a lock |
| `gauges.tsv` | `name <TAB> value <TAB> epoch` — last write wins |

Counters are read-modify-write, and hooks run in parallel — this one is invoked from inside
a parallel fetch loop — so an unlocked increment loses counts exactly when the system is
busiest. `flock` where available, a bounded `mkdir` spin otherwise (macOS ships no
`flock`); if the lock cannot be taken the write is skipped rather than raced.

Gauges hold numbers you can chart. Paths and free text belong on the event as `--detail`.

### What `pre-commit-fetch` records

| Counter | Gauge |
|---|---|
| `invocations`, `not_a_commit`, `commits_intercepted` | `repos_scanned` |
| `runs_clean`, `runs_reported` | `repos_behind` |
| `repos_behind_total`, `fetch_failures_total` | `repos_unreachable` |
| `errors`, `error_line_<n>`, `no_root`, `skipped_disabled` | `duration_s` |

`runs_clean` matters as much as `runs_reported`: **the all-clear is a measurement too.**
Recording only the bad case would leave a hook that scans nothing indistinguishable from one
that scans everything and finds it healthy — precisely the ambiguity these hooks exist to
remove.

### Env

`METAOS_OBS_OFF=1` disables the sink; `METAOS_OBS_DEBUG=1` reports its own failures on
stderr; `METAOS_OBS_DIR` and `METAOS_OBS_MAX_BYTES` relocate and resize the store.
