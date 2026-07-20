# Complex data — networks, hierarchies, flows, temporal-at-scale, geospatial

These structures aren't a chart *pick* — they need **method selection**, because the same data supports several radically different depictions and the right one depends on structure (size, density) and task. This is the domain of Manuel Lima's *Visual Complexity* (2011), Katy Börner's *Atlas of Science* (2010/11), and the empirical node-link-vs-matrix literature.

## Networks / graphs

**The core decision: node-link diagram vs. adjacency matrix.** This is empirically settled, not stylistic (Ghoniem, Fekete & Castagliola 2005, *Information Visualization*; corroborated by Keller, Eckert & Clarkson 2006):

| Situation | Use | Why |
|---|---|---|
| Small graph (**< ~20 nodes**), sparse | **Node-link** | Intuitive; readers see structure at a glance. |
| Large or **dense** graph (> ~20 nodes) | **Adjacency matrix** | Matrices beat node-link on *most* readability tasks (find neighbors, count edges, detect clusters) once graphs get big/dense — no edge crossings, no occlusion. |
| Task = **path-following** (trace a route between nodes) | **Node-link** | The one task where node-link wins at *every* size/density. Matrices are poor at paths. |
| Audience already fluent in matrices (e.g. engineering DSMs) | Matrix acceptable even when small | Familiarity conditions the choice. |

**Node-link layout** — match the layout algorithm to the underlying structure (VisualComplexity guidance):
- **Force-directed** (spring): general-purpose; reveals clusters and centrality in medium graphs. Degrades to a "hairball" when dense — that's your signal to switch to a matrix.
- **Radial / hub-and-spoke**: emphasize a central node or cyclic structure.
- **Arc diagram** (nodes on a line, arcs above): good for sequence/linear data and spotting repeats; scales better than force layouts for ordered nodes.
- **Edge bundling**: tame route-like link collections (flight maps, migrations) by grouping parallel edges.
- **Circular / chord**: fixed node ring, ribbons for edges — good for a modest number of nodes with weighted bidirectional relationships.

**Encoding inside a network** still obeys perception: position and length over angle/area; **color sparingly and always redundantly** with a label or symbol. A pretty network that doesn't answer a question is the field's signature failure mode — Lima's own principle is that network visualizations must be *relevant*, and reviewers fault the genre for "visually striking but analytically trivial" images. Don't draw the hairball; answer the question.

**Lima's syntax of networks** (*"The Syntax of a New Language"*): ~15 basic depiction types — arc diagrams, radial convergence, radial implosion, ramification, organic rhizomes, flow charts, sphere, centralized/decentralized/distributed nets, etc. Treat it as a vocabulary of options, not a ranking. The historical arc Lima draws — **from hierarchical trees to distributed networks** — is itself a modeling choice: ask whether your data is genuinely a network or a tree in disguise (trees are far easier to read).

## Hierarchies (part-to-whole, nested)

Pick by what the reader must judge:

| Task | Form |
|---|---|
| Compare leaf **magnitudes** across a big hierarchy in fixed space | **Treemap** (area = value; nesting = structure) — but area is a weak quantitative encoding, so it's for gist and space-efficiency, not precise comparison. |
| Show the **branching structure** / ancestry clearly | **Node-link tree** (dendrogram) or **indented outline** |
| Part-to-whole **with the path from root visible** | **Icicle** (rectangular, aligned — easier to compare than radial) or **sunburst** (radial, prettier, harder to compare outer rings) |
| Few levels, compact | **Nested / stacked bar** |
| Emphasize relative sizes, one level | **Circle packing** (again area-based: gist only) |

Prefer **aligned** layouts (icicle, indented tree) over **radial** ones (sunburst) when the reader must compare sizes — radial distorts by radius. Reach for radial only when the display is space-constrained or the hierarchy's cyclic/centered nature is the point.

## Flows (quantities moving between states)

| Data | Form | Watch out |
|---|---|---|
| One-way, multi-stage flow (energy, budget, user funnel, referrals) | **Sankey / alluvial** — link width = magnitude | Cluttered past ~15–20 nodes per stage; aim for **≤10 nodes/stage**. Order nodes within a stage by value. Best for *left-to-right, one-way* flows. |
| Running total with +/− steps | **Waterfall** | Not a Sankey — use when the story is accumulation/subtraction to a total. |
| Weighted relationships among a fixed set (bidirectional) | **Chord diagram** | Only for modest node counts; ribbons overwhelm quickly. |
| Bidirectional or many-to-many with logic | **Network diagram / flowchart** | Sankey is the wrong tool for decision logic or two-way movement. |

Sankey is *not* the answer for: simple category comparison (bar), time series (line/area), geography (map), correlation (scatter/heatmap). Use it only when *flow between stages* is the actual subject.

## Temporal at scale

Beyond a single line:
- **Small multiples** (a grid of identical mini-charts) — the default when you have >5 series; comparison is by position across panels, the most accurate channel. Almost always beats an overplotted multi-line "spaghetti" chart.
- **Horizon chart** — layered/folded bands pack many series into little vertical space; good for dense monitoring dashboards once the reader is trained on them.
- **Streamgraph** — stacked area around a central baseline; expressive for composition-over-time *gist* but poor for reading individual values (wiggling baselines). Aesthetic-first.
- **Calendar heatmap** — value as color over a date grid; good for daily cadence/seasonality (activity, incidents).
- **Cycle plot** — for seasonality: trend *within* each period alongside the across-period trend.

## Geospatial

- **Choropleth** (regions colored by value): **normalize first** — map a rate/density/per-capita, never a raw count, or you just re-draw population. Use a perceptually-uniform sequential ramp (or diverging around a meaningful midpoint). Region size ≠ importance (big rural areas dominate visually).
- **Symbol / bubble map**: value as marker size at points; sidesteps the area-bias of choropleths but overplots in dense cities.
- **Hexbin / grid map**: equalizes area to fight the "big empty regions shout" problem.
- **Cartogram**: deliberately distorts region size to encode the value (e.g. population); powerful but needs a familiar audience.
- **Flow map**: origin→destination lines with width = volume; edge-bundle to reduce clutter.
- Ask first whether geography is even the point. If the reader's task is *ranking* regions, a sorted bar chart is more accurate than any map — the map is for genuinely *spatial* patterns (adjacency, clustering, distance).

## Science mapping / knowledge domains (Börner)

Börner's *Atlas of Science* (companion to the *Places & Spaces: Mapping Science* exhibition) frames visualization within **scientometrics** — mapping the structure and evolution of knowledge. The transferable ideas for a complex-data widget:
- **Use a stable reference system** (a base map / coordinate space you reuse) so successive views are comparable over time — the way geographic maps share a projection.
- **Separate base map from overlay**: compute a layout once (the "map"), then overlay time slices, metrics, or subsets on it. This is exactly how to animate a knowledge/network graph without the layout thrashing between frames.
- Science maps typically encode entities (papers, authors, topics) as nodes with **position from similarity/co-citation**, size from output, and color from field — a concrete template for visualizing any corpus of related items (memories, agents, sessions) by similarity.

## Method-selection checklist

1. Is it really a network, or a **tree**? Trees read far more easily — don't over-model.
2. Network: how many nodes, how dense, and is the task **path-following**? → node-link vs matrix per the table.
3. Hierarchy: does the reader need **structure** (tree/icicle) or **magnitude** (treemap)?
4. Flow: one-way between stages (Sankey), accumulation (waterfall), or bidirectional (chord/network)?
5. Many series over time → **small multiples** before anything exotic.
6. Geographic value → **normalize**, and confirm the pattern is spatial (else use a bar).
7. Reusable/animated view → fix a **base layout** (Börner) so frames stay comparable.
