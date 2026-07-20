# The five design layers — working checklists

Kirk separates **representation** (the chart-type/encoding choice) from **presentation** (every other visible decision) and partitions the work into **five layers**. Walk them in order; each is a place where a good chart is won or lost. (Kirk 2016, Chapters 6–10.)

## Layer 1 — Data representation (marks & channels)

This is the encoding itself: the **marks** (geometric primitives — points, lines, areas/bars) and the **channels** (attributes that vary — position, length, size, angle, color, shape, texture) that carry the data (Munzner; Bertin's "visual variables").

Checklist:
- [ ] **Highest-accuracy channel for the primary quantity.** Position on a common scale first, then length. Demote to area/angle/color only for secondary or gist-level values. (Cleveland & McGill / Mackinlay hierarchy.)
- [ ] **Channel matches data type.** Quantitative → position/length/size ordered ramps. Nominal → hue/shape/region (unordered). Ordinal → ordered channel (position, luminance). Never encode a quantity in hue, or a category in a continuous ramp.
- [ ] **Zero baseline** for any length-based mark (bar, area). Position-based marks (dots, lines) may use a non-zero range *if chosen deliberately and disclosed*.
- [ ] **One mark per data point's identity**; don't double-encode the same variable in two channels "for emphasis" (that's meaningless variety).
- [ ] **Preattentive pop-out for the one thing that matters.** A single differing hue, size, or position is detected in <250ms without scanning. Use exactly one preattentive channel to mark the focus; if everything pops, nothing does.

**Preattentive attributes** (perceived instantly, pre-cognition): position, length, size, orientation/angle, hue, intensity/luminance, shape, enclosure, added marks, blur/motion. These are your tools for directing attention — spend them deliberately.

## Layer 2 — Interactivity

Only relevant for on-screen/exploratory work; a static explanatory chart may correctly have none.
- [ ] **Overview first, then zoom/filter, then details-on-demand** (Shneiderman's mantra) — don't make the reader interact to see the headline.
- [ ] Interaction is **additive, not load-bearing**: the default state must already tell the core story. Tooltips carry precision, not the message.
- [ ] Every interactive affordance is discoverable and reversible; hover-only reveals fail on touch and in print.

## Layer 3 — Annotation

Annotation is where a chart becomes *understandable* rather than merely correct. Often the highest-leverage layer.
- [ ] **Title states the takeaway**, not the mechanics. "Revenue tripled after launch," not "Revenue by month." (Explanatory charts should assert the angle.)
- [ ] **Direct labels** on lines/bars/points where space allows — beats a legend that forces eye round-trips.
- [ ] **Annotate the notable**: the peak, the anomaly, the threshold, the "you are here." Guide interpretation explicitly.
- [ ] **Units, scale, source, and n** are visible. Say what's excluded.
- [ ] Reference lines/bands for targets, averages, or meaningful thresholds.

## Layer 4 — Colour

*Style/palette specifics belong to the `dataviz` skill.* Here, the structural rules that are about *meaning*, not taste:
- [ ] **Color has a job or it's off.** Categorical (distinct hues, ≤~7), sequential (one hue, light→dark = low→high), diverging (two hues around a meaningful midpoint), or highlight (one accent on a neutral field). Pick the type from the data, then hand the exact ramp to `dataviz`.
- [ ] **Never meaning-in-hue-alone.** Redundant with label/position/shape so it survives grayscale and color-vision deficiency (~8% of men, ~0.5% of women).
- [ ] **Perceptually-uniform ramps** for quantitative (viridis-family); **never rainbow/jet** — it invents false boundaries and fails CVD.
- [ ] **Neutral by default, saturated only to highlight.** Most of the chart should be quiet so the focus can shout.

## Layer 5 — Composition

How the pieces sit together — layout, alignment, hierarchy, proportion.
- [ ] **Visual hierarchy matches information hierarchy** — the most important element is largest / boldest / top-left (in LTR reading order).
- [ ] **Small multiples** for comparison across a dimension: identical scales, shared axes, arranged in a meaningful order. Comparison-by-position beats comparison-by-memory.
- [ ] **Shared, consistent scales** across any panels that will be compared. Independent scales silently lie.
- [ ] **Aspect ratio** chosen honestly — "banking to 45°" aids trend reading; a stretched/squashed ratio manufactures or hides slope.
- [ ] **Alignment and a grid.** Aligned edges let the eye compare; ragged placement adds cognitive load.
- [ ] **Reduce non-data ink** (Tufte): drop chartjunk, heavy gridlines, redundant borders, backgrounds, 3D bevels. Maximize the share of ink that encodes data — but not to the point of stripping helpful annotation.

## The final gate — trust / accessible / elegant (in that order)

Kirk's three principles, derived from Dieter Rams. They are **ranked**: elegance may never undermine the two above it.

1. **Trustworthy** — honest encoding (zero baselines, no dual axes, normalized rates, disclosed exclusions), and faithful to the data. A beautiful chart that misleads is a failure. *Trust is non-negotiable and comes first.*
2. **Accessible** — the intended reader can actually decode it: readable text, CVD-safe, direct labels, appropriate complexity for the audience, works in its medium (phone/print/screen).
3. **Elegant** — no wasted ink, considered composition, aesthetic restraint that serves clarity. Earned only after 1 and 2 pass.

If a choice improves elegance at the cost of trust or access, revert it.

## Marks-and-channels quick reference (Munzner / Bertin)

| Channel | Best for | Accuracy (quantitative) |
|---|---|---|
| Position (common scale) | any quantity | ★★★★★ |
| Position (unaligned) | quantity | ★★★★ |
| Length | quantity | ★★★★ |
| Angle / slope | quantity | ★★★ |
| Area | quantity (gist) | ★★ |
| Luminance / saturation | ordinal, quantity (gist) | ★★ |
| Hue | **nominal categories** | ★ (for quantity) |
| Shape / texture | nominal categories | — |

Read top-down: give your most important quantitative variable the highest channel it can have; push nominal identity to hue/shape.
