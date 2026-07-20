# Annotated bibliography — the canon behind this skill

Grouped by role. Each entry: what it is, and the one thing to take from it. Sources marked ✚ are the anchor references this skill was built on; ★ are foundational empirical/theoretical works.

## Practitioner methodology (the workflow)

**✚ Andy Kirk — *Data Visualisation: A Handbook for Data Driven Design*** (SAGE; 1st ed. 2016, 2nd 2019, 3rd 2024).
The spine of this skill. Defines dataviz in nine words ("the representation and presentation of data to facilitate understanding"), models understanding as *perceive → interpret → comprehend*, and structures the craft as a staged workflow: **Hidden Thinking** (Formulating the Brief → Working With Data → Editorial Thinking) then **Design Thinking** across five layers (data representation, interactivity, annotation, colour, composition). Chart taxonomy **CHRTS** = Categorical, Hierarchical, Relational, Temporal, Spatial (~40 chart types). Three ranked principles — **trustworthy > accessible > elegant** — from Dieter Rams. *Take:* decide the chart from data + audience + task, and do the thinking before the drawing.

**Stephen Few — *Show Me the Numbers* / *Information Dashboard Design* / *"Common Pitfalls of Dashboards"* / *"Abela's Folly"*** (Perceptual Edge).
The rigorous, opinionated practitioner. Dashboards = at-a-glance monitoring on a single screen; his 13 dashboard pitfalls are a working QA list. His critique of Abela's chart chooser is the canonical caution against rule-following choosers. *Take:* the pitfall lists and the "learn principles, don't follow flowcharts" stance.

**Alberto Cairo — *The Truthful Art* / *The Functional Art*.**
Bridges journalism and perception; "basic principles of visualization." *Take:* truthfulness and functionality as first-order design goals, not add-ons.

## Perceptual & theoretical foundations

**★ Cleveland & McGill (1984), "Graphical Perception," *JASA*.**
The first rigorous experiments on how accurately people decode encodings. Establishes the **effectiveness hierarchy**: position (aligned) > length > angle/slope > area > color-saturation > color-hue for quantitative data. Replicated by **Heer & Bostock (2010)**. *Take:* the hierarchy is empirical, not opinion — prefer position and length.

**★ Jacques Bertin — *Sémiologie Graphique* (1967).**
The "visual variables": position, size, shape, value(luminance), color(hue), orientation, texture — and which suit ordered vs. selective (categorical) data. The theoretical root of marks-and-channels. *Take:* match variable to data's measurement level.

**★ Jock Mackinlay (1986), "Automating the Design of Graphical Presentations."**
Extended Cleveland & McGill's ranking to nominal/ordinal data and built APT, an automated design system reasoning *compositionally* about encodings rather than picking chart types. Ancestor of modern viz recommenders. *Take:* charts can be *derived* from encoding rules, not chosen from a catalog.

**★ Tamara Munzner — *Visualization Analysis & Design* (2014).**
The standard graduate framework: **what–why–how** (data / task / idiom), "Marks and Channels" (Ch.5), "Arrange Tables" (Ch.7). Ranks channels by the task they serve. *Take:* separate *what* you have, *why* you're showing it, and *how* to encode it — decide in that order.

**★ Leland Wilkinson — *The Grammar of Graphics* (1999).**
A statistical graphic = structured components (data, marks, scales, coordinates, encodings). Operationalized as Wickham's **Layered Grammar of Graphics** → ggplot2 / Vega-Lite. *Take:* build charts compositionally from encodings, not from a fixed type list.

**★ Edward Tufte — *The Visual Display of Quantitative Information* (1983).**
Data-ink ratio, chartjunk, small multiples, "graphical integrity," the lie factor. *Take:* maximize the share of ink that encodes data; comparison via small multiples.

**Zeng & Battle (2023, CHI), "A Review and Collation of Graphical Perception Knowledge."**
Collates 59 perception studies across 10 tasks into a machine-readable knowledge base for viz recommendation. *Take:* effectiveness is **task-conditioned** — no chart wins everything; bars lead most tasks, scatter for correlation/anomaly, parallel coords for multivariate.

## Complex data — networks, hierarchies, science maps

**✚ Manuel Lima — *Visual Complexity: Mapping Patterns of Information* (2011)** and **visualcomplexity.com** (archive of 700+ network projects).
First systematic attempt at typologies and principles for **network visualization**. "The Syntax of a New Language" classifies ~15 depiction types (arc, radial convergence/implosion, rhizome, flow, sphere, centralized/distributed nets…). Traces the shift from **trees to networks**. *Take:* a vocabulary of network forms — and the warning that a network viz must be *relevant*, not just beautiful.

**★ Ghoniem, Fekete & Castagliola (2005), "On the Readability of Graphs Using Node-Link and Matrix-Based Representations," *Information Visualization*.**
The empirical basis for node-link-vs-matrix: **matrices beat node-link on most tasks once graphs exceed ~20 vertices / get dense; node-link wins for path-following at all sizes.** Corroborated by **Keller, Eckert & Clarkson (2006)** for engineering DSMs. *Take:* the size/density/task rule for choosing graph representation.

**✚ Katy Börner — *Atlas of Science: Visualizing What We Know* (2010/11)**, companion to the *Places & Spaces: Mapping Science* exhibition.
Science mapping within **scientometrics**: map the structure and evolution of knowledge. *Take:* use a **stable reference system / reusable base map** so successive/animated views stay comparable; separate base-layout from overlay.

## Chart-selection frameworks & practitioner guides

**✚ Financial Times — *Visual Vocabulary*** (github.com/Financial-Times/chart-doctor).
Chart-selection reference organized by **data relationship**: deviation, correlation, ranking, distribution, change-over-time, magnitude, part-to-whole, spatial, flow. Poster in multiple languages. Inspired by the Graphic Continuum. *Take:* the nine relationships — the primary axis for choosing a form.

**Abela — *Chart Chooser* ("Thought-Starter").**
Four purposes (Comparison, Distribution, Composition, Relationship) → chart. Popular but flawed (see Few's "Abela's Folly"): non-parallel categories, some perceptually poor recommendations. *Take:* use to *generate* candidates; justify the pick perceptually; cite the critique.

**Schwabish & Ribecca — *Graphic Continuum*** (90+ types, 6 categories); **Ribecca — *Data Visualisation Catalogue*** (datavizcatalogue.com, browse by function); **Holtz & Healy — *From Data to Viz*** (data-to-viz.com; decision tree from data format + a ~37-item caveat list).
Function-first choosers. *Take:* all structure advice by data-question/task, not appearance — corroborating this skill's approach.

**✚ Randy Krum — *Cool Infographics* dataviz-guides** (coolinfographics.com/dataviz-guides).
Curated meta-index (~27 entries) of choosers, cheatsheets, and checklists — incl. Kirk's Chartmaker Directory, Few's Graph Selection Matrix, the Evergreen/Emery Data Visualization Checklist (24 items). *Take:* the landscape of how existing guides organize their advice — overwhelmingly by task.

**✚ Andrew Vande Moere — *infosthetics.com*.**
Long-running blog on **information aesthetics** — the tension between data art and functional visualization. *Take:* aesthetics and function are a spectrum; be explicit about where a given piece sits and don't let beauty override the reader's question.

## Empirical notes on specific pitfalls

- **Correll, Bertini & Franconeri (2020, CHI), "Truncating the Y-Axis."** Truncation exaggerates perceived effect on *line and bar* charts, persists even when values are read correctly, and break-glyphs don't fix it. Rejects both "always zero" and "zero optional" dogmas.
- **Crameri, Shephard & Heron (2020), *Nature Communications*, "The misuse of colour in science communication."** Rainbow maps aren't perceptually uniform, exclude CVD readers, and are pervasive; prescribes perceptually-uniform scientific colormaps + CVD/grayscale testing.
