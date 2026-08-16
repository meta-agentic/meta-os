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
opinions. Zero packs is a fully supported install.

For *what* makes a good pack and *where* the strategic opportunity is (codified
disciplines beyond software), see [[systems/pack-strategy]]. To *author* one, use the
[[skills/pack-builder/SKILL|pack-builder]] skill. Same philosophy as the
[[systems/distribution|framework mount]] itself; packs just apply it per-domain.

## Vocabulary — pack, discipline, registry name

One thing, three names, deliberately: **pack** is the *mechanism* (a mountable, pinned
repo of skills), **discipline** is what a good one *contains* (a method + a rigor
standard + portability — [[systems/pack-strategy]]), and the **registry name** is the
short key an instance mounts it by. First-party discipline repos are therefore named
`meta-discipline-<name>` while the registry key names the discipline, not the repo
(`agile` → `meta-discipline-agile`, `advanced-math` → `meta-discipline-math`); the
authoring skeleton follows the same rule (`pack-builder/resources/discipline-pack/`).
Where these docs say *pack*, read *a discipline packaged for mounting*.

## What a discipline adds to a skill

A skill is one codified workflow — a method, executable, discoverable. A discipline is a
*set* of them plus the two things that make an agent a practitioner rather than a
step-follower, and both are **per-skill**, not pack-level prose:

| | A plain skill | A skill inside a discipline |
|---|---|---|
| **Method** | numbered steps | the same steps, with `config.<knob>` referenced inline where a choice changes the procedure |
| **Standard of rigor** | usually absent | **required** — what "done right" means, stated as rules that *reject* something |
| **Evidence** | free-form output | **a named ledger** with a concrete filled-in example, able to read *fail* |
| **Boundaries** | implicit | the sibling skill it defers to, named in the intro |
| **Portability** | the author's conventions, welded in | method in the pack, choices in the instance (config · profiles · overrides) |

[[systems/pack.schema.json|pack.schema.json]]'s `per_skill` block is the checkable form
of that right-hand column, and `resources/discipline-pack/skills/SKILL.template.md` in
[[skills/pack-builder/SKILL|pack-builder]] is the shape to copy. The rigor standard and
the ledger are what [[systems/pack-strategy]]'s *checkable* test cashes out to: without
them a pack is a prompt pile with a manifest.

## What a pack is

A git repo carrying `SKILL.md` folders. The mount resolves a pack's skills two ways:

- **`.claude-plugin/plugin.json` present** → its `skills[]` list is **authoritative**
  (honours the author's own inclusions/exclusions — e.g. a `deprecated/` or `personal/`
  category the manifest omits stays unmounted).
- **otherwise** → `SKILL.md` is discovered **recursively at any depth**, so both flat
  (`skills/<name>/`) and category-nested (`skills/<category>/<name>/`) collections work.

The skill's mounted name is its folder basename. A pack MAY also carry `agents/`
(engine agent definitions, `*.md`) and `hooks/` (hook scripts). No special manifest is
required — existing third-party skill collections, and Claude Code plugins, qualify
as-is.

## Mount model (in the instance)

- A mounted pack lives at `.packs/<name>/` — a **pinned git submodule**, dot-folder so
  Obsidian doesn't index it directly (same trick as `.meta-os/`).
- The instance's `skills/` is a **union mount**: a real directory of per-skill
  symlinks — every framework skill plus every skill from every mounted pack.
  `scripts/packs.sh sync` (instance template) rebuilds it; re-run after a framework or
  pack bump.
- **Collision rule: the framework wins.** A pack skill whose name collides with a core
  skill (or an earlier pack's) is skipped with a warning — deterministic, no shadowing.
  **Exception — a depended-upon skill never fails quietly.** If the skipped name is one
  that another mounted pack declares in `depends[].for`, the warning becomes an **error**:
  the mount stops and names both claimants. A silently skipped dependency leaves the
  dependent pack citing a skill that isn't there, which surfaces later as an agent
  confidently improvising the discipline it was supposed to defer to.
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
| Configure | `scripts/packs.sh config <pack> [key]` | resolve a pack's parameters (instance `config:` over `pack.yaml` defaults), validate enums |

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

## Conformance — the manifest contract

[[systems/pack.schema.json|pack.schema.json]] is the machine-readable contract for a
pack's `pack.yaml`: required keys, the `config` key shape (`default` / `one_of` /
`doc`), `depends` / `provides`, and — in its `required_files` block — the files a
conformant pack ships. [[skills/pack-builder/SKILL|pack-builder]] carries the matching
skeleton at `resources/discipline-pack/`.

The convention is deliberately checkable rather than prose-only, because prose drifts:
the structure documented before this contract existed had already fallen behind what the
shipped packs carried, and a pack authored from the doc came out wrong. **Validate the
manifest, then mount it** — reading another pack by eye is how the drift propagates.

**Config keys are written in block form**, one key per block with `default:` / `one_of:` /
`doc:` beneath it — *not* as an inline `{ … }` map. `doc:` is required and its prose
contains commas, which a comma-split inline map cannot carry, so the inline shape cannot
express a conformant key at all. It survives only as a legacy shape the mount still reads.

Three rules the schema encodes that are easy to get wrong from examples alone:

- **Every skill emits a named ledger** with a filled-in example, and the ledger must be
  able to say *no* — a rigor standard with no failing reading is decoration.
- **Profiles are optional.** Ship them only for genuine methodology variants; a pack with
  one mode says so instead of inventing a split to look like its siblings.

## Dependencies between packs

Packs reuse each other: the physics pack consumes the math pack's `dimensional-analysis`
rather than redefining units, π-groups, and uncertainty. That relationship is declared in
the depending pack's `pack.yaml` and mirrored in its registry entry (so it can be resolved
*before* the repo is cloned):

```yaml
depends:
  - name: advanced-math
    for: [dimensional-analysis]
    reason: "units homogeneity, Buckingham π, uncertainty propagation — not duplicated here"
```

The dependency's own manifest declares the other side of the contract:

```yaml
provides: [dimensional-analysis, mathematical-rigor]   # the public surface
```

**Resolution semantics** — deliberately thinner than Maven/Gradle:

| Concern | Rule | Why |
|---------|------|-----|
| Version | **Names only; no ranges.** | A mounted pack is a *pinned submodule* — the instance's commit pin is the version. A range would fight the pin, and mediating two ranges against one submodule has no sound answer. |
| Transitivity | Resolved transitively by name against the registry; `add <pack>` mounts missing dependencies and reports each one it added. | Mounting must not require the adopter to hand-walk a graph. |
| Missing | **Hard failure**, naming what is missing and which registry entry would supply it. | A pack whose dependency is absent is not degraded, it is broken. |
| Cycles | Rejected at validate time. | Two packs that need each other are one pack. |
| Removal | `remove <pack>` refuses while a mounted pack depends on it; removing the dependents first (or an explicit cascade) is the path. | Silent orphaning is how a working instance breaks a week later. |
| Optional | `optional: true` deps are **reported, never auto-mounted** — for a skill only reachable under a non-default profile. | Auto-mounting on a profile the estate doesn't use is unrequested surface. |
| Collision | A collision on a depended-upon name is an **error** (see the mount model above). | The one case where the warn-and-skip default hides a real break. |

Pins stay the unit of upgrade: bumping a dependency is `packs.sh update <dep>` in the
instance, a reviewable commit, exactly as for any other pack. Nothing here introduces a
resolver that can change what is mounted without a diff.

## Evolving a discipline — the improvement loop

The lifecycle table above is the *consumption* side (how an instance takes a new pin);
this is how the discipline itself gets better. Skills improve **structurally, not by
memory** ([[skills/_index]]) — a discipline adds one thing to that loop: **the ledger is
the evidence stream.** A rigor standard runs keep waiving, or a ledger column that is
always empty, is a finding about the discipline, not about the run.

1. **Observe in the instance.** Per-run [[templates/skill-note|skill-notes]] roll into the
   one standing [[templates/skill-learnings|skill-learnings]] note per skill
   (`memory/wiki/skills/<skill>-learnings.md`). Learnings never live in a pack repo —
   they are instance experience, and packs are public-safe by construction.
2. **Classify before editing** — which layer is actually wrong decides where the change
   goes, and getting this wrong is how a pack turns back into one shop's dogma:

   | Symptom | Layer | Where the fix lands |
   |---------|-------|---------------------|
   | Every estate practising this discipline would want it | **method** | edit the skill in the pack |
   | Only this estate wants it | **parameter** | a `config:` knob (or a knob that already exists) |
   | A coherent *other* way to practise the discipline | **profile** | a new `profiles/<name>.md` — never a fork |
   | A distinct method the pack doesn't cover | **scope** | a new skill; re-run the three-part test first |
   | Another pack already codifies it | **dependency** | `depends:` + cite by wikilink, never a second copy |
3. **Change it upstream.** Fold the generalized learning into the pack repo as a reviewed
   change, then delete it from the instance note. Editing `.packs/<name>/` in place is a
   detached submodule change — the next update discards it.
4. **Re-verify before publishing.** `pack.yaml` still validates against
   [[systems/pack.schema.json|pack.schema.json]]; the changed skill still emits its named
   ledger and can still say *no*; `skills/_index.md` gained its row; the skill was driven
   once end-to-end in a clean instance clone ([[skills/pack-builder/SKILL|pack-builder]]
   Step 6).
5. **Adopt deliberately.** Instances take the improvement with `scripts/packs.sh update
   <pack>` — a pin bump, a reviewable commit. Nothing improves ambiently: the estate
   chooses when the discipline changes under it.

Retiring or renaming a skill runs the same loop in reverse, and keeps a deprecation row
for one minor version naming what supersedes it (as the framework does under Migration
below) — another pack may name that skill in `depends[].for`, where a silent
disappearance becomes an agent improvising the discipline it was meant to defer to.

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
