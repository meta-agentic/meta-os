---
type: system
tags: [os, system, ontology]
---
# Ontology

The vault's implicit type system, made explicit. The machine-readable contract lives in
[[systems/ontology.yaml|ontology.yaml]]; this note is the *why* and the *rules*.

## Why an ontology at all

Front-matter `type:`, namespaced tags, and graphify's node/edge vocabulary already form a
lightweight ontology — but only by convention. Writing it down as a schema turns it into
the **contract between layer 2 (memory) and layer 3 (interface)**:

1. **Schema-driven rendering.** The [[systems/interface-layer|interface layer]] renders
   *from the ontology* — a view per note type, facets per tag namespace. New types appear
   in the UI with zero UI changes.
2. **Validation at the boundary.** Notes lint against the schema; promotion-discipline
   violations (untyped notes, missing required fields) surface instead of rotting.
3. **Agent grounding.** Agents type new notes consistently, and graphify's graph types
   align with vault types — one queryable structure, not two.

## Rules — deliberately light

- **Controlled vocabulary, not OWL/RDF.** Note types + required fields + a small relation
  vocabulary. Heavy ontology engineering is a tarpit; if a rule doesn't pay for itself in
  rendering, validation, or grounding, it doesn't go in.
- **Plain `[[wikilinks]]` stay untyped.** Typed links (`INFORMS`, `APPLIES_TO`, `RELATED`
  — canonized from [[templates/source|the source template]]) are optional signal, never a
  gate on linking.
- **Framework defines the core; instances extend.** An instance may add note types,
  fields, and tag namespaces in its own `ontology.yaml` (additive merge). It never
  removes or redefines framework entries — that would fork the contract.
- **Templates are the ontology's executable form.** Adding a note type means adding a
  template, a `note_types:` entry, and a row in [[templates/_index]] — all three or none.
- **LLM-maintained, human-approved.** Agents may propose schema changes (new type
  observed repeatedly in `raw/`, say); a human promotes them, same as any wiki note.
- **Flow entities are vocabulary, not notes.** Lanes, queues, and stages (the `flow:`
  section) are *derived* by layer 3 from their authoritative feeds — tracker/backlog
  mirror, swarm batch state, vault git history — never hand-filed as notes. A swarm lane
  ([[systems/swarm-harness]]) and the promotion pipeline ([[systems/memory-layer]]) are
  both queues; defining them once in the ontology lets one flow-metric machinery (WIP,
  queue depth, throughput, cycle time, Little's-Law ETA) cover both.
