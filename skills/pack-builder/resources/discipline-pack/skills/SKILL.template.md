---
name: <skill-name>
description: "Use when/whenever <the trigger conditions, front-loaded with the words a user would actually type> — <the specific moves this skill makes>. <One clause naming its sibling skills and the boundary between them.>"
---

<!--
  Copy to skills/<skill-name>/SKILL.md in the pack. Named SKILL.template.md here on
  purpose: pack mounts discover SKILL.md recursively at any depth, so a live SKILL.md
  under a resources/ folder would mount as a phantom skill.

  Target 80–120 lines. Every section below is required — the ledger most of all: it is
  what makes the rigor standard auditable instead of asserted.
-->

# <Skill Name In Title Case>

<Two to four sentences: what a competent practitioner does at this moment, and why it is
a discipline rather than a lookup. Name the sibling skill this one defers to and the
boundary between them — "that skill owns X (the bookkeeping); this one owns Y".>

## Method

1. **<First move, imperative.>** <What it produces and why it comes first. Reference
   config knobs inline as `config.<knob>` where they change the procedure.>
2. **<Second move.>** <…>
3. **<Third move.>** <Cross-link a sibling skill with a wikilink where it takes over:
   [[skills/<other-skill>/SKILL|<other-skill>]].>
4. **<Fourth move.>** <…>
5. **<Final move — what gets recorded, and what signal sends you back to step 1.>**

## The rigor standard

<What "done right" means, as assertions a reviewer can hold you to. This is the half most
skill collections omit; a skill without it is a step-follower, not a practitioner.>

- **<Standard, stated as a rule.>** <What it rejects.>
- **<A claim that must be evidenced, not asserted.>**
- **<What is explicitly out of scope>** — cite the skill or pack that owns it rather than
  restating it.

## Checkable output

A **<name> ledger**: <what it records, field by field>. <State any profile-conditional
behaviour: mandatory under `<profile-a>`, advisory under `<profile-b>`.>

```
<A concrete, filled-in example — real-looking values, not placeholders. A reader must be
able to copy this shape. Show the check columns: what was verified, against what, and
whether it agreed.>
```

Ship only when <the conditions that make the ledger complete>. <Name the reading that is
a rejection rather than a pass — the ledger must be able to say no.>

## Anti-patterns

- <The tempting shortcut, and what it costs.>
- <Asserting where the standard demands evidence.>
- <Restating a sibling skill's content instead of citing it.>
- <The silent-degradation failure: producing an unchecked result that reads as checked.>
