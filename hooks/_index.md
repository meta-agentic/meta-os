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
