# .githooks.d/ — this instance's own git hooks

The framework's hooks in `.githooks/` are dispatchers: after the framework's own check,
each runs every **executable** file in `.githooks.d/<hook>/` whose name is letters,
digits, `_` and `-` only (so `*.orig`, `*~` and editor swap files never run), in name
order, with the hook's arguments, and the first that fails fails the hook. Put an instance hook here —
never edit a file in `.githooks/`, which an upgrade replaces.

    .githooks.d/pre-commit/10-my-gate      # chmod +x; runs after the framework gate
    .githooks.d/commit-msg/10-my-check     # gets the message file as $1

Dispatched today: `pre-commit`, `commit-msg`. A hook is found through
`git rev-parse --show-toplevel`, not through its own location: one that sources
sibling files via `$(dirname "$0")` must say where they are now. A symlink here is
followed. Hooks run only in a
clone that enabled them: `git config core.hooksPath .githooks`.
