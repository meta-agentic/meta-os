---
name: "Bootstrap Instance"
description: "Interactive first-run setup for a fresh meta-os instance (a clone of the framework repository): run scripts/bootstrap.sh if it has not been run, then decide the backlog, the memory layout and the first project, choose packs (and optionally its GitHub repo), and fill in the instance contract .claude/CLAUDE.md. Use once, right after cloning — not a standing operating skill."
---

# Bootstrap Instance

A fresh instance — a clone of the framework repository, bootstrapped or not yet — is
structurally correct but has **zero decisions made**: no backlog declared, no first
project, no instance facts filled in. This skill runs that onboarding conversation once,
so the estate starts from a real decision instead of an empty placeholder.
Every decision has a non-interactive path in the script (`--backlog`, `--memory-layout`,
`--project`, `--packs`): the script is the one place that writes them.

Run this **once per new instance**, right after the repo is cloned and opened. It is
not a standing operating skill — [[skills/agile-process/SKILL|agile-process]],
[[skills/graphify/SKILL|graphify]], etc. take over from here. The mechanical part of
first run is `scripts/bootstrap.sh` ([[systems/distribution]]); this skill drives it and
never re-implements what it does.

## Step 0 — Bootstrap the checkout

Check whether `.claude/CLAUDE.md` exists at the repository root. It is the instance
contract, instantiated from `instance-template/root/` by `scripts/bootstrap.sh`, so:

- **Absent** → the clone has not been bootstrapped. Ask for the instance name (default:
  the directory name) and whether a private remote URL already exists, then run
  `scripts/bootstrap.sh --yes --name <name> [--origin <url>]`. It instantiates the
  instance files, turns the clone's `origin` into the fetch-only `upstream`, and builds
  the discovery links. Read its output back to the user; offer `--commit`, or leave
  the commit to Step 4. Packs are chosen in Step 1b, so don't pass `--packs` here.
- **Present** → already bootstrapped. `scripts/bootstrap.sh --yes` is idempotent and
  reports what exists; run it only if `.claude/skills/` is missing or dangling
  (`scripts/packs.sh check` says so).
- **`upstream` remote missing or `origin` still pointing at the public framework** →
  that is bootstrap's job too; run it rather than fixing remotes by hand.

Don't proceed until the instance files exist — every later step writes into them.

## Step 1 — Backlog

Ask where the backlog lives (present as distinct options, not a leading question):

1. **None yet** — work stays skill-driven; add a backlog later.
2. **A per-item backlog** — one markdown file per work item, filed by lifecycle tier,
   kept in a directory of its own (typically a separate vault repository, which brings
   its own CLI and gate). Ask for a **space key** (the backlog's short name) and the
   **directory**.

An external tracker is not part of this decision. Whether one exists, and whether it is
read-only or the tracker of record, is the agile pack's `tracker` setting (Step 1b); the
estate config only records where the backlog is.

Record the choice by running the script, which writes `backlogs[]` in
`meta-os.config.json` ([[systems/config]]) and is idempotent:

- **(1)** — `scripts/bootstrap.sh --yes --backlog none`
- **(2)** — `scripts/bootstrap.sh --yes --backlog <space>=<directory>` (repeat the flag
  for more spaces; `${var}` in the directory expands against `vars`)

A conflicting value already in the file is reported and left alone; change it by hand.

## Step 1b — Skill packs

The core ships only generic OS skills; domain skill sets are **packs**
([[systems/packs]]). Read the registry through the mount (`systems/packs.yaml`) and
offer the `available` entries by name + description — plus "none, add later". For each
chosen pack run `scripts/packs.sh add <name>`; report the provenance/license line as
you do. Mounting auto-enriches the project-local `.claude/` (skills + agents); if a
pack stages hooks, list them and ask per-hook before wiring any into
`.claude/settings.json` — never enable executable hooks silently. Custom repos are
allowed (`scripts/packs.sh add <name> <url>`) but tell the user they're outside the
curated registry.

**Configure a mounted pack.** A pack that ships a `pack.yaml` is parameterised — write
its `config:` block under `packs.<name>` in `.packs.yaml` from the choices already made,
then confirm with `scripts/packs.sh config <name>`. For the **agile** pack, take `space` from
the Step 1 space key and ask which `tracker` applies (`jira | local | none`, as the pack
documents it): an external tracker, a backlog with none, or no backlog (`profile: kanban,
tracker: none`). Suggest the agile pack whenever the user chose a backlog in Step 1.

## Step 2 — Memory layout and first project

**Memory layout.** Ask which topology the instance wants ([[systems/memory-layer]],
"Choosing a layout"): `default` (the instance's own `memory/{raw,wiki,output}` plus
`vaults/*`, no config block), or one canon root with layout `flat`, `tier/project` or
`project/tier`. Record it with `scripts/bootstrap.sh --yes --memory-layout <layout>`.
More roots and federated mounts are estate knowledge you add to `meta-os.config.json` by
hand.

**First project.** Ask for the first project to register: **name**, **local path**, and
whether the repo **already exists** or needs creating.

- If it exists: read its stack from what's actually there (package.json, pom.xml,
  Cargo.toml, etc.) — don't guess.
- If it doesn't exist yet: offer to `git init` it at the given path (or `gh repo create`
  — see Step 3). **Ask before running either.**

Then scaffold the node with `scripts/bootstrap.sh --yes --project <name>`: it writes
`projects/<name>.md` from [[templates/project|templates/project.md]] and adds the row to
[[projects/_index|projects/_index.md]]. Re-running reports it as already configured.
Then fill the node's `path`, `stack`, `tags` and one-line purpose, and the row's purpose
and stack cells, from what you read.

The three flags combine in one call, and `--dry-run` shows what would be written.

## Step 3 — GitHub integration for the project

Ask how the project relates to GitHub:

1. **Already has a remote** — read it with `git -C <path> remote get-url origin` and
   fill the note's `repo:` field from the real value (org/repo shorthand or full URL) —
   never guess an org name.
2. **Needs a new repo** — offer `gh repo create <owner>/<name> [--public|--private]`,
   asking the user which visibility, then set `repo:` from the result. **Confirm before
   creating** — this is a public-content / account action, not a silent default.
3. **Skip for now** — leave `repo:` unset; the [[systems/interface-layer.md|dashboard]]
   and registry table simply show no repo link until it's added later.

## Step 4 — Wrap up

- Fill in any remaining `.claude/CLAUDE.md` blanks (estate list now has at least one
  entry) and the `_index.md` title if bootstrap's guess at the name was wrong.
- Commit, if Step 0 did not: `git add -A && git commit -m "bootstrap: instantiate <name>"`,
  and push to the private remote once it exists (`git push -u origin main`).
- Mention the dashboard once: `scripts/bootstrap.sh --dashboard` clones it next to the
  repo and points it here; it is optional and can be done any time.
- If the project carries its own docs vault, offer to federate it —
  see [[vaults/_index|vaults/_index.md]] (`ln -s ../../<repo>/<vault-folder> vaults/<name>`).
- Point out [[skills/graphify/SKILL|graphify]] as the natural next step once there's a
  real codebase to map.

## Principles

- **Ask, don't assume.** Every decision above (tracker model, repo creation, visibility)
  is the user's call — present options, don't default silently.
- **Read reality before writing it.** Stack and `repo:` fields come from what's actually
  on disk/GitHub, never guessed.
- **One project is enough to start.** Don't try to onboard the whole estate in one pass
  — register the first project, leave `projects/_index.md`'s "Adding a project" note for
  the rest.
