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
