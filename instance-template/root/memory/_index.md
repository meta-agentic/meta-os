---
type: index
tags: [os, memory, layer2]
---
# Layer 2 — Memory

The knowledge base. One directional flow, borrowed from Karpathy's LLM-wiki:

```
raw  →  wiki  →  output
capture   refine    deliver
```

| Stage | Folder | Rule |
|-------|--------|------|
| **raw** | [[memory/raw/_index\|raw/]] | Cheap, disposable captures & Claude outputs. Never cited as ground truth. |
| **wiki** | [[memory/wiki/_index\|wiki/]] | Refined, linked, indexed reference. The durable knowledge. |
| **output** | [[memory/output/_index\|output/]] | Finished deliverables — docs, decks, reports. |

## Promotion — the one discipline that matters

Knowledge is only trustworthy after it's **promoted**: someone (human or agent) takes a
`raw/` capture, cleans it, links it into the graph, gives it front-matter, and moves it to
`wiki/`. Un-promoted notes stay in `raw/`. This keeps the knowledge base honest.

Use [[skills/graphify/SKILL|graphify]] over `wiki/` to see the knowledge graph and find gaps/orphans.

## Cross-vault memory

This is the meta memory. Project-local vaults can still exist and are federated by
linking, not copied — see [[vaults/_index|vaults/]]. Durable cross-project knowledge gets
promoted *here*.
