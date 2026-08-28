---
type: system
tags: [os, systems, documentation]
---
# Repo docs — entry READMEs as a distributed knowledge base

An estate is many repositories; its documentation is one corpus. Each repo's root
`README.md` is a **node** in that corpus and its links are the **edges** — so the
standard below is less about prose style than about where knowledge is allowed to
live. It applies to every repo an instance registers, framework and estate alike.

## The one-home rule

Every concept has exactly **one authoring home**; every other mention is a link.

| Kind of knowledge | Authoring home |
|---|---|
| Repo-specific (build, layout, procedures of *this* repo) | that repo's own `README.md` / docs |
| Estate-cross-cutting (topology, architecture decisions, governance) | the estate's **docs hub** repo (or the instance, if no hub exists) |
| Operating model, process, conventions (how work is done, not what is built) | the **framework** (public, generic) and the **instance** (private specifics) |

Corollaries:

- **The corpus map lives once.** One repo — the docs hub or the instance root —
  owns the table of "which repo does what". Every other README states its own role
  in one line and links to that map. Never paste the map into a second repo: copies
  drift, and a drifted map is worse than none.
- **Public repos link only to public repos.** A private instance may link anywhere;
  a public README naming a private repo leaks the instance and gives readers a
  dead link. This is the framework/instance privacy boundary applied to edges.
- **Link the enforcer, don't restate the rule.** If a CI job or hook enforces a
  convention, the README links to it; prose restatements of enforced rules rot.

## Entry-README structure (graduated onboarding)

Order sections so that each scroll-depth serves a reader one level deeper. A
newcomer must get value from the top without reading the bottom; an expert must
find the deep material without wading through the basics being re-explained.

1. **Identity** — title + one paragraph: what this repo is, for whom, in what state.
2. **Where this fits** — one line + link to the corpus map. Never the full map.
3. **Quick start** — the smallest complete action a newcomer can take (clone,
   build, consume, run), as a copy-paste block. This comes *before* any
   architecture or theory.
4. **Contents** — a TOC, once the README exceeds roughly a screenful.
5. **Body** — the repo-specific sections (layout, catalog, procedures). Advanced
   material is welcome here, but *sectioned*, so it can be skipped, and deep
   dives live in linked specialist docs rather than inflating the entry page.
6. **Further reading** — the outbound edges: canonical docs, sibling repos,
   the framework. This is what makes the corpus navigable as a graph.

## Rules of evidence

- **Every actionable procedure carries at least one runnable example.** A
  procedure described without a copy-paste command is a claim, not documentation.

  ```bash
  # e.g. a "build one module" procedure must show the actual invocation:
  mvn -pl <module> -am clean verify
  ```

- **No dead edges.** When you touch a README, verify the paths and repo links it
  asserts still exist — a moved folder or renamed repo must not survive in prose.
  Stale links are how a distributed corpus silently partitions.
- **Date what decays.** Status claims ("scaffold", "sprint N", counts of things)
  carry a date or are derived from a linked source; undated status is
  indistinguishable from wrong status.
- **Tables for enumerables, prose for reasoning.** Catalogs of services, modules,
  or files are tables; the *why* around them is prose.

## Maintenance

Treat the entry README as part of the change, not as an afterthought: a PR that
moves a folder, renames a launcher, or retires a mechanism updates every README
line that asserted the old fact — in the same PR. Periodic estate-wide audits
(walk every repo, check every edge) catch what slips through; codify that walk
as a skill if it is done more than once.
