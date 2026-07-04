---
type: index
tags: [os, systems]
---
# Systems — How the OS Operates

The *how* behind the contract. [[CLAUDE|CLAUDE.md]] states the invariants; these docs hold
the procedure. Load the one you need.

| System | Covers |
|--------|--------|
| [[systems/agentic-operating-model\|agentic-operating-model]] | How work flows through the OS: skills → agents → memory; the SendMessage coordination model; when to swarm |
| [[systems/memory-layer\|memory-layer]] | The `raw → wiki → output` discipline, promotion, and federation with project vaults |
| [[systems/scrum-harness\|scrum-harness]] | The agile process: backlog↔Jira, ceremonies, sprint lifecycle (driven by [[skills/agile-process/SKILL|agile-process]]) |
| [[systems/swarm-harness\|swarm-harness]] | Parallel multi-lane execution model (driven by [[skills/agile-swarm/SKILL|agile-swarm]]) |
| [[systems/ontology\|ontology]] | The vault's type system made explicit: note types, tags, relations ([[systems/ontology.yaml\|ontology.yaml]] is the machine-readable contract) |
| [[systems/interface-layer\|interface-layer]] | Layer 3 contract: what the dashboard reads, how it triggers runs, ontology-driven rendering |
