---
type: system
tags: [os, system, distribution, packs]
---
# Skill Packs

The framework core stays **generic by construction**: it ships only the skills that are
part of the OS itself (bootstrapping, skill authoring, graph, hooks, verification).
Everything that encodes *a* process rather than *the* OS — an agile method, a swarm
lab, a third-party skill collection — is a **pack**: a separate repo, mounted into an
instance on demand, individually pinned and updatable. Same philosophy as the
[[systems/distribution|framework mount]] itself; packs just apply it per-domain.

## What a pack is

A git repo carrying `skills/<name>/SKILL.md` folders (a `skills/` dir at the repo root,
or skill folders at the root itself — the mount script auto-detects). It MAY also carry
`agents/` and `hooks/`; v1 mounts **skills only** (agents/hooks mounting is a planned
extension). A pack needs no special manifest — existing third-party skill collections
qualify as-is.

## Mount model (in the instance)

- A mounted pack lives at `.packs/<name>/` — a **pinned git submodule**, dot-folder so
  Obsidian doesn't index it directly (same trick as `.meta-os/`).
- The instance's `skills/` is a **union mount**: a real directory of per-skill
  symlinks — every framework skill plus every skill from every mounted pack.
  `scripts/packs.sh sync` (instance template) rebuilds it; re-run after a framework or
  pack bump.
- **Collision rule: the framework wins.** A pack skill whose name collides with a core
  skill (or an earlier pack's) is skipped with a warning — deterministic, no shadowing.
- Machine-global discovery is unchanged: `~/.claude/skills/<name>` chains through the
  union dir to wherever the skill really lives.

## The registry — [[systems/packs.yaml|packs.yaml]]

The curated list offered at bootstrap ([[skills/bootstrap-instance/SKILL|bootstrap-instance]]
asks which packs to mount). Curation bar for an entry:

- **Provenance named** — `first-party` or `third-party` with the real upstream repo;
  never a silent fork or vendored copy.
- **License known** (or explicitly marked verify-before-use).
- **Public-safe** — a pack must carry no instance data; the privacy boundary applies to
  packs exactly as it does to the framework.

Custom packs outside the registry mount with `packs.sh add <name> <repo-url>` — allowed,
but reported as unregistered/unverified when added.

## Lifecycle

| Action | Command (instance) | Effect |
|--------|--------------------|--------|
| Mount | `scripts/packs.sh add <name> [url]` | submodule at `.packs/<name>` + union re-sync |
| Unmount | `scripts/packs.sh remove <name>` | submodule removed + union re-sync |
| Upgrade | `scripts/packs.sh update [name]` | pin bump (reviewable commit) + re-sync |
| Inspect | `scripts/packs.sh list` | mounted packs, pins, skill counts |
| Rebuild | `scripts/packs.sh sync` | regenerate the union `skills/` |

Pins are commits: upgrading a pack is a deliberate, diffable change in the instance's
history — never an ambient drift.

## Not packs, still worth knowing

Some widely-used resources don't mount as packs and shouldn't be forced into the
model: **awesome-lists** (skill *directories* — browse them to find pack candidates),
**anthropics/claude-cookbooks** (notebooks/patterns, not SKILL.md folders),
**modelcontextprotocol/servers** (MCP servers — connect them via engine config, not
mounts), **ccusage** (a CLI utility; the dashboard's usage widget covers the same logs
natively). The registry keeps a comment block of such non-pack resources and of
candidates awaiting provenance verification.

## Migration

Skills extracted from the framework core reappear as packs (first: the agile set; then
the vendored third-party cluster flagged in `PROVENANCE.md`, which becomes registry
pointers at real upstreams instead of vendored copies). Each extraction carries a
deprecation row in the framework release notes for one minor version, naming the pack
that now provides the skill.
