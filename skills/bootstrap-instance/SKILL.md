---
name: "Bootstrap Instance"
description: "Interactive first-run setup for a freshly-created meta-os instance repo (from meta-os-instance-template or built by hand): decide the backlog/tracking model, register the first project (and optionally its GitHub repo), and fill in CLAUDE.md. Use once, right after cloning a new instance — not a standing operating skill."
---

# Bootstrap Instance

A brand-new instance repo (cloned from
[meta-os-instance-template](https://github.com/mova77/meta-os-instance-template) or
built by hand) is structurally correct but has **zero decisions made** — no backlog
model chosen, no first project, no `CLAUDE.md` facts filled in. This skill runs that
onboarding conversation once, so the estate starts from a real decision instead of an
empty placeholder.

Run this **once per new instance**, right after the repo is cloned and opened. It is
not a standing operating skill — [[skills/agile-process/SKILL|agile-process]],
[[skills/graphify/SKILL|graphify]], etc. take over from here.

## Step 1 — Backlog & tracking model

Ask the user (present as distinct options, not a leading question):

1. **No tracker yet** — work stays skill-driven; add a tracker later. Nothing to
   configure now.
2. **Local JSON backlog** — a self-contained `backlog.json` (stories/sprints/epics,
   no external tracker) lives in the instance or a project repo. Lightweight, git-diffable,
   no external account needed.
3. **Jira-integrated** — an external Jira project is the source of truth, mirrored into
   a `backlog.json` via [[skills/agile-process/SKILL|agile-process]]'s `sync.py`. Heavier:
   needs a Jira project key and (per that skill's convention) a private repo to hold the
   mirror.

Record the choice in the instance's `CLAUDE.md`, "Instance facts" section:

- **(1)** — leave the authority-order line out entirely.
- **(2)** — `**Backlog:** local JSON — see \`<path-to-backlog.json>\`. No external tracker.`
- **(3)** — `**Authority order (process/backlog):** Jira (project <KEY>) → \`<mirror-repo>/backlog.json\` → agile-process → framework invariants.` and confirm a mirror repo exists (offer to `gh repo create <owner>/<mirror-repo> --private` if not — **ask before creating**).

## Step 2 — First project

Ask for the first project to register: **name**, **local path**, and whether the repo
**already exists** or needs creating.

- If it exists: read its stack from what's actually there (package.json, pom.xml,
  Cargo.toml, etc.) — don't guess.
- If it doesn't exist yet: offer to `git init` it at the given path (or `gh repo create`
  — see Step 3). **Ask before running either.**

Then scaffold the node:

1. Copy [[templates/project|templates/project.md]] to `projects/<name>.md`.
2. Fill `name`, `path`, `stack`, `tags`; write the one-line purpose.
3. Add a row to [[projects/_index|projects/_index.md]]'s table.

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

- Fill in any remaining `CLAUDE.md` blanks (estate list now has at least one entry).
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
