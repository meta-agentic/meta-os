# meta-os — Agentic OS framework

This repo is the **generic framework** of an Agentic OS: the skill backbone, the operating
model, the vault conventions and the template a fresh instance is instantiated from — with
**no instance data**. An *instance* (project registry, memory, live automations) is a
private clone of this repository with the instance paths instantiated at its root; the
framework paths stay the framework's and update by merge. The path split is the privacy
boundary: every framework path must stay **public-safe by construction** — no repo names,
trackers, paths, or promoted knowledge.

This file is the **framework contract**, loaded by Claude Code in every session inside
this directory, framework checkout or instance alike. In an instance, `.claude/CLAUDE.md`
is the **instance contract** and is loaded beside it. The *how* lives in
[[systems/_index|systems/]]; load the specific system doc or skill you need instead of
re-deriving it.

## The model — skill backbone, not dashboard

Three layers, built bottom-up. Value lives in the lower two; the dashboard is last and
optional. (After chaseAI's Agentic OS; memory flow after Karpathy's LLM-wiki.)

| Layer | Folder | What it is |
|-------|--------|-----------|
| **1 · Skills & automation** | [[skills/_index\|skills/]] · automations (instance) | Codified, executable workflows. If you do it more than once, it becomes a skill. |
| **2 · Memory** | memory (instance; its skeleton ships in `instance-template/root/memory`) | Knowledge base. Karpathy flow: `raw → wiki → output`. |
| **3 · Interface** | (build last) | Obsidian graph + optional dashboard, only after 1 & 2 are stable. |

## Framework vs. instance — two repositories, one tree split by path

The framework (this public repository) and each instance (a private repository of its
own) are **two repositories**. An instance starts as a clone of this one and keeps
merging it, so its tree holds the framework's paths beside its own. Commits cross one
way only: the instance fetches the framework as its `upstream` (push URL `no_push`) and
never sends anything back.

```
<instance>/  (your private repo, cloned from this one — open THIS as the vault)
├── CLAUDE.md          ← this contract                        ┐
├── skills/            ← the skill library                    │
├── systems/           ← how the OS operates                  │ FRAMEWORK paths —
├── templates/ agents/ ← note templates · roster + patterns   │ public-safe, upstream's,
├── hooks/ pipeline/   ← harness event scripts · swarm loop   │ updated by
├── scripts/           ← bootstrap · upgrade · packs · gates  │ scripts/upgrade.sh
├── instance-template/ ← root/ is instantiated on first run   │
├── README.md PROVENANCE.md LICENSE                           ┘
├── .claude/CLAUDE.md  ← the instance contract                ┐
├── _index.md          ← the vault home                       │ INSTANCE paths —
├── projects/          ← estate registry                      │ private, the instance's,
├── memory/            ← the live knowledge                   │ instantiated once by
├── automations/       ← live routine rows                    │ scripts/bootstrap.sh,
├── vaults/            ← federated project vaults             │ never touched by the
└── meta-os.config.json .packs.yaml .packs/ .obsidian/        ┘ framework again
```

The two path sets are disjoint and each has one owner ([[systems/distribution]]). The
framework **never tracks an instance path** — `scripts/validate_framework.py` derives
those paths from `instance-template/root/` and fails on any tracked file there — and an
instance **never edits a framework path** — `scripts/upgrade.sh` refuses to merge while
one is modified; the instance's own hooks and root ignore rules live in `.githooks.d/` and
`.gitignore.instance`, which the framework's files dispatch to. That is what makes an upgrade a merge that cannot collide. Pack skills
are linked into `skills/` beside the framework's own by `scripts/packs.sh sync` and
mirrored into `.claude/skills/`; those links are generated and never committed.
Vault-root-relative wikilinks (`[[skills/…]]`, `[[systems/…]]`) resolve the same in a
framework checkout and in an instance, because they are the same tree.

## Conventions (apply in framework and instance alike)

- **Every folder has an `_index.md`** — its table of contents. Add a line when you add a
  file; read it first when you enter a folder. Keeps navigation token-efficient at scale.
- **Skills live in `skills/` and only there.** Discovery is via symlinks
  (`~/.claude/skills/<name> → meta-os/skills/<name>`). Never create a second real copy.
- **Hooks ship, they do not switch themselves on.** [[hooks/_index|hooks/]] carries
  harness-executed event scripts; a hook is executable code, so enabling one is an
  explicit, per-hook user decision — the same rule [[systems/packs]] sets for pack hooks,
  applied to the framework's own. *Ships by default* and *runs by default* are different
  claims; only the first is ever true here.
- **Memory promotion is deliberate.** Capture lands in `memory/raw/`; only *promoted*
  notes (cleaned, front-mattered, linked) enter `memory/wiki/`. Don't cite `raw/`.
- **Link liberally** with `[[wikilinks]]`; a link to a not-yet-existing note is a TODO
  marker, not an error. Front-matter (`type:`, `tags:`) on every note.
- **Naming:** descriptive note names; tags lowercase `#type/subtype`; wikilinks by
  shortest path.
- Keep notes focused; split when a note outgrows one idea. Never commit secrets.
- **Instance data never enters a framework path** — repo names, tracker ids, machine
  paths, business context, promoted knowledge all belong at instance paths, in the
  instance's private clone. **This applies to git metadata too, not just file content:**
  commit messages, PR titles/bodies, and issue references in the framework must never
  carry tracker IDs (e.g. Jira keys) or other instance identifiers — describe the change
  in plain language instead. This repo is public; commit history is permanent. Reference
  tracker IDs only in the private instance's own notes, never here.
- **The template is instantiated, never re-applied.** `instance-template/root/` is
  copied to the root on first run and from then on those files are the instance's; a
  change to the template reaches future instances only (running ones see a diff report
  on upgrade). Mechanism that must reach every instance belongs in `skills/`, `systems/`,
  `scripts/` or `hooks/`.

## Entry points

- **Human:** open the instance (the clone) as the Obsidian vault; start at its `_index.md`.
  A fresh clone has none yet — `scripts/bootstrap.sh` creates it.
- **Agent:** this file and the instance's `.claude/CLAUDE.md` are both loaded; then read
  the `_index.md` of the folder you're working in, then the specific skill/system doc.
  Don't load everything.
