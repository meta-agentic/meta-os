# Chart selection — data relationship → form

The reliable way to choose a chart is **not** to browse a gallery of shapes. It is to name the *relationship in the data* and the *task*, then let those select the form. Two complementary taxonomies do this; use whichever fits your head better. They agree far more than they differ.

## Primary axis: the FT *Visual Vocabulary* — nine data relationships

The Financial Times Visual Journalism team's *Visual Vocabulary* organizes charts by **the relationship you want to show**, not by appearance. It was inspired by Schwabish & Ribecca's *Graphic Continuum* and is meant as a chart-*literacy* tool — recognizing when a form fits — not a construction tutorial.

| Relationship | Reader's question | First-choice forms | Notes |
|---|---|---|---|
| **Deviation** | How far from a reference/zero/target? | diverging bar, diverging stacked bar, surplus/deficit line | Anchor on a meaningful zero; color the two directions differently. |
| **Correlation** | Do two+ variables move together? | scatter, bubble (3rd var = size), connected scatter, XY heatmap | Beware inferring cause. Add a trend line only if honest. |
| **Ranking** | What's the order? | ordered horizontal bar, lollipop, dot/dumbbell, slope | **Always sort by value.** Horizontal bars for long labels. |
| **Distribution** | How are values spread? | histogram, box, violin, strip/beeswarm, cumulative curve | Show the shape, not just a mean. Box hides modality; violin/strip reveal it. |
| **Change over time** | What's the trend/trajectory? | line, area (part-to-whole over time), candlestick, connected scatter, slope | Time on x. One line reads cleanly; >5 lines → small multiples. |
| **Magnitude** | Which is bigger, by how much? | bar, lollipop, grouped bar, isotype | Length on a common scale. Avoid area/bubble when the exact value matters. |
| **Part-to-whole** | How does the total split? | stacked bar, single stacked bar, treemap (nested), pie (only 2–3 slices) | Pie is legitimate only for a couple of slices at one moment; otherwise bar/treemap. |
| **Spatial** | Where, geographically? | choropleth, symbol map, flow map, cartogram, hexbin | Normalize choropleths (rate, not count). See complex-data. |
| **Flow** | How do quantities move between states? | Sankey/alluvial, chord, network, waterfall | Width = magnitude. See complex-data for node limits. |

The resource also covers cross-cutting concerns (uncertainty, animation, interactivity, map projections, colour) — treat those as design-layer decisions, not chart picks.

## Secondary axis: Kirk's CHRTS — five chart families

Kirk's handbook profiles ~40 chart types grouped into five families **by analytic task** (2016 ed., p.158). This is a useful coarse filter — decide the family, then pick within it.

- **C — Categorical**: comparing categories and the distribution of quantitative values across them. (bar, dot plot, histogram, box, heatmap)
- **H — Hierarchical**: part-to-whole and nested structure. (stacked bar, treemap, sunburst, icicle, circle packing)
- **R — Relational**: correlations and connections. (scatter, bubble, connected scatter, network, chord)
- **T — Temporal**: change and trend over time. (line, area, slope, streamgraph, horizon, candlestick, calendar heatmap)
- **S — Spatial**: mapping patterns via overlays and distortions. (choropleth, symbol map, flow map, cartogram, dot-density)

CHRTS and the FT nine map cleanly onto each other (Categorical↔ranking/magnitude/distribution, Hierarchical↔part-to-whole, Relational↔correlation/flow, Temporal↔change-over-time, Spatial↔spatial). Kirk frames chart choice as a **data + audience** decision delivered through a "chart gallery."

## Task-conditioned encoding evidence (why the defaults are what they are)

From the graphical-perception literature (Cleveland & McGill 1984; Heer & Bostock 2010; collated by Zeng & Battle 2023 across 59 studies / 10 tasks):

- **No single chart type wins every task.** Bar charts lead for the majority of tasks (cluster, filter, sort, find-extremum, aggregate, and reading distributions); **scatterplots** win for *correlate* and *find-anomalies*; **parallel coordinates** win for multivariate cluster/range tasks.
- **Bar-vs-pie is task-dependent, not absolute.** Bars beat pies for *sort* and *find-extremum*; pies can match or beat bars for a single *retrieve-value / part-of-whole* read. Condition your rule on the task, not the chart.
- **Bars carry a documented systematic perceptual bias** (viewers misjudge within-bar positions); **point marks show none.** When precision at the value level matters more than magnitude gist, prefer dots/points.
- The canonical effectiveness order for **quantitative** encoding (Cleveland & McGill, extended by Mackinlay): **position(x)=position(y) > length > angle/slope > area > color-saturation > color-hue.** For **nominal** data the order flips toward spatial region and hue.

## On chart-chooser flowcharts (Abela) — use as a thought-starter, cite the critique

Abela's *Chart Chooser* branches from one question ("what do you want to show?") into four purposes — **Comparison, Distribution, Composition, Relationship** — then to a specific chart. It is widely reproduced and genuinely useful for *starting* a decision; Abela himself titles it a "Thought-Starter."

But know its documented flaws before leaning on it (Stephen Few, *"Abela's Folly"*):
- The four categories **aren't parallel** — *comparison* and *relationship* are properties of almost every chart, so they don't cleanly partition the space.
- Specific mis-recommendations: scatter/3D-area filed under *Distribution* (they show correlation); circular/radar area pushed for "cyclical" data (cyclicality doesn't imply a circular form and radar is rarely effective); pie recommended for share-of-total where a bar reads better.
- Few's pedagogical point: **single-page choosers let novices follow rules without learning the principles.** Use the chooser to generate candidates, then justify the pick perceptually.

Other function-first choosers in the same lineage (all catalogued by Cool Infographics / Randy Krum): the **Graphic Continuum** (Schwabish & Ribecca, 90+ types / 6 categories), **Data-to-Viz** (decision tree from data format: numeric / categoric / num+cat / maps / network / time-series, each with a caveats list), the **DataViz Catalogue** (Ribecca, datavizcatalogue.com, browsable by function), and **From Data to Viz**'s ~37-item caveat list. The dominant structuring principle across all of them is **task/data-question**, not chart appearance — which is why this skill leads with the relationship, not the shape.

## Decision recipe

1. **Name the relationship** (the nine) and the **task verb** (compare, rank, track, correlate, locate, decompose, trace-flow, find-extremum/anomaly).
2. **Check data types** — how many quantitative fields, how many categories, is there time or geography?
3. **Pick the highest-accuracy encoding** the task allows (position/length first).
4. **Count the series/categories.** >~7 categories or >~5 time series usually means: sort + top-N + "other", or switch to small multiples.
5. **Name the likely pitfall** for that form (see `pitfalls.md`) and pre-empt it.
6. Hand color/style to `dataviz`.
