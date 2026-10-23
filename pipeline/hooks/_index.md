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

The instance installs each hook as a one-line wrapper in the clone's own `.git/hooks/` that
calls the framework's hook, so the hook finds the package from its real path:

```sh
#!/bin/sh
sh <framework>/pipeline/hooks/post-commit    # post-merge: the same, with post-merge
```

`METAOS_PIPELINE_INBOX` is exported in the environment that commits. Where the clone already
has a hook, the line goes at its end. `METAOS_PIPELINE_DIR` overrides the package location.
