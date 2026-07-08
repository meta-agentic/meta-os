---
type: system
tags: [os, system, distribution]
---
# Distribution — how an instance consumes the framework

Community feedback on the two-repo model: sibling checkouts + symlinks confuse adopters
who want to *clone one thing and go*; it's unclear where a project's deliverables land;
and a containerized install was requested. This note is the standing answer: the
consumption modes, why the framework/instance **separation stays** in all of them, and
the container layout.

## The invariant

The privacy boundary is structural, not procedural: framework (public-safe) and instance
(private) are **different git histories**. That survives every mode below. What varies is
only *how the framework arrives on disk*.

## Modes

| Mode | Get it | Update it | For |
|------|--------|-----------|-----|
| **1 · Single clone (submodule)** — default for adopters | `git clone --recursive <your-instance>` (created from the instance template; `meta-os` is a git submodule inside it) | `git submodule update --remote meta-os`, commit the pin — a deliberate, reviewable version bump | Users who want one repo that just works |
| **2 · Sibling checkouts** — developer mode | clone framework and instance side by side; per-folder symlinks (`skills → ../meta-os/skills`) | `git pull` in `meta-os/` | Anyone hacking the framework itself while running an instance |
| **3 · Container** | `docker compose up` — image ships framework + engine + dashboard at a pinned tag | pull a newer image tag; volumes untouched | Zero-setup / server installs (layout below) |

In modes 1 and 2 the instance's mount folders are the same four symlinks; only the
target differs (`meta-os/skills` vs `../meta-os/skills`). Vault-root-relative wikilinks
resolve identically, so notes never know which mode they're in.

## Why not one merged repo

The obvious ask — "let me clone `meta-os` and customize it in place, with updates that
skip my folders" — was evaluated and rejected:

- **Updates would conflict exactly where users customize.** The framework tracks
  `memory/` skeleton indexes, `CLAUDE.md`, `_index.md`; a merged repo means every
  upstream pull fights the user's edits to those same paths. The submodule pin gives
  "update without overwriting my folders" *for free* — framework files aren't in the
  instance's history at all.
- **Root contracts collide.** Framework and instance each need their own `CLAUDE.md` /
  `_index.md` (the generic contract vs. *your* estate and authority order). One repo
  can only have one of each.
- **Privacy inverts.** A public-repo fork can never be made private on GitHub, and a
  private vault whose history *contains* the public repo is one wrong `git push
  --set-upstream` away from leaking memory. Two histories make the leak structurally
  impossible.
- **Contributing back gets harder,** not easier: framework fixes would need
  path-filtered cherry-picks out of a private history instead of a normal PR from a
  `meta-os` checkout.

What the feedback actually asks for — one clone, protected customization — is mode 1.

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

## Container layout (mode 3)

The split maps 1:1 onto image vs. volumes — the image is the framework, volumes are the
instance:

```
image (versioned, disposable)          volumes (private, persistent)
├── meta-os @ pinned tag               ├── /vault     ← the instance repo: CLAUDE.md,
├── engine (claude CLI)                │               projects/, memory/, automations/,
├── meta-os-dashboard (built)          │               instance.config.json
└── entrypoint: wire symlinks,         ├── /projects  ← estate working repos (graphify
    start dashboard + heartbeat        │               output, backlog mirrors live here)
                                       └── /engine    ← engine home (credentials,
                                                       session logs — feeds the usage widget)
```

- Upgrade = pull a newer image; both private volumes are untouched — the container
  answer to "updates must not overwrite my customization".
- `/vault` stays a git repo the user pushes to their own private remote; the container
  adds no second source of truth.
- The dashboard's `instance.config.json` lives in `/vault` and points at
  `/vault` + `/projects/...` paths, so one config survives image upgrades.

Status: layout agreed here; `Dockerfile` + `compose.yml` land in the dashboard repo
(app lifecycle) once built and verified — this note then links to them.
