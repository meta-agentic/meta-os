---
type: system
tags: [os, system, distribution]
---
# Distribution — one repository, two owners

An instance of the OS **is a clone of this repository**. The framework and the instance
share one git history and own **disjoint paths**: the framework's folders arrive and
update by merge, the instance's folders are instantiated once on first run and never
touched by the framework again. Setting up is one clone and one script; updating is one
script. This note is the standing answer to how an instance consumes the framework, why
the separation that used to be two repositories now runs *inside* one, and what each
side may and may not do.

## The invariant

The privacy boundary is structural, not procedural. It used to be "two git histories";
it is now **two path sets with one owner each, enforced by a gate**:

| Owner | Paths | Who writes | How it changes |
|-------|-------|-----------|----------------|
| **Framework** (public) | `CLAUDE.md` · `README.md` · `LICENSE` · `PROVENANCE.md` · `SECURITY.md` · `skills/` · `systems/` · `templates/` · `agents/` · `hooks/` · `pipeline/` · `scripts/` · `tests/` · `instance-template/` · `.github/` · `.githooks/` · `.gitignore` | upstream, by pull request in a public checkout | `scripts/upgrade.sh` merges the framework's `main` |
| **Instance** (private) | everything `instance-template/root/` carries, at the same paths: `.claude/CLAUDE.md` · `_index.md` · `projects/` · `memory/` · `automations/` · `vaults/` · `meta-os.config.json` · `.packs.yaml` · `.obsidian/` — plus the pack mounts `.packs/` and `.gitmodules` | the instance, directly | never by the framework |

Two rules keep the sets disjoint, and both are checked by a program rather than by care:

1. **The framework never tracks an instance path.** `scripts/validate_framework.py`
   derives the instance paths from `instance-template/root/` and fails — never as
   tolerated debt — on any tracked file at one of them. So a framework merge cannot
   carry a change to an instance file, because no framework commit contains one.
2. **An instance never edits a framework path.** `scripts/upgrade.sh` lists the
   framework paths the instance modified or deleted since the merge base and refuses
   to merge while there are any (`--force` to carry them and resolve the result
   yourself). Adding a path anywhere is fine — the instance's own skill in `skills/`,
   its own note type in `systems/`; only the framework's files are off limits.

What the instance contract and the framework contract are is unchanged: the root
`CLAUDE.md` is the framework's (what the OS *is*), `.claude/CLAUDE.md` is the
instance's (what *this estate* is). Claude Code loads both as project instructions, so
no composition step and no symlink stands between a framework rule and the session
that must follow it.

## First run

```bash
git clone https://github.com/meta-agentic/meta-os.git my-os && cd my-os
scripts/bootstrap.sh            # interactive on a terminal; --yes takes every default
```

`scripts/bootstrap.sh` does five things, each idempotent and each reported:

1. **Instantiates** `instance-template/root/` at the repository root — path for path,
   only where the path does not exist yet — and fills the placeholders
   (`{{instance-name}}`, `{{bootstrapped}}`, `{{template-ref}}`) in the copies.
   [[instance-template/_index|instance-template/]] documents the payload.
2. **Points the remotes the right way round.** The clone's `origin` is the public
   framework, so it becomes `upstream` with its push URL set to `no_push`: the
   framework is fetched, never pushed to, and a wrong `git push` fails instead of
   leaking an estate. Your private remote is added as `origin` (`--origin <url>`, or
   later by hand).
3. **Mounts packs** (`--packs agile,…` from [[systems/packs.yaml|the registry]]) and
   **builds the discovery links**: pack skills linked into `skills/` beside the
   framework's own, the whole of `skills/` mirrored into `.claude/skills/`. Generated,
   never committed — `scripts/packs.sh sync` lists its links in `.git/info/exclude`,
   the framework's `.gitignore` covers `.claude/{skills,agents,hooks}/`.
4. **Installs the dashboard** if asked (`--dashboard [dir]`): clones
   [meta-os-dashboard](https://github.com/meta-agentic/meta-os-dashboard) next to the
   repository and writes its `instance.config.json` pointing here — the app keeps its
   own repository and lifecycle (Node dependencies, build, CI), the instance just
   gets it wired on first run.
5. **Commits** (`--commit`) or tells you the command.

Headless installs pass every answer as a flag (`--yes --name acme --packs agile
--origin git@…`); `--dry-run` prints the plan and writes nothing. The guided first
conversation — backlog model, first project, GitHub wiring — stays with the
[[skills/bootstrap-instance/SKILL|bootstrap-instance]] skill, which calls this script
for the mechanical part.

## Updating

```bash
scripts/upgrade.sh --check      # how far behind, integrity, template drift — changes nothing
scripts/upgrade.sh              # fetch upstream, verify, merge, re-sync the links
```

The merge touches framework paths only (rule 1). After it, `scripts/packs.sh sync`
rebuilds the links so a skill the framework added is discoverable at once, and the
framework's own gate runs scoped to the framework's paths.

**The template is reported, not re-applied.** An instance's `_index.md`, `projects/`,
`automations/` are its own from the moment they were instantiated; a later change to
`instance-template/root/` is shown as a diff since the `template` ref recorded in
`meta-os.config.json`, for the operator to apply by hand or ignore, then
`--ack-template` records the reviewed ref. A change that must reach *running*
instances is framework mechanism and belongs in `skills/`, `systems/`, `scripts/` or
`hooks/` — never in the template.

**A repository created from a template snapshot** (GitHub's *Use this template*, or a
copied tree) has no history in common with the framework. The first upgrade merges
with `--allow-unrelated-histories`; every conflict it can meet is a framework path the
framework itself changed since the snapshot (rule 2 was checked first), so each is
resolved to the framework's version. From then on there is a merge base and upgrades
are ordinary merges.

## Why one repository — and what changed since it was rejected

An earlier version of this note rejected the merged repository on four grounds. Each
was an argument against *a live merge of unowned paths*; the ownership rules above
remove the premise:

| Objection then | Answer now |
|---|---|
| Updates conflict exactly where users customise — the framework tracked `memory/`, `CLAUDE.md`, `_index.md` | The framework tracks **no** instance path (rule 1, gate-enforced) and the instance edits **no** framework path (rule 2, refused on upgrade). A merge cannot collide with a file only one side has ever committed. |
| Root contracts collide — one repository has one `CLAUDE.md`, one `_index.md` | The engine loads two project-instruction files, `CLAUDE.md` and `.claude/CLAUDE.md`; the framework owns the first, the instance the second. The framework ships no `_index.md` at the root: the vault home is instantiated. |
| Privacy inverts — a fork can never be made private; a private history containing the public one is one wrong push from a leak | An instance is a clone or a template snapshot, never a GitHub fork, so it is private from its first commit. The framework remote is fetch-only by construction (`no_push`), and the public repository's own gate rejects instance identifiers in anything it tracks. |
| Contributing back needs path-filtered cherry-picks out of a private history | A framework change is made in a public checkout and proposed upstream, as for any open-source dependency; the instance takes it with the next upgrade. An edit that landed in an instance by mistake is a `git diff upstream/main -- <framework paths>` away from a patch. |

What the rejection protected — the public framework must never carry an estate's
data — survives intact; it is now enforced by the gate on every commit rather than by
the accident of two repositories. What it cost — a template repository that drifted
from the framework it scaffolded, a `packs.sh` vendored per instance and fixed in one
place at a time, a submodule most adopters cloned without `--recursive`, a mode script
to flip four symlinks — is gone with the second repository.

## Where deliverables land (per project)

Default: finished work is filed to the instance's `memory/output/`, namespaced by
project when volume warrants (`memory/output/<project>/`). A project that delivers
somewhere else — an existing repo, a new empty one, a docs site — declares it in its
registry node: the `output:` front-matter field ([[systems/ontology.yaml|ontology.yaml]]
`project` type) holds a repo (`org/repo` or URL) or a path. The delivering skill reads
the field and lands results there; the dashboard's registry and output-inbox widgets
surface it so the answer to "where does this project deliver?" is always one glance
away. `output:` names the *destination*, not a promise — an empty referenced repo is
fine; it fills as the project ships.

## Container

A container install is the same layout with the engine and the dashboard baked into
an image and the instance — this repository, framework paths included — on a volume:

```
image (versioned, disposable)          volumes (private, persistent)
├── engine (claude CLI)                ├── /instance  ← your clone of this repository:
├── meta-os-dashboard (built)          │               framework + instance paths,
└── entrypoint: scripts/bootstrap.sh   │               upgraded with scripts/upgrade.sh
    --yes on an empty volume,          ├── /projects  ← estate working repos
    scripts/packs.sh apply every boot  └── /engine    ← engine home (credentials, logs)
```

- Upgrading the framework is `scripts/upgrade.sh` inside the volume; upgrading the
  engine or the dashboard is a newer image tag. Neither touches the other.
- `/instance` stays a git repository the operator pushes to their own private remote;
  the container adds no second source of truth.
- The dashboard's `instance.config.json` points at `/instance` for both
  `instanceRoot` and `frameworkRoot` — one path, because they are one checkout.

Status: layout agreed here; `Dockerfile` + `compose.yml` land in the dashboard repo
(app lifecycle) once built and verified — this note then links to them.
