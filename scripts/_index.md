---
type: index
tags: [os, scripts, validation]
---
# scripts/ — the instance lifecycle and the framework's own gate

The three scripts an instance runs over its life — first run, upgrade, packs — and the
executable checks this repo runs against **itself**, plus the one checker every **pack**
in the estate is held to. The framework is the public artifact of the estate: it states
invariants about itself in [[CLAUDE|CLAUDE.md]], [[PROVENANCE]], `README.md` and the
`_index.md` files, and this is what keeps those statements true.

| File | What |
|------|------|
| `bootstrap.sh` | **First run.** Instantiates `instance-template/root/` at the repository root (never overwriting), fills the placeholders, turns the clone's `origin` into the fetch-only `upstream`, mounts the packs asked for, builds the discovery links, optionally installs the dashboard and commits. Idempotent; `--dry-run`; `--yes` for headless installs; `--local` for a framework developer's checkout. See [[systems/distribution]]. |
| `upgrade.sh` | **In-place upgrade.** Fetches the framework's `main`, refuses if the instance edited a framework path, merges (handling the first merge of a template-snapshot instance), re-syncs the pack links, runs the self-check, and reports what `instance-template/` changed since the recorded template ref (`--ack-template` records the reviewed ref; `--check` reports only). `--adopt [--dry-run] [--yes]` is the one-time first merge into an instance that predates the framework's history, run from the fetched framework's copy. |
| `adopt.py` | **Adoption**, called by `upgrade.sh --adopt` from the fetched framework commit. Moves a root instance contract to `.claude/CLAUDE.md`, removes symlink mounts at framework paths, moves instance hooks and ignore rules to their extension points, lists every other instance file the framework's version would replace (refusing without `--yes`; a case-only clash is refused outright), commits that preparation and takes a merge that cannot conflict; any failure rolls the whole run back. `--dry-run` writes nothing. Handles both older layouts: a framework mounted from a sibling checkout, and the template repository's framework submodule with its committed discovery links. See [[systems/distribution]], "Adopting an existing instance". |
| `adopt_plan.py` | The adoption's **read-only planner**: classifies every path the framework tracks against the instance's `HEAD` and working tree (contract, mounts, framework submodule, committed discovery links, hooks, ignore rules, replacements, case clashes) and prints the plan. `upgrade.sh --adopt` extracts it with `adopt.py` from the fetched commit. |
| `packs.sh` | **Packs.** `add · remove · update · list · sync · apply · check · config` — mounts a pack as a pinned submodule at `.packs/<name>`, links its skills into `skills/` beside the framework's own and mirrors `skills/` into `.claude/skills/`; refuses dangling, off-pin, symlinked or modified mounts and pack names that are not plain names. `sync` also copies the instance's `.gitignore.instance` into `$GIT_DIR/info/exclude`. The single home of the script: it used to be vendored per instance from the template repository. Contract: [[systems/packs]]. |
| `validate_framework.py` | The self-check. Skill registration (provenance row + catalog entry), catalog entries that resolve on disk, `systems/*.md` front-matter against [[systems/ontology]], the `_index.md` convention, a public-safety scan for instance identifiers, derivable count claims, and — one repository, two owners — that the framework tracks no file at an instance path (derived from `instance-template/root/`). Inside a bootstrapped instance it scopes itself to the paths the framework tracks at the commit last merged, so an instance's own additions are never judged. |
| `framework-baseline.txt` | Accepted pre-existing debt — the ratchet. A violation listed here warns; anything else is an error. Debt can be paid down, never grown. |
| `run_tests.py` | **Every test suite.** Finds each directory holding a `test_*.py` outside `fixtures/` (today the gates' own [[tests/_index\|tests/]] and [[pipeline/tests/_index\|pipeline/tests/]]) and runs each in its own interpreter; exits non-zero on any failure or on finding none. The one command CI runs, so a new suite is in the build the moment it is committed. `--list` prints the suites; `-v` names each case. |
| `validate_pack.py` | The pack conformance gate — the **single home** of the checker. `pack.yaml` against [[systems/pack.schema.json\|pack.schema.json]], the `required_files` checklist, the per-skill shape, `meta-os.config.json`, and the estate-neutral scan (instance identifiers, with the ratified LICENSE-holder exemption). Takes a pack directory, so it works against a checkout of any pack repository. |
| `pack-baseline.txt` | The same ratchet for packs. `estate-neutral` and `checklist-placeholder` can never enter it. |

## Running it

```bash
scripts/bootstrap.sh                               # first run of a clone — see --help
scripts/upgrade.sh --check                         # how far behind the framework is; --check off to merge
scripts/packs.sh list                              # mounted packs and their pins

python3 scripts/validate_framework.py              # gate: new violations fail, known debt warns
python3 scripts/validate_framework.py --strict     # every warning becomes an error (cleanup pass)
python3 scripts/validate_framework.py --update-baseline   # re-record accepted debt

python3 scripts/validate_pack.py                   # every pack that lives inside this repo
python3 scripts/validate_pack.py ../some-pack      # one pack, from anywhere on disk
python3 scripts/run_tests.py                       # every test suite in the repo, as CI runs them
python3 -m unittest discover -s tests              # one suite: the gates' own tests — see [[tests/_index|tests/]]
```

Both gates and every test suite run in CI (`.github/workflows/check.yml`), where they cannot be skipped. A
pack in **its own repository** runs the same `validate_pack.py` by calling
`.github/workflows/pack-conformance.yml` from a one-file caller workflow — see
[[systems/packs]]. No pack's conformance depends on a local copy of anything.

**Enable the pre-commit hook once per clone** — hooks are not carried by a clone:

```bash
git config core.hooksPath .githooks
```

The mirror of this gate for a vault's items is that repo's own `scripts/validate_items.py`;
the two are deliberately shaped alike.
