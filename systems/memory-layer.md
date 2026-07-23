---
type: system
tags: [os, system, memory]
---
# Memory Layer

The knowledge discipline. Full folder detail in [[memory/_index]]; this is the *why* and
the *rules*.

## raw → wiki → output

- **raw/** — capture everything, structure nothing. Disposable. Never authoritative.
- **wiki/** — the durable, linked, indexed reference. Only **promoted** notes live here.
- **output/** — finished deliverables, each linking back to the wiki notes it drew from.
  Namespace by project when volume warrants (`output/<project>/`). A project that
  delivers somewhere *else* declares it in its registry node's `output:` field — see
  [[systems/distribution]], "Where deliverables land".

## Memory topology — roots vs federated, and configurable layout

`raw → wiki → output` is the invariant; *where it physically lives* is **configurable per
instance**. Two kinds of memory, and the reader treats them differently:

- **Canon roots** — enumerated *as* the pipeline (counted, promotable). Each root declares
  a **layout**: `flat` (`{raw,wiki,output}` at the root), `project/tier`
  (`<project>/{raw,wiki,output}`), or `tier/project` (`{raw,wiki,output}/<project>`). An
  instance may have more than one root — e.g. an **instance root** for *cross-cutting* OS
  knowledge (retros, skill-learnings, cross-project architecture) and an **estate root**
  holding per-project memory including the **backlog** as its raw tier.
- **Federated mounts** — surfaced in the graph for *navigation/context*, **never counted
  as canon**. These are other repos' own docs vaults, joined by symlink (see below).

**Boundary rule:** a fact about one project lives in project memory; a fact that spans
projects, or is about the OS itself, lives in the instance root. Project knowledge that
becomes cross-project-durable is **promoted up**, never copied. *Single source of truth
per fact.*

### Choosing a layout

The layout is a genuine trade-off, so it is a choice, not a mandate:

- **`tier/project`** favours **cross-project** browsing ("everything in flight across the
  estate") — good when a root is read *directly* by the reader.
- **`project/tier`** favours **per-project ownership and clean extraction**, and is
  **required** when that memory is also **federated per project** — a federated mount is
  one symlink per project (`vaults/<project>`), so each project must map to a single
  directory; `tier/project` can't be federated that way.
- **`flat`** suits a single self-contained root (e.g. the instance root).

So an adopter who reads a root directly may pick `tier/project`; one who federates
per-project into the Obsidian graph uses `project/tier`. Cross-cutting views under
`project/tier` come from **tags and queries**, not directory layout. Absent any config, the
default is the in-instance `memory/` root (`flat`) plus per-project `vaults/*` federation.

*Where* a project's memory lives is likewise per-project: the project's **own doc-repo**
(when it already keeps ADRs/architecture beside its code) or a folder in a **shared vault
repo** (for projects with no doc home). Instance memory is **never symlinked out** — the
reader walks its git history in place, so a cross-repo symlink there returns nothing.

## Promotion is the whole game

An LLM-wiki is only as trustworthy as its promotion discipline. To promote a `raw/` note:

1. Clean it — remove scratch, keep the signal.
2. Add front-matter (`type:`, `tags:`) and a clear title.
3. Link it into the graph with `[[wikilinks]]` (to projects, skills, other wiki notes).
4. Move it to the right `wiki/` topic folder; update that folder's `_index.md`.

Run [[skills/graphify/SKILL|graphify]] over `wiki/` periodically to surface orphans and gaps — orphans are
usually un-promoted knowledge or missing links.

## Federation by symlink, not absorption

Project memory joins the OS's Obsidian graph through symlinks in the instance's `vaults/`
folder — one unified graph, zero file moves. The mount contract is uniform ("mount this
project's vault"); the backing is whichever the topology chose above — the project's own
docs repo (ADRs/architecture colocated with its code) **or** a folder in the shared vault
repo. Either way the content is committed by its **backing** repo, not absorbed into the
instance.

Federation is for **navigation**; promotion is for **canon**: cross-project-durable
knowledge still gets promoted into the instance `wiki/`. Single source of truth per fact.

## Relationship to agent memory

Runtime agent memory (ReasoningBank / AgentDB, the `.swarm/` stores) is *operational* — it
learns trajectories and patterns. This vault is *editorial* — human-curated knowledge.
Promote insights worth keeping from the former into the latter; don't conflate them.
