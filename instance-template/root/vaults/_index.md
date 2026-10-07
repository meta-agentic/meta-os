---
type: index
tags: [os, vaults, federation]
---
# Federated Vaults

Symlinks that pull project-local vaults into this Obsidian graph **without moving their
files** — each stays owned by, and colocated with, its repo.

| Vault | Symlink target | Owner repo | Conventions |
|-------|----------------|------------|-------------|
| _(none yet)_ | | | |

## Adding a federated vault

```bash
ln -s ../../<repo>/<vault-folder> vaults/<name>
```

## Rules

- **Edit federated notes in their own conventions**, not this OS's — they belong to their repo.
- Their content is committed in *their* repos; this repo only commits the symlinks.
- On a machine without those checkouts, the symlinks dangle — harmless; Obsidian just
  shows them empty.
- Cross-project-durable knowledge still gets **promoted** into [[memory/wiki/_index|memory/wiki/]]
  — federation is for navigation, promotion is for canon.
