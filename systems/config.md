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
| **Instance estate** | `meta-os.config.json` (at the instance root, beside `CLAUDE.md`/`_index.md`) | Estate knowledge: `memory` topology, `backlogs[]`, estate `vars`. | the adopter · **private** |
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
  "vars": { "code": "…" },                         // reusable ${} prefixes
  "backlogs": [ { "space": "…", "path": "…" } ],   // backlog mirrors (per-item dir or legacy json)
  "memory": {                                       // configurable topology (omit → default)
    "roots": [                                      // canon: counted as the pipeline
      { "label": "instance", "path": "…/memory", "layout": "flat" },
      { "label": "estate",   "path": "…/vault",  "layout": "project/tier" }
    ],
    "federated": [ { "label": "docs-repo", "path": "…" } ]  // navigation only, never canon
  }
}
```

- **`vars`** — `${name}` expands in any config value (and in `projects/*.md` `path:`), so a
  repo-root move is a one-line change.
- **`backlogs[]`** — the backlog mirrors this instance tracks; `path` resolves to a per-item
  `raw/` directory or a legacy `backlog.json`.
- **`memory`** — the topology contract from [[systems/memory-layer]]: `roots` are **canon**
  (each with a `layout`), `federated` mounts are **navigation** context. Omit the block and
  memory falls back to the instance's own `memory/{raw,wiki,output}` as the sole canon root
  plus `vaults/*` as federated mounts — byte-for-byte the prior behaviour.

## Defaults & degradation

- **No `meta-os.config.json`** → default topology (in-instance `memory/` + `vaults/*`), no
  backlogs, no vars. No adopter is broken by upgrading.
- **`${var}` expansion** works in every path, exactly as it does for `backlogs`.
- **A broken/dangling root or federated path** is skipped and reported, never fatal.

## Back-compat

An existing single `instance.config.json` that still carries estate keys keeps working — the
reader accepts estate config from either file, **preferring `meta-os.config.json` when
present**. The migration is simply: move `vars` / `backlogs` / `memory` out of
`instance.config.json` into `meta-os.config.json`, and leave the deployment keys behind.

See [[systems/memory-layer]] for the topology semantics and [[systems/distribution]] for how
an instance mounts the framework.
