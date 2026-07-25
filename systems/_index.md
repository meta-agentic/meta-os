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
| [[systems/engine\|engine]] | Pluggable headless runtimes: Claude is the default adapter; meta-cli fan-out; run artifacts → `memory/raw/` |
| [[systems/memory-layer\|memory-layer]] | The `raw → wiki → output` discipline, promotion, and federation with project vaults |
| [[systems/config\|config]] | The three config levels (framework schema · instance estate `meta-os.config.json` · deployment) and the `meta-os.` namespace; [[systems/meta-os.config.schema.json\|meta-os.config.schema.json]] is the machine-readable contract |
| [[systems/scrum-harness\|scrum-harness]] | The agile process: backlog↔Jira, ceremonies, sprint lifecycle (driven by [[skills/agile-process/SKILL|agile-process]]) |
| [[systems/swarm-harness\|swarm-harness]] | Parallel multi-lane execution model (driven by [[skills/agile-swarm/SKILL|agile-swarm]]) |
| [[systems/ontology\|ontology]] | The vault's type system made explicit: note types, tags, relations ([[systems/ontology.yaml\|ontology.yaml]] is the machine-readable contract) |
| [[systems/interface-layer\|interface-layer]] | Layer 3 contract: what the dashboard reads, how it triggers runs, ontology-driven rendering |
| [[systems/interface-extensions\|interface-extensions]] | Layer 3 roadmap: the common agentic-dashboard widget set evaluated against the contract — verdicts, new read surfaces, phasing |
| [[systems/distribution\|distribution]] | How an instance consumes the framework: single-clone (submodule), sibling checkouts, container; why one merged repo is rejected; per-project delivery targets |
| [[systems/packs\|packs]] | Skill packs: core stays generic; domain skill sets mount as pinned pack submodules from a curated registry ([[systems/packs.yaml\|packs.yaml]]) |
| [[systems/pack-strategy\|pack-strategy]] | The thesis behind packs: a pack = a codified discipline (method + rigor + portability); the evidence-disciplined-work niche the coding-born ecosystem leaves open, and why meta-os is built to fill it |
