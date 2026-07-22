# Provenance & Attribution

Origin and license of every skill in `skills/`. The repository as a whole is MIT
([LICENSE](LICENSE)); third-party-derived content remains under its original MIT copyright,
noted below. Last verified: 2026-07-04.

## Skill provenance

| Skill(s) | Origin | License | Notes |
|----------|--------|---------|-------|
| `agentdb-*` (5) | [claude-flow / Ruflo](https://github.com/ruvnet/claude-flow) — rUv (ruvnet) | MIT | Installed via the claude-flow ecosystem |
| `v3-*` (9) | [claude-flow / Ruflo](https://github.com/ruvnet/claude-flow) | MIT | claude-flow v3 implementation skills |
| `flow-nexus-*` (3) | [claude-flow / Ruflo](https://github.com/ruvnet/claude-flow) | MIT | Flow Nexus platform skills |
| `github-*` (5) | [claude-flow / Ruflo](https://github.com/ruvnet/claude-flow) | MIT | GitHub swarm-coordination skills |
| `sparc-methodology`, `swarm-advanced`, `swarm-orchestration`, `stream-chain`, `hooks-automation`, `pair-programming`, `verification-quality`, `reasoningbank-agentdb`, `reasoningbank-intelligence`, `browser`, `skill-builder` | [claude-flow / Ruflo](https://github.com/ruvnet/claude-flow) | MIT | Core claude-flow skill set |
| `graphify` | [Graphify Labs](https://github.com/safishamsi/graphify) · [graphify.net](https://graphify.net) — safishamsi | MIT | Vendored at v0.9.5 (2026-07-04). Update via `pip install -U graphifyy && graphify install --platform claude` — writes through the `~/.claude/skills/graphify` symlink into this repo |
| `agile-process`, `agile-swarm` | **Original** — this project; **moved** to [meta-os-agile-pack](https://github.com/mova77/meta-os-agile-pack) | MIT | Extracted from core when the skill library was slimmed to generic-only; mount as the `agile` pack |
| `multi-engine` | **Original** — this project; invokes sibling [meta-cli](https://github.com/meta-aos/meta-cli) | MIT | Standing multi-provider surface; see `systems/engine.md` |

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
