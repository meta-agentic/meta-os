# Pitfall catalogue

Each entry: the mistake, *why* it misleads (with evidence where the literature is precise), and the fix. Screen every chart against this list before shipping. Distilled from Kirk (Ch.1 deceptions), Stephen Few (*Common Pitfalls of Dashboards*; *Show Me the Numbers*), Cleveland & McGill, Correll et al. (2020), Crameri et al. (2020), and the From-Data-to-Viz caveat list.

## Encoding / axis integrity

**Truncated value axis on length marks.** Bars/areas encode magnitude by length, so a non-zero baseline lies about ratios. Few's quantified example: a bar axis starting at $5M (not $0) made revenue look ~4× cost when it was <2×.
→ **Fix:** zero baseline for all bar/area charts. *Nuance:* Correll et al. (2020) showed y-axis truncation exaggerates perceived effect size **even on line charts**, and even when readers correctly read the numbers — and that "broken-axis" glyphs and gradient fades do **not** reliably fix it. So for line/scatter (position marks), don't truncate carelessly: choose the range against the *meaningful effect size* for the data and disclose it. Reject both dogmas ("always zero" and "zero is optional") in favor of a deliberate, disclosed choice.

**Dual / secondary y-axes.** Two independent scales let you slide two series until they appear correlated — the correlation is an artifact of scaling choices.
→ **Fix:** two aligned panels (small multiples) sharing the x-axis, or index both series to a common base (=100 at t₀).

**Aspect-ratio manipulation.** Stretching/squashing a line chart inflates or flattens perceived slope. Kirk lists it among core deceptions.
→ **Fix:** choose ratio honestly; "bank to 45°" for the average slope of the trend you're reading.

**Inaccurate quantitative encoding generally** (Few pitfall #8): sizing bubbles by radius instead of area (quadratic exaggeration), non-proportional icons, mismatched bin widths.
→ **Fix:** encode by area for size marks; equal bins; proportional everything.

## Chart-type misuse

**Pie chart misuse.** Angle/area are low on the perception hierarchy, so pies are read inaccurately; they fail as soon as slices are similar or numerous, or when comparison across pies is needed. A pie whose slices don't sum to 100% is "effectively corrupt" (Kirk). Few: if you must read the slice labels to compare, a bar would have been clearer.
→ **Fix:** bar/lollipop for comparison; reserve pie for 2–3 slices, one moment, where only the gross split matters.

**Sankey for the wrong job.** Great for one-way stage-to-stage flow; wrong for category comparison, time series, correlation, geography, or bidirectional/decision logic. Clutters past ~15–20 nodes/stage.
→ **Fix:** match the tool to the task (see complex-data); cap nodes/stage at ~10.

**Node-link "hairball" for dense graphs.** Force-directed layouts collapse into unreadable tangles past a couple dozen dense nodes.
→ **Fix:** adjacency matrix for large/dense graphs (matrices win on most tasks >~20 nodes); keep node-link only for small graphs or path-following tasks.

**Radar/circular charts for non-cyclical data.** Cyclicality doesn't imply a circular form; radar areas are hard to compare and their area exaggerates (Few, on Abela's folly).
→ **Fix:** grouped bar or parallel coordinates for multivariate comparison; reserve circular forms for genuinely cyclic structure and trained audiences.

**3D on 2D data.** Depth occludes, foreshortens, and adds no information; perspective distorts bar heights and pie slices.
→ **Fix:** 3D only for three genuine spatial data dimensions. Otherwise flat.

## Color

**Rainbow / jet colormap for quantitative data.** Not perceptually uniform — equal data steps map to unequal perceived steps, and the lightness bands invent false boundaries; false-coloring can introduce visual errors up to ~7.5% of the data range. Excludes CVD readers (red–green adjacency). Rainbow misuse is rampant: in 997 hydrology papers, 23.7% had ≥1 rainbow figure; color problems rose from ~20% (2005) to 47% (2020) in one journal (Crameri et al. 2020).
→ **Fix:** perceptually-uniform sequential ramps (viridis, plasma, Crameri's scientific colormaps); diverging ramp around a meaningful midpoint; test with a CVD simulator and in grayscale. *Honest nuance:* the research isn't unanimous — multi-hue maps can aid fine gradient discrimination for some high-spatial-frequency value tasks (Reda et al.) — but the default for quantitative encoding should still be perceptually uniform.

**Meaning in hue alone.** ~8% of men / ~0.5% of women can't reliably separate red–green; red/yellow/green status encodings exclude them (Few).
→ **Fix:** redundant encoding — pair hue with label, shape, position, or icon.

**Misusing/overusing color** (Few pitfall #12): saturated color everywhere leaves nothing to highlight.
→ **Fix:** neutral by default; one accent reserved for the focus.

## Data honesty

**Unnormalized choropleth.** Coloring regions by raw count re-draws population/area, not the phenomenon.
→ **Fix:** map a rate/per-capita/density; consider hexbin or cartogram to counter area bias.

**Overplotting / spaghetti charts.** Too many points or lines overlap into an unreadable mass.
→ **Fix:** small multiples, transparency/alpha, density/hexbin, sampling, or highlight-one-dim-the-rest.

**Cherry-picked range / baseline** (temporal): starting the window at a convenient date to imply a trend.
→ **Fix:** show enough history for context; disclose the window.

**Simpson's-paradox aggregation:** an aggregate trend that reverses within subgroups.
→ **Fix:** disaggregate; show groups (small multiples) when the pooled number could mislead.

## Dashboard-specific (Few's 13)

Few's thirteen common dashboard pitfalls, condensed: (1) exceeding a single screen; (2) inadequate context for the numbers; (3) excessive detail/precision; (4) expressing measures indirectly; (5) inappropriate display media (wrong chart for the data); (6) meaningless variety (different chart types for variety's sake); (7) poorly designed display media; (8) inaccurate encoding (e.g. truncated bars); (9) poor arrangement (most-important not most-prominent); (10) ineffective highlighting; (11) useless decoration/chartjunk; (12) misusing/overusing color; (13) unappealing visual display.
→ Dashboards are for **at-a-glance monitoring on one screen** (Few's definition). Every widget must earn its pixels against that job: right chart, enough context, the important thing most prominent, color spent only to highlight.

## Meta-pitfall: aesthetics over insight

The signature failure of "beautiful" data art (and of network-viz especially, per critiques of Lima): visually striking images that answer no question. Kirk's gate puts **trustworthy and accessible before elegant** for exactly this reason.
→ **Fix:** state the reader's question first; if the gorgeous chart doesn't answer it, it's decoration. Ship the one that answers the question.
