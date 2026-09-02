# Provenance & Attribution

Origin and license of every skill in `skills/`. The repository as a whole is MIT
([LICENSE](LICENSE)); third-party-derived content remains under its original MIT copyright,
noted below. Last verified: 2026-08-29.

## Skill provenance

| Skill(s) | Origin | License | Notes |
|----------|--------|---------|-------|
| `skill-builder` | **Original** — this project; **replaced** the vendored [claude-flow / Ruflo](https://github.com/ruvnet/claude-flow) copy on 2026-08-29 | MIT | Rewritten from nothing against this framework's own contract: the trigger-not-summary description, progressive disclosure, the index + provenance rows a skill is not finished without, when a skill belongs in a pack instead, and the discipline five-part shape it hands to `pack-builder`. No upstream text survives. |
| `infoviz` | **Original** — this project | MIT | Encodes published practitioner canon (Kirk, Cleveland & McGill, Munzner, Bertin, the FT *Visual Vocabulary*, Lima) as a decision procedure; sources are cited in `references/bibliography.md`, none vendored. Complements Anthropic's `dataviz`, which owns palette and chart chrome. **Pack candidate** — it is a domain discipline rather than OS machinery, and belongs in an information-visualisation pack when one exists. |
| `graphify` | [Graphify Labs](https://github.com/safishamsi/graphify) · [graphify.net](https://graphify.net) — safishamsi | MIT | Vendored at v0.9.5 (2026-07-04). Update via `pip install -U graphifyy && graphify install --platform claude` — writes through the `~/.claude/skills/graphify` symlink into this repo |
| `agile-process`, `agile-swarm` | **Original** — this project; **moved** to [meta-discipline-agile](https://github.com/meta-agentic/meta-discipline-agile) | MIT | Extracted from core when the skill library was slimmed to generic-only; mount as the `agile` pack (org: meta-agentic) |
| `multi-engine` | **Original** — this project; invokes sibling [meta-cli](https://github.com/meta-agentic/meta-cli) | MIT | Standing multi-provider surface; see `systems/engine.md` |

## Removed, 2026-08-29 — the last vendored third-party skills

`hooks-automation` (1,201 lines of claude-flow hook-CLI reference), `swarm-orchestration`
(agentic-flow swarm topology) and `ruflo-setup` (a Ruflo CLI quick-reference, locally
written, no upstream file). All three documented a **third-party tool** rather than the OS,
which is exactly what the core is not for.

The 2026-08-02 note held the first two back because this repo's own docs cited them as the
canonical mechanism. Those citations are now patched to the framework's own doctrine
instead: coordination inside a session belongs to the host engine (`systems/engine.md`,
`systems/swarm-harness.md`), hook *policy* — staged per pack, never auto-wired — lives in
`systems/packs.md`, and skill authoring is the native `skill-builder` above.

The intended endpoint was a `claude-flow` pack replacing them by mount. **Verified 2026-08-29:
that pack cannot exist** — 359 `SKILL.md` files at 282 unique names, and a
`.claude-plugin/plugin.json` that declares `mcpServers` with no `skills[]` paths, so the
mount resolves to zero skills. It is a CLI ecosystem with its own installer, recorded under
"Not packs" in `systems/packs.md` and de-listed from the registry. Install it upstream,
opt-in, outside this repo.

## Removed, 2026-08-02

`agentdb-*` (5), `v3-*` (9), `flow-nexus-*` (3), `github-*` (5), `sparc-methodology`,
`swarm-advanced`, `stream-chain`, `pair-programming`, `verification-quality`,
`reasoningbank-agentdb`, `reasoningbank-intelligence`, `browser` — 30 skills, all
[claude-flow / Ruflo](https://github.com/ruvnet/claude-flow) origin, MIT, zero
cross-references elsewhere in this repo. Meta-os doesn't repackage third-party skills
with provenance tracking — it now ships without them. If you want that tooling in an
instance, install claude-flow/Ruflo through its own canonical installer (`ruflo init` /
`npx @claude-flow/cli@latest init`), opt-in, outside this repo — not vendored here.

## Framework docs

`systems/`, `templates/`, `agents/_index`, `memory/` conventions, `CLAUDE.md`, and all
`_index.md` files are **original** to this project (MIT). The three-layer model follows
[chaseAI's Agentic OS](https://www.chaseai.io/blog/agentic-os-skill-backbone-not-dashboard)
(concept attribution, no code); the memory flow follows Karpathy's `raw → wiki → output`
LLM-wiki pattern.

## Maintenance rules

- **Adding a skill:** record its origin + license here in the same commit. No skill enters
  `skills/` without a provenance row.
- **Prefer a mount to a copy.** If a procedure already exists upstream, the answer is a pack
  in `systems/packs.yaml`, not a vendored file — vendoring buys a maintenance burden and a
  provenance problem in exchange for a local copy that ages. `graphify` remains the one
  vendored exception, and only because it ships a real update path (below).
- **Vendored upstreams** (graphify) are snapshots — local edits are allowed
  (e.g. our `agile-*` parameterization), but note significant divergence in the table.
- Third-party copyright notices must be preserved in [LICENSE](LICENSE).
