---
type: index
tags: [os, scripts, validation, tests]
---
# tests/ — the gates' own test suite

[[scripts/_index|scripts/]] holds the gates; this folder holds what proves they still
gate. A conformance checker nobody exercises degrades into a script that exits 0 — so
every rule the pack contract states is pinned here by a test that fails when the rule
stops being enforced.

| File | What |
|------|------|
| `test_instance_lifecycle.py` | Builds a throwaway upstream from this working tree, then drives `scripts/bootstrap.sh` and `scripts/upgrade.sh` the way an adopter does: instantiation and placeholders, remotes, generated links never tracked, idempotence, dry run, developer mode, the gate passing inside an instance and refusing a tracked instance path in the framework, an upgrade that changes framework paths and no instance path, the refusal when an instance edited a framework path, the first merge of a template-snapshot instance, and the template-drift report. |
| `test_adopt.py` | Drives `scripts/upgrade.sh --adopt` from the fetched framework against a synthetic instance that predates the framework's history (own history, contract in the root `CLAUDE.md`, framework folders as symlinks into a sibling checkout, a vendored script, its own hooks, ignore lines and workflow, top-level paths of its own): the plan listed before anything is replaced, the refusal without `--yes`, nothing of the instance lost (contract moved, hooks running from `.githooks.d/`, ignore rules effective), the gate passing, the next upgrade an ordinary merge; plus an untracked file backed up, an instance with no contract, a template snapshot whose symlink meets a framework folder (`<path>~HEAD`), a dry run that writes nothing in any state, symlinked hook/contract/`.gitignore` kept, a folder link that is not a framework checkout listed, a failing commit rolled back, a case-only clash refused, the dispatchers' name filter, a stale framework ref unable to narrow the gate, a developer checkout keeping the full gate scope, and a framework commit without the adoption scripts failing instead of reporting success. |
| `test_adopt_submodule.py` | The template-repository layout (the framework as a submodule): the submodule and committed links removed with a clean tree, a failed run restoring the submodule checkout exactly (mounts resolving, no nested copy, verified), work that exists only in the submodule (a branch commit, a stash) listed and kept in a self-contained backup, a submodule shaped like the framework but from elsewhere needing `--yes`, an instance skill linked into `skills/` never dropped silently, and an upgrade beside the operator's untracked files succeeding. |
| `test_ci_framework_ref.py` | Drives `scripts/ci_framework_ref.py` against a throwaway framework and a depth-1, remote-less checkout like the one CI gets: the framework repository left alone, an instance given its history, `upstream` and the merge base of the framework commit it merged (not a later one), `--url` over the environment, an existing remote kept, a snapshot with no shared history and an unreachable framework failing, the framework repository tracking `.claude/CLAUDE.md` refused (by its origin or by `$GITHUB_REPOSITORY`), URLs compared by what they name; both jobs of `check.yml` preparing the ref before the gate; and, built from this working tree, the gate in the framework's own repository still catching a leak in a new file and refusing the tracked contract when `upstream/main` is reachable. |
| `test_packs_sh.py` | Drives `scripts/packs.sh` against local fixture packs in the one-repository layout: mount, idempotent apply, remove, the pack links placed beside the framework's skills and listed in `.git/info/exclude`, the framework winning a name collision, dangling, off-pin, symlinked and modified mounts refused, `remove` keeping local changes and dropping a linked worktree's module gitdir, name validation on every command, a symlinked `.claude/skills` refused, `.gitignore.instance` applied, config resolution; an uninitialised submodule refused then initialised by `apply`, a dangling skill link and a declared-but-unmounted pack refused by `check`, `apply` failing when a declared pack cannot mount, `update` staging the bump so `apply` keeps it, a union link with a wrong target refused until `sync`, an instance-owned skill shadowing a pack skill with `check` passing. |
| `test_packs_sh_config.py` | `scripts/packs.sh config` against the manifest shapes an instance writes, on the same fixture: block-form and inline-map defaults, a block map and a block sequence returned whole, a bare key read as empty, a `#` inside quotes kept and a trailing comment dropped, an unknown key refused and a misspelled one warned, enum values matched literally (not as a pattern), a pack without `pack.yaml` resolving only its own keys. |
| `test_run_tests.py` | Pins `scripts/run_tests.py`: it finds this repository's suites (this one and the pipeline's), never a `fixtures/` file or an ignored one, fails the run on one failing suite and on finding none, and is what the blocking CI job calls, with no suite named there by hand. |
| `test_validate_pack.py` | Drives `scripts/validate_pack.py` through its real command line against the fixture packs: the required-file checklist, the manifest schema, the per-skill shape, and the estate-neutral scan including the ratified LICENSE exemption and its adversarial probes. Also asserts the reusable workflow a pack repo adopts is present and callable. |
| `fixtures/` | The two control packs — see [[tests/fixtures/_index\|fixtures/]]. |

## Running it

```bash
python3 -m unittest discover -s tests        # the suite
python3 -m unittest discover -s tests -v     # with each case named
python3 scripts/run_tests.py                 # every suite in the repo, this one included, as CI runs them
```

Dependencies are the gates' own: `pyyaml` and `jsonschema`, plus `git` and `bash` for the lifecycle and packs suites. CI runs the suite, with every other suite in the repository, through
`scripts/run_tests.py` in the blocking job of [[systems/packs|the check workflow]], so a change that
weakens the pack gate reddens the build rather than passing quietly.

## Writing a new case

Never commit a string that must not appear in a public repository — a tracker-key
lookalike, an absolute home path, a real name. Assemble it from fragments at run time
and write it into a temporary copy of a fixture, the way the existing probes do. The
framework's own public-safety scan reads every tracked file and will (correctly) fail
the build otherwise.
