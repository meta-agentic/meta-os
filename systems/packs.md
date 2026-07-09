---
type: system
tags: [os, system, distribution, packs]
---
# Skill Packs

The framework core stays **generic by construction**: it ships only the skills that are
part of the OS itself (bootstrapping, skill authoring, graph, hooks, verification).
Everything that encodes *a* process rather than *the* OS — an agile method, a swarm
lab, a third-party skill collection — is a **pack**: a separate repo, mounted into an
instance on demand, individually pinned and updatable.

Packs are also how the OS stays **domain-agnostic**: a software-delivery estate mounts
the agile pack, a research instance might mount a literature-review pack, a
systems-engineering instance a requirements/trade-study pack — same core, different
opinions. Zero packs is a fully supported install. Same philosophy as the
[[systems/distribution|framework mount]] itself; packs just apply it per-domain.

## What a pack is

A git repo carrying `skills/<name>/SKILL.md` folders (a `skills/` dir at the repo root,
or skill folders at the root itself — the mount script auto-detects). It MAY also carry
`agents/` (engine agent definitions, `*.md`) and `hooks/` (hook scripts). A pack needs
no special manifest — existing third-party skill collections qualify as-is.

## Mount model (in the instance)

- A mounted pack lives at `.packs/<name>/` — a **pinned git submodule**, dot-folder so
  Obsidian doesn't index it directly (same trick as `.meta-os/`).
- The instance's `skills/` is a **union mount**: a real directory of per-skill
  symlinks — every framework skill plus every skill from every mounted pack.
  `scripts/packs.sh sync` (instance template) rebuilds it; re-run after a framework or
  pack bump.
- **Collision rule: the framework wins.** A pack skill whose name collides with a core
  skill (or an earlier pack's) is skipped with a warning — deterministic, no shadowing.
- Mounting also enriches the **project-local `.claude/` engine surface** —
  `.claude/skills/` mirrors the union (sessions inside the instance discover
  everything with zero global setup; portable to containers/remote), pack `agents/`
  link into `.claude/agents/`, pack `hooks/` are **staged** at `.claude/hooks/<pack>/`.
  **Hooks are never auto-wired into `settings.json`** — a hook is executable code, so
  enabling one is an explicit, per-hook user decision, always.
- Machine-global discovery (`~/.claude/skills/<name>`) remains available and chains
  through the union dir to wherever the skill really lives.

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
| Rebuild | `scripts/packs.sh sync` | regenerate the union `skills/` + `.claude/` |
| Reconcile | `scripts/packs.sh apply` | make mounts match the instance's `.packs.yaml` manifest |

Pins are commits: upgrading a pack is a deliberate, diffable change in the instance's
history — never an ambient drift.

**Declarative selection / headless installs.** The instance's `.packs.yaml` is the
desired-state list; `add`/`remove` maintain it, `apply` reconciles to it
(idempotent). A container entrypoint or CI can therefore install packs with no
conversation at all: write the manifest (e.g. from a feature flag like
`METAOS_PACKS=agile,superpowers` on first run) and run `apply`. The selection lives in
the vault, so it survives image upgrades and re-applies on every boot.

## Parameterisation — method vs. opinion

A pack that hardcodes its author's conventions just relocates opinion; the contract is
that packs separate three things:

1. **Method (invariant)** — what the pack *is*: the ceremony structure, the lane model,
   the review discipline. Lives in the pack's skills, versioned with the pack.
2. **Parameters (chosen per instance)** — names, trackers, cadences, repos. A pack
   documents its knobs in its README; the instance sets them in `.packs.yaml` under the
   pack's `config:` block (it's the one desired-state file packs already own):

   ```yaml
   packs:
     agile:
       config:
         space: acme
         tracker: jira          # jira | local | none
         mirror-repo: you/scrum-mirror
   ```

   Skills read config-first and fall back to their documented defaults; placeholders in
   a pack's docs (`<SPACE>`-style) name the keys that resolve from this block.
3. **Conventions (overridable)** — branch rules, DoR lists, commit formats. Packs ship
   them as *data* (files the skills read) with instance-side overrides winning, additive
   merge — the same template-chain semantics the OS uses elsewhere. Hooks remain opt-in
   per hook, always, regardless of configuration.

Packs MAY ship **profiles** — named convention bundles (e.g. a Scrum-with-tracker
profile vs. a lightweight Kanban profile) selected via `config: profile: <name>` — so
"choose a methodology" is a one-line decision, and "change it" is an edit to instance
data, never a fork of the pack.

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
