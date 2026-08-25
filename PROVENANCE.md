# Provenance & Attribution

Origin and license of every skill in `skills/`. The repository as a whole is MIT
([LICENSE](LICENSE)); third-party-derived content remains under its original MIT copyright,
noted below. Last verified: 2026-08-02.

## Skill provenance

| Skill(s) | Origin | License | Notes |
|----------|--------|---------|-------|
| `hooks-automation`, `swarm-orchestration`, `skill-builder` | [claude-flow / Ruflo](https://github.com/ruvnet/claude-flow) — rUv (ruvnet) | MIT | **Held back, 2026-08-02** — this repo's own docs (`agents/_index.md`, both `templates/skill-*.md`, `pack-builder`, `systems/interface-extensions.md`) still point to these as the canonical mechanism for coordination / hooks / skill-authoring. Kept as a flagged exception until a native replacement (or a decision to patch those docs) lands — not because they're exempt from the strip below. |
| `graphify` | [Graphify Labs](https://github.com/safishamsi/graphify) · [graphify.net](https://graphify.net) — safishamsi | MIT | Vendored at v0.9.5 (2026-07-04). Update via `pip install -U graphifyy && graphify install --platform claude` — writes through the `~/.claude/skills/graphify` symlink into this repo |
| `agile-process`, `agile-swarm` | **Original** — this project; **moved** to [meta-discipline-agile](https://github.com/meta-agentic/meta-discipline-agile) | MIT | Extracted from core when the skill library was slimmed to generic-only; mount as the `agile` pack (org: meta-agentic) |
| `multi-engine` | **Original** — this project; invokes sibling [meta-cli](https://github.com/meta-agentic/meta-cli) | MIT | Standing multi-provider surface; see `systems/engine.md` |
| `bootstrap-instance` | **Original** — this project | MIT | First-run onboarding for a fresh instance repo. Written against this repo's own `systems/distribution.md` and the [meta-os-instance-template](https://github.com/meta-agentic/meta-os-instance-template); added 2026-07-04. No upstream, no third-party copyright notice. |
| `pack-builder` | **Original** — this project | MIT | The pack-authoring meta-discipline; written against `systems/packs.md` + `systems/pack-strategy.md` and ships the `resources/discipline-pack/` skeleton. Added 2026-07-10. No upstream, no third-party copyright notice. (Previously only mentioned in the `hooks-automation` row's prose — that is not a row.) |
| `infoviz` | **Original** — this project; concept attribution only | MIT | Chooses the visual form before anything is drawn. Synthesised from published literature (Kirk; Cleveland & McGill; Munzner; Bertin; the FT *Visual Vocabulary*; Lima), cited in `references/bibliography.md` — no code or text vendored. Added 2026-07-20. No upstream repo, no third-party copyright notice. |
| `ruflo-setup` | **unknown — needs owner confirmation** | unknown — MIT if claude-flow-derived | Documents the third-party [claude-flow / Ruflo](https://github.com/ruvnet/claude-flow) CLI. The repo establishes only *how it arrived*: added 2026-08-01, "consolidates the ruflo/claude-flow CLI quick-reference and install steps into one shared skill instead of duplicating the same boilerplate across every instance's `CLAUDE.md`". That does not establish whether the command reference itself was copied from upstream docs, and it survived the 2026-08-02 strip of all claude-flow-origin skills with no recorded reason — unlike the three explicitly held back above. **Owner must decide: original write-up (→ mark Original), or upstream-derived (→ record the origin and check [LICENSE](LICENSE)).** Not guessed here on purpose. |

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
- **Vendored upstreams** (claude-flow, graphify) are snapshots — local edits are allowed
  (e.g. our `agile-*` parameterization), but note significant divergence in the table.
- Third-party copyright notices must be preserved in [LICENSE](LICENSE).
