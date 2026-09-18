---
name: example-method
description: "Use when a result has to be shown correct rather than asserted — whenever a calculation, a migration or a generated artefact is about to be accepted on the strength of the tool that produced it. Derives an independent second estimate and records both in a ledger that can read fail. The pack's only skill, so it defers to nothing."
---

# Example Method

A practitioner asked to accept a result does not re-run the producing tool; they obtain a
second, independent estimate and compare. The discipline is in the independence: a check
that shares the failure mode of the thing it checks is decoration. This fixture pack ships
one skill, so there is no sibling to defer to — a real pack names that boundary here.

## Method

1. **State the claim as a number with units and a tolerance.** "Roughly right" cannot be
   checked; `config.profile` decides whether an unstated tolerance is a hard reject
   (`strict`) or a recorded warning (`light`).
2. **Choose an independent estimator.** A different method, different inputs, or a
   dimensional argument — never the same pipeline run twice.
3. **Compute the second estimate and the relative deviation** between the two.
4. **Record both readings in the ledger**, including the case where they disagree.
5. **Accept, or send it back to step 1** with the disagreement named. A deviation outside
   tolerance is a result, not a retry trigger.

## The rigor standard

- **Independence is asserted with a reason.** Naming the shared input that would break the
  check is part of the check; a ledger row with no independence note is rejected.
- **A tolerance is chosen before the second estimate is computed**, never after seeing it.
- **Precision is not evidence.** Extra digits on a single estimate never substitute for a
  second one.

## Checkable output

A **verification ledger**: one row per claim, carrying the claim, both estimates, the
relative deviation, the tolerance, and the verdict. Mandatory under `strict`; advisory
under `light`.

```
claim                         primary    independent   deviation   tolerance   verdict
batch throughput (items/s)     1240        1190          4.0%        5%         pass
index rebuild wall time (s)     310         505         62.9%        10%        FAIL
```

Ship only when every row carries a verdict and every FAIL has a follow-up. A ledger in
which nothing can read FAIL has not been applied.

## Anti-patterns

- Re-running the producing tool and calling the second run an independent estimate.
- Widening the tolerance after seeing the deviation.
- Recording only the rows that passed.
- Reporting a verified result when only the arithmetic, not the model, was checked.
