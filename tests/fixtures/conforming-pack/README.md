# example-discipline pack

Fixture pack used by `tests/test_validate_pack.py` as the **positive control** for the
pack conformance gate: it ships every file `systems/pack.schema.json` requires, its
manifest validates, its one skill carries the required shape, and it is estate-neutral.

A change that makes this pack fail the gate is a change to the contract, not a fixture
bug — read `systems/packs.md` before editing it.

| Skill | Discipline | Checkable output |
|-------|------------|------------------|
| `example-method` | worked-example verification | verification ledger |

Config knobs live in `pack.yaml`; profiles in `profiles/`.
