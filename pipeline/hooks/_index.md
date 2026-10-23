---
type: index
tags: [os, pipeline, automation]
---
# pipeline/hooks/ — the record clone's event hooks

Git hooks for the local clone of the record repository ([[pipeline/_index|pipeline/]]). Each
writes one `vault_commit` event, the new `HEAD`, to the runner's inbox when
`METAOS_PIPELINE_INBOX` is set, and is a no-op otherwise. Both always exit 0.

| File | What |
|------|------|
| `post-commit` | After a local commit. |
| `post-merge` | After a pull or merge brings commits in. |

## Installing

From the clone's own `.git/hooks/post-commit` and `post-merge`, call
`sh <framework>/pipeline/hooks/post-commit` (or `post-merge`), and export
`METAOS_PIPELINE_INBOX` in the environment that commits. A symlinked hook also needs
`METAOS_PIPELINE_DIR=<framework>/pipeline`, because it finds the package from its own path.
