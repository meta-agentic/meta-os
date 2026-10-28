---
type: index
tags: [os, pipeline, automation]
---
# pipeline/systemd/ — the runner and sentinel as systemd user units

The systemd counterparts of the launchd templates, for instances on Linux. Templates only: the instance fills each `__PLACEHOLDER__` and installs the units; the framework installs nothing.

| File | What |
|---|---|
| `metaos-runner.service.template` | the runner (`tick.py run`); `Restart=on-failure` restarts a crash, a clean exit or a lost lease stays down |
| `metaos-sentinel.path.template` | starts the sentinel when the inbox changes (`PathChanged=`, systemd's WatchPaths), never on an interval |
| `metaos-sentinel.service.template` | the sentinel in inbox mode, one shot per trigger |
