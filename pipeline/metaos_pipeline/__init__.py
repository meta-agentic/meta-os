"""meta-os autonomous pipeline — the deterministic half of the swarm loop.

The pipeline is split in two by design:

* **This package** (framework, public-safe) computes: the ready set, lane assignment under
  the WIP cap and the one rule, the token regulator, the reflection record, the speculative
  plan, and the ledger. It never talks to a session API and holds no instance data.
* **The harness** (an instance automation) executes what `tick.py plan` emits — starts and
  reaps lane sessions, reads their usage — and feeds the results back through
  `tick.py record`. It is the only part that needs credentials.

Everything the pipeline decides is written to a state directory the instance owns, as
append-only JSON lines, so a human can replay any tick from its inputs.
"""

__version__ = "0.1.0"
