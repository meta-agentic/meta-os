# {{instance-name}} — Agentic OS instance

<!-- Instantiated by scripts/bootstrap.sh on {{bootstrapped}} from instance-template/root/
     at framework ref {{template-ref}}. This file is YOURS: fill in "Instance facts",
     delete the TODO comments. The framework contract is the root CLAUDE.md; Claude Code
     loads both (./CLAUDE.md and ./.claude/CLAUDE.md are both project instructions). -->

This checkout is **your private repository, holding the framework's paths beside your
own**. The framework is a separate public repository, fetched as `upstream` and never
pushed to; it arrives and updates through `scripts/upgrade.sh` and is never edited here.
The instance is everything else and is never touched by an upgrade.

```
{{instance-name}}/                 ← open THIS folder as the Obsidian vault
├── .claude/CLAUDE.md              ← this file — the instance contract        ┐
├── _index.md                      ← the vault home                           │
├── projects/                      ← estate registry (repos, trackers, paths) │ INSTANCE
├── memory/                        ← raw → wiki → output — the knowledge      │ (yours; an
├── automations/                   ← live routine rows                        │ upgrade never
├── vaults/                        ← symlinks to federated project vaults     │ touches these)
├── meta-os.config.json            ← estate config (memory topology, backlogs)│
├── .packs.yaml  .packs/<pack>/    ← declared packs + their pinned mounts     ┘
├── CLAUDE.md                      ← the framework contract                   ┐
├── skills/ systems/ templates/    ← the framework: skill library, operating  │ FRAMEWORK
│   agents/ hooks/ pipeline/          model, note templates, roster, hooks     │ (upstream's;
├── scripts/                       ← bootstrap · upgrade · packs · the gates  │ read, run,
├── instance-template/             ← what this instance was instantiated from │ never edit)
└── README.md  PROVENANCE.md  LICENSE                                         ┘
```

Pack skills are linked into `skills/` beside the framework's own and mirrored into
`.claude/skills/` by `scripts/packs.sh sync`; those links are generated and never
committed. The framework's contract on this split is [[systems/distribution]].

**Framework rules apply here** — the root `CLAUDE.md` states them (`_index.md` discipline,
memory promotion, naming, linking, public-safety of the framework paths). This file holds
only what is instance-specific.

## Instance facts

<!-- TODO: fill these in as your estate grows; delete this comment once populated. -->

- **Estate:** (list your projects — one node each in [[projects/_index|projects/]])
- **Authority order (process/backlog):** (e.g. tracker → per-item vault files →
  [[skills/agile-process/SKILL|agile-process]] → framework invariants. Higher source
  wins. Skip this line if you don't run the agile pack.)
- **Packs:** declared in `.packs.yaml`; `scripts/packs.sh list` shows what is mounted and
  at which pin. Edit a pack in its own repo, then bump the pin — never in `.packs/`.
- **Upgrades:** `scripts/upgrade.sh` — merges the framework's `main` from the `upstream`
  remote, refuses if a framework path was edited here, re-syncs the pack links, and
  reports what changed in `instance-template/` since this instance was instantiated.

## Rules

- **Never edit a framework path.** A change the framework needs is made in a public
  checkout of meta-os and proposed upstream; this instance takes it with the next
  upgrade. A local edit to a framework path is what `scripts/upgrade.sh` refuses on.
- Memory promotion, `_index.md` discipline, naming and linking: as per the framework
  ([[systems/memory-layer]], root `CLAUDE.md`).
- Projects are nodes, not clones. Federated vault notes are edited in *their* conventions.
- This repository should stay **private**: it holds your estate's data. The `upstream`
  remote is fetch-only (its push URL is disabled by bootstrap), so nothing here can be
  pushed to the public framework by accident.
