---
type: system
tags: [os, system, config]
---
# Config — three levels, one namespace

The engine, the memory topology, and the backlog mirrors all need configuration. meta-os
splits that into **three levels**, each owned by a different party and carrying only what it
legitimately should. All meta-os config artifacts share the **`meta-os.` namespace** so they
are unmistakable wherever they sit.

## The three levels

| Level | File | Holds | Owner · visibility |
|-------|------|-------|--------------------|
| **Framework** | [`systems/meta-os.config.schema.json`](meta-os.config.schema.json) (+ this doc) | Valid keys, valid enum values (e.g. `layout ∈ flat \| tier/project \| project/tier`), defaults, fallback behaviour. **Zero values.** | meta-os · **public** |
| **Instance estate** | `meta-os.config.json` (at the repository root, beside `_index.md`; instantiated from `instance-template/root/` on first run) | Estate knowledge: `memory` topology, `backlogs[]`, estate `vars` — plus the `instance` record `scripts/bootstrap.sh` writes (name, date, template ref). | the adopter · **private** |
| **Deployment** | `instance.config.json` (the dashboard) | Bootstrap pointer (`instanceRoot`/`frameworkRoot`/`github.*`), `auth`, `corsOrigins`, `claudeHome`, `dataDir`. | per-deploy · **secret** |

**Why the split.** A framework-level concept like the memory topology must be readable
*without the dashboard installed* — so estate knowledge lives with the estate
(`meta-os.config.json`), not inside a deployment's config. The **bootstrap pointer stays with
the deployment**: it is what tells the server *where the instance is*, so it cannot itself
live in the instance it would have to point to.

**Why `instance.config.json` keeps its name.** It points *to* an instance — the name is
defensible there — and renaming it would break existing deployments. Estate knowledge simply
moves *out* of it into `meta-os.config.json`.

## The estate config — `meta-os.config.json`

Validated by [`meta-os.config.schema.json`](meta-os.config.schema.json). Every key is
optional; the file may be omitted entirely (defaults apply). Shape:

```jsonc
{
  "instance": { "name": "…", "bootstrapped": "YYYY-MM-DD", "template": "<sha>" },  // written at bootstrap
  "vars": { "code": "…" },                         // reusable ${} prefixes
  "backlogs": [ { "space": "…", "path": "…" } ],   // backlog mirrors (per-item dir or legacy json)
  "memory": {                                       // configurable topology (omit → default)
    "roots": [                                      // canon: counted as the pipeline
      { "label": "instance", "path": "…/memory", "layout": "flat" },
      { "label": "estate",   "path": "…/vault",  "layout": "project/tier" }
    ],
    "federated": [ { "label": "docs-repo", "path": "…" } ]  // navigation only, never canon
  },
  "swarm": { "lanes": 3, "record_repository": { "url": "…", "path": "…" } }  // the autonomous pipeline
}
```

- **`instance`** — the instantiation record: `name`, the `bootstrapped` date, and the
  `template` ref (the framework commit whose `instance-template/` was copied in).
  `scripts/upgrade.sh` diffs the template from that ref to report what changed since;
  `--ack-template` moves it forward once the diff has been reviewed. The one key the
  framework writes rather than the adopter; see [[systems/distribution]].
- **`vars`** — `${name}` expands in any config value (and in `projects/*.md` `path:`), so a
  repo-root move is a one-line change.
- **`backlogs[]`** — the backlog mirrors this instance tracks; `path` resolves to a per-item
  `raw/` directory or a legacy `backlog.json`.
- **`memory`** — the topology contract from [[systems/memory-layer]]: `roots` are **canon**
  (each with a `layout`), `federated` mounts are **navigation** context. Omit the block and
  memory falls back to the instance's own `memory/{raw,wiki,output}` as the sole canon root
  plus `vaults/*` as federated mounts — byte-for-byte the prior behaviour.

- **`swarm`** — the autonomous pipeline's bounds, quiet timers and identities ([[systems/pipeline]]). The loop reads them and never writes them; the pipeline's own configuration file keeps the lane prompt and the routing of items to repositories. Every key is optional:

| Key | Meaning | Default |
|---|---|---|
| `lanes` | `m_max`, the lane slots | 5 (the sizing); 3 for a proof of concept |
| `min_lanes` | `m_min`, the fewest working lanes the regulator keeps while the pipe runs | 1 |
| `tokens` | `N`, the CONWIP cap, set by a human from the sizing | `2 × lanes` |
| `fairness_share` | the largest share of the tokens one space may hold | 0.5 |
| `automerge_classes` | change classes that merge without the human station | `[]` |
| `review_sla_days` | a space whose oldest item in review is older takes no new work | 5 |
| `review_queue_cap` | the most items one space may hold in review before it takes no new work | 4 |
| `lane_budget` | a run's cap as a multiple of its expected cost | 3 |
| `max_retries` | give-backs before an item is no longer admissible | 2 |
| `reserves.five_hour`, `reserves.week` | the share of each window's allowance never spent | 0.15, 0.10 |
| `mileage_readings` | the span, in budget readings, of the per-window mileage average | 6 |
| `stall_minutes` | the quiet timer: a step with no progress (no exit, its log unchanged) for this long is killed and reaped; also the sentinel's limit for an unconsumed event | 5 |
| `max_stale_reaps` | reaps of one item before it is held for a human | 2 |
| `unattended_after_minutes` | a question to the human unanswered this long switches the pipe to unattended | 30 |
| `remote_poll_seconds` | the remote watcher's interval, the one poll; it only writes events | 60 |
| `build_slots` | full builds the runner runs at once on one machine | 1 |
| `executable_spaces` | the spaces whose items the pipeline may start | `[]` (none) |
| `record_repository.url`, `.path` | the private repository the loop writes, and its local clone ([[pipeline/record]]) | none: the record stays in the plain directory `tick.py --state` names |
| `planner.adapter` | `command` or `reasoning` | `reasoning` |
| `planner.command` | the planner command and its arguments | none |
| `planner.repair_max_items`, `.churn_cap` | repair when a change touches at most this many items or one lane; solve cold past this edit distance | 5, 10 |
| `planner.repair_timeout_seconds`, `.cold_timeout_seconds` | time allowed before the pass plans by reasoning | 30, 90 |
| `dashboard_controls` | the Pipeline tab's controls on a local-source dashboard; never on a hosted one | `false` |
| `visibility_probe` | probe each run's repository through `scripts/public_repo_gate.py` | `false` |

## Defaults & degradation

- **No `meta-os.config.json`** → default topology (in-instance `memory/` + `vaults/*`), no
  backlogs, no vars. No adopter is broken by upgrading.
- **`${var}` expansion** works in every path, exactly as it does for `backlogs`.
- **A broken/dangling root or federated path** is skipped and reported, never fatal.

## Precedence — worked example

Lower levels set defaults; higher levels override. **Framework < instance < deployment.**

1. **Framework** ships no memory topology at all — the *documented default* (no
   `meta-os.config.json`, or a `meta-os.config.json` with no `memory` block) is: the
   instance's own `memory/{raw,wiki,output}` as the sole canon root, `vaults/*` as
   federated mounts.
2. **Instance** (`meta-os.config.json`) overrides that default by declaring a second
   canon root — e.g. a shared per-project vault repo with `layout: "project/tier"` —
   because this adopter's backlog lives outside the instance's own `memory/` folder.
   This is estate knowledge: it belongs to the adopter, not to any one machine.
3. **Deployment** (`instance.config.json`) overrides a *path*, never the topology
   shape — e.g. a second machine checks out the estate at a different filesystem root,
   so its `instance.config.json` repoints `instanceRoot`/`frameworkRoot` without
   touching the instance's `meta-os.config.json` at all. *Which* roots exist and *what*
   they mean travels with the instance; *where they sit on disk* is a deployment
   concern.

Net effect: an adopter with one estate and N deployments (laptop, server, CI) declares
the topology once, in the instance, and each deployment only ever overrides paths.

## Back-compat

An existing single `instance.config.json` that still carries estate keys keeps working — the
reader accepts estate config from either file, **preferring `meta-os.config.json` when
present**. The migration is simply: move `vars` / `backlogs` / `memory` out of
`instance.config.json` into `meta-os.config.json`, and leave the deployment keys behind.

See [[systems/memory-layer]] for the topology semantics and [[systems/distribution]] for how
an instance holds the framework's paths in its own repository.
