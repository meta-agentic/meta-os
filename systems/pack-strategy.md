---
type: system
tags: [os, system, packs, strategy]
---
# Pack Strategy — codified disciplines beyond software

The design thesis behind [[systems/packs|skill packs]]: *what* makes a good pack, and
*where* the real opportunity is. [[systems/packs]] is the mechanism (how packs mount and
resolve); this is the philosophy (what to put in one, and why it matters).

## A pack is a codified discipline — not merely "a process"

"If it's a process, it's a pack" is close, but process is **necessary, not sufficient**.
Look at what real packs contain: the agile pack is pure process (ceremonies, flow), but
a good engineering pack's `code-review` / `domain-modeling` skills aren't processes —
they're *judgment*: knowing what good looks like and applying it in review, not
lecturing it. The unifying trait is broader:

> **A pack = a codified discipline: a repeatable _method_ + a _standard of rigor_ +
> portability across estates.**

Process is only the *method* half. The half most skill collections forget is the *rigor
standard* — what to reject, what "done right" means, how to check yourself. That is what
makes a pack turn an agent into a *competent practitioner of X* rather than a
step-follower. The agile pack makes it run Scrum like a scrum master; a physics pack
would make it reason like a physicist (dimensional analysis, order-of-magnitude checks,
conservation laws).

### The three-part test

A candidate is a pack when it passes all three:

1. **Recognizable** — a real practitioner of the field would recognize it as "how we
   actually work."
2. **Portable** — parameterizable to any estate, not welded to one shop's specifics
   (this is what [[systems/packs]]' config/profiles enforce).
3. **Checkable** — it produces outputs a reviewer (human or agent) can verify against
   the discipline's own standard.

`agile` passes. "A pile of prompts about Python" fails — no rigor standard, nothing
checkable.

## The opportunity — evidence-disciplined work

Every excellent pack in the ecosystem today grew out of **coding**: the well-known
third-party collections, the swarm-orchestration sets, even the official skill repos.
That world is ~99% software engineering plus generic productivity. So the white space is
not "some other niche" — it is *systematic*:

> Every rigorous, evidence-disciplined field has a method and a standard of rigor, and
> almost none have been codified as agent packs.

And meta-os is built to serve exactly those fields, because its differentiators are not
coding features — they are **structural provenance** (the public-safe boundary; see
`PROVENANCE.md` and [[systems/distribution]]), the **`raw → wiki → output` memory
discipline** ([[systems/memory-layer]]), the **knowledge graph** ([[skills/graphify/SKILL|graphify]]),
and **parameterized packs**. Those are precisely what *citation-heavy, audit-heavy,
reproducibility-heavy* disciplines need — and precisely what code-born skill collections
don't provide, because in software, provenance and citation aren't the point. In science,
systems engineering, and regulated industries, they are the *whole game*.

So the niche has a name: **evidence-disciplined knowledge work.** meta-os's substrate is
a structural advantage there that a coding-skills catalogue cannot match.

## Candidate slate

Not a grab-bag of industries — one *category*, entered through the discipline where our
substrate already does the heavy lifting.

| Pack | The discipline it codifies | Why meta-os specifically |
|------|----------------------------|--------------------------|
| **Research method** *(the wedge)* | Hypothesis framing, literature triage, claim-with-citation discipline, adversarially reviewing your own conclusion, reproducibility | The memory layer *already implements its backbone* — Karpathy's `raw → wiki → output` **is** capture → literature → synthesis. Most universal (every field researches) and the strongest proof that meta-os isn't for software. |
| **Quantitative rigor** | Dimensional analysis, Fermi estimation, unit discipline, error propagation, sanity-checking | A small, sharp, *cross-industry* rigor layer — physics, finance, engineering all get answer-checking for free. |
| **Systems engineering** | MBSE, requirements traceability, trade studies, V&V, FMEA | Broader than a software-only pack; traceability is native to the graph. Closest to an estate that already does systems work. |
| **Regulated domains** (pharma / clinical / legal) | GxP / protocol discipline, audit trails, cite-the-SOP / pincite-the-precedent | Structural provenance is *legally load-bearing* here — "where did this claim come from" is the deliverable. No coding-skills catalogue can offer that. |
| **Information visualization** *(the presentation end of the wedge)* | Choosing the visual form from data type × reader task × human perception; perceptual accessibility; showing uncertainty honestly; critique against the field's own standard | `raw → wiki → output` **ends in output**, and a chart is what output looks like when the reader is not reading prose. This *completes* the research-method wedge rather than competing with it — that pack governs how a claim is earned, this one governs how it is shown without being overstated, and the same provenance substrate carries the citation from evidence through to the chart. **Recognizable:** Bertin, Munzner, Kirk — the field's own method, not a tool tutorial. **Portable:** the config axes (profile, medium, accessibility, library, palette) fall out of the discipline itself, and `library: none` is a legitimate setting. **Checkable:** Cleveland & McGill ranked encoding accuracy *experimentally*, so "area where position was available" is a defect rather than a preference, and the accessibility floor is arithmetic. |

## The principle

Don't chase industries one by one — chase the **category** (evidence-disciplined work)
and lead with the **research pack**. It's the least speculative (the substrate exists),
the most universal, and it turns "meta-os is domain-agnostic" from a README claim into a
shipped artifact. Quantitative rigor is a tiny sharp second; systems engineering is the
one closest to a real estate.

This is a durable, material differentiator: the ecosystem is coding-shaped, and the
disciplines where *rigor and provenance are the product* are wide open — and are exactly
the ones meta-os was, almost accidentally, built to serve.
