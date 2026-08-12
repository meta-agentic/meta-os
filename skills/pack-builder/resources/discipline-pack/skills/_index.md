---
type: index
tags: [os, skills, pack, <pack>]
---
# <pack> pack — skills

Each skill is an *executable discipline*: a method + a standard of rigor + a checkable
artifact. <Describe the pack's structure: which skills form the method spine — the
cross-cutting reasoning applied in every branch — and which are branch disciplines that
invoke the spine within one area. Name any pack whose skills are reused rather than
duplicated.>

| Skill | Discipline | Checkable output |
|-------|------------|------------------|
| [[skills/<skill-a>/SKILL\|<skill-a>]] | <the method it codifies> | <named ledger> |
| [[skills/<skill-b>/SKILL\|<skill-b>]] | <…> | <named ledger> |

Config knobs in `pack.yaml`; profiles in `profiles/`. See `README.md`.

<!--
  Required by the meta-os convention that every folder carries its own _index.md.
  Add a row when you add a skill — this table is what an agent reads on entering the
  folder, so a missing row means a skill nobody finds.

  If the pack gates any skill behind an opt-in switch, add a "Switch (default)" column
  and say so here: mounting a pack must never silently enable a costly practice.
-->
