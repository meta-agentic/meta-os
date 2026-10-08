---
type: index
tags: [os, systems, swarm, pipeline]
---
# systems/pipeline/ — the evidence behind the pipeline

The living page is [[systems/pipeline]]: read that. These are the analyses it rests on, kept as
they were written so the reasoning stays checkable. Where one of them and the living page
differ, the living page wins.

| File | What |
|------|------|
| `queueing.md` | Spike findings (2026-09-15): the pipeline as a Markovian queueing network. Where the ceiling is, what tokens buy, why pooling wins; the sizing rules come from here |
| `queueing-model.py` | Reproduces every table in `queueing.md` (standard library only); also the predictor the loop's reflection loads by path |
| `control-spike.md` | Spike (2026-09-16, reviewer's corrections 2026-10-07): running unattended. The token regulator, reflection, speculative execution, the latency budget and bottlenecks, and the one-night prototype |
