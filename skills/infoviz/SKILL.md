---
name: infoviz
description: "Decide the RIGHT visual form for data before drawing it — chart/graph selection, information-visualization design, and complex-data (network, hierarchy, flow, temporal, geospatial) method choice. Use whenever you're about to build ANY chart, graph, diagram, dashboard, or visualization and need to pick the form (not just style it): 'which chart should I use', 'how do I visualize this network/tree/flow/funnel', 'is this the right chart', 'visualize relationships between X', 'design a dashboard widget', 'show change over time / part-to-whole / correlation / ranking / distribution'. Complements the styling-focused `dataviz` skill: this one chooses and structures the encoding; that one applies the palette and chart chrome. Grounded in Kirk (Data Visualisation), Cleveland & McGill, Munzner, Bertin, the FT Visual Vocabulary, and Lima (Visual Complexity)."
---

# infoviz — choosing and designing the visual form

This skill decides **what a visualization should be**, before anyone styles it. It encodes the practitioner canon (Andy Kirk's workflow, Cleveland & McGill's perception hierarchy, Munzner's marks-and-channels, Bertin's visual variables, the Financial Times *Visual Vocabulary*, Manuel Lima's network taxonomy) into a repeatable decision procedure.

**Scope boundary.** For *palette, color-contrast, mark styling, and chart chrome*, use the `dataviz` skill. This skill owns the upstream calls: framing the brief, choosing the encoding/form from data + task, structuring complex data, and passing a trust/accessibility/pitfall gate. Run this first; hand off to `dataviz` for the visual polish.

## The one rule that governs everything

> **Match the visual encoding to (a) the data type, (b) the reader's task, and (c) human perception — in that priority order. Form follows function, never the reverse.**

A chart is a *decision*, not a default. Never reach for a chart type because it is familiar or pretty; reach for the encoding that lets the reader's specific task be done most accurately. Kirk's nine-word definition — *"the representation and presentation of data to facilitate understanding"* — uses **facilitate** deliberately: you control the output, not the outcome. Design for the reader's act of understanding, which runs **perceive → interpret → comprehend**, with your control shrinking at each stage ([Kirk 2016](references/bibliography.md)).

## Workflow — five moves, in order

Do the "hidden thinking" (moves 1–3) before touching a chart library. Most bad visualizations are decided wrong before a single mark is drawn.

### 1. Formulate the brief
Answer, in one line each: **Who** is the audience (expert / general / self)? **Why** — is this *explanatory* (you found the story, now tell it) or *exploratory* (help the reader find their own)? **Where** does it live (report, slide, phone, dashboard, print)? **What** must the reader be able to *do* with it? The last question is the task, and the task drives the form.

### 2. Work with the data
Classify every field by measurement type — this determines which encodings are even legal:

| Type | Examples | Legal encodings (best→worst) |
|------|----------|------------------------------|
| **Nominal** (categories, unordered) | country, product, agent-id | spatial region, **hue**, shape, texture |
| **Ordinal** (ordered categories) | low/med/high, rank | **position**, size, luminance, saturation |
| **Quantitative** (numbers, ratios) | tokens, latency, count | **position on aligned scale** > **length** > angle/slope > area > luminance/saturation > hue |
| **Temporal** | timestamp, date | position on a **time axis** (horizontal by convention) |
| **Spatial** | lat/long, region | map position / geometry |

Then examine (ranges, outliers, missingness), transform (normalize, aggregate, derive), and explore before deciding the angle.

### 3. Editorial thinking
Decide the **angle** (what's the story?), **framing** (what comparison makes it land?), and **focus** (what is the *one* thing the reader should leave with?). Everything you choose to include must earn its place against that focus; everything else is noise. "Clarify complexity rather than simplify it" ([Kirk](references/bibliography.md)).

### 4. Choose the form → see `references/chart-selection.md`
Pick the **data relationship** you're showing, then let it and the data shape select the chart. The primary axis is the FT *Visual Vocabulary*'s nine relationships:

**deviation · correlation · ranking · distribution · change-over-time · magnitude · part-to-whole · spatial · flow**

Quick defaults (full matrix + caveats in the reference file):

| You want to show… | Reach for | Not |
|---|---|---|
| **Ranking / compare categories** | horizontal bar (sorted) | pie |
| **Change over time** (continuous) | line | many pies / stacked-to-100 over time |
| **Part-to-whole**, 2–4 parts, one moment | stacked bar or single bar; pie only if ≈2–3 slices and precision doesn't matter | pie with 6+ slices |
| **Correlation** (2 quantitative) | scatter | dual-axis line |
| **Distribution** | histogram / box / strip / violin | bar of means alone |
| **Magnitude** (compare absolute size) | bar / lollipop | area/bubble when precision matters |
| **Flow / stage-to-stage quantity** | Sankey / alluvial (see complex-data) | pie |
| **Network / hierarchy / geo** | → `references/complex-data.md` | — |

For anything relational, hierarchical, temporal-at-scale, or geographic, **go to `references/complex-data.md`** — those need method selection, not a chart pick.

### 5. Design the five layers, then pass the gate → `references/design-layers.md`
Every visible decision falls in one of Kirk's five layers. Walk them as a checklist: **data representation** (marks & channels), **interactivity**, **annotation**, **colour**, **composition**. Then run the **trust / accessible / elegant** gate and the **pitfall check** (`references/pitfalls.md`) before shipping.

## Non-negotiables (violating any of these is a bug, not a taste call)

- **Bar and area charts start their value axis at zero.** Length encodes magnitude; a truncated baseline lies about ratios. (Truncation exaggerates perceived effect even on *line* charts and even when readers can read the true numbers — [Correll et al. 2020](references/pitfalls.md) — so for lines, choose the axis range deliberately and disclose it.)
- **No dual y-axes.** They manufacture correlations by letting you slide two scales independently. Use two aligned panels (small multiples) instead.
- **No rainbow / jet colormap for quantitative data.** Not perceptually uniform, not colorblind-safe. Use a perceptually-uniform sequential ramp (viridis) or a diverging ramp around a meaningful midpoint. (Hand palette choice to `dataviz`.)
- **No 3D on 2D data.** Depth distorts and occludes unless you have three genuine data dimensions that must be shown together.
- **Prefer position and length over angle, area, and color** whenever the reader must judge quantity accurately (Cleveland & McGill). This is why bars beat pies for comparison and why bubble sizes are for gist, not values.
- **Color must survive grayscale and CVD** (~8% of men). Never encode meaning in hue alone; make it redundant with position, label, or shape.
- **Sort by value, not alphabetically,** whenever ranking is the point.
- **Label directly** where you can; make the reader's eye travel less. Reserve legends for when direct labels won't fit.

## Reference files (load on demand)

- **`references/chart-selection.md`** — the full data-relationship → chart matrix, the FT *Visual Vocabulary* nine categories, Kirk's CHRTS five families, and why chart-chooser flowcharts (Abela) are a *starting point*, not an authority.
- **`references/complex-data.md`** — networks (node-link vs adjacency matrix, the >20-node rule), hierarchies (tree / treemap / icicle / sunburst), flows (Sankey / alluvial / chord), temporal-at-scale, and geospatial (choropleth normalization, cartograms), plus Lima's syntax-of-networks taxonomy and Börner's science-mapping.
- **`references/design-layers.md`** — Kirk's five design layers as working checklists, the marks-and-channels model, preattentive attributes, and annotation/composition patterns.
- **`references/pitfalls.md`** — the catalogue: truncated axes, dual axes, pie misuse, rainbow colormaps, overplotting/spaghetti, unnormalized choropleths, aspect-ratio manipulation, 3D, meaningless variety — each with the evidence and the fix.
- **`references/bibliography.md`** — annotated canon: Kirk, Cleveland & McGill, Bertin, Munzner, Wilkinson, Few, Tufte, Lima, Börner, FT *Visual Vocabulary*, plus the practitioner guides (Data-to-Viz, DataViz Catalogue, Cool Infographics).

## How to answer a "what chart should I use?" request

1. Restate the **task** and the **data types** in one sentence each. If they weren't given, ask — the answer changes entirely between "compare 5 categories" and "track 5 series over time."
2. Name the **data relationship** (the nine).
3. Recommend **one** primary form and say why in perceptual terms ("bar, because the task is ranking and length on a common scale is the most accurately-read encoding"). Offer at most one alternative.
4. Flag the **pitfall** most likely to bite this specific chart.
5. Hand off styling to `dataviz`.
