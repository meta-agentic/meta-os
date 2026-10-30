#!/usr/bin/env bash
# First run of a meta-os checkout: turn it into YOUR instance.
#
# The framework and your instance are two repositories; the instance's tree holds the
# framework's paths beside its own, split by path (systems/distribution.md). This script
# copies instance-template/root/ to the repository root — path for path, never
# overwriting — fills the placeholders, points the remotes the right way round (the
# framework becomes the fetch-only `upstream`, fetched here), mounts the packs you ask
# for, initialises the pinned ones (scripts/packs.sh apply) and builds the engine's
# discovery links. Re-running it is safe: every step reports what already exists and
# changes nothing there.
#
# A second checkout of an existing instance (a new machine, a container) is a clone of
# the INSTANCE's repository, then this script. Its .claude/CLAUDE.md is committed, so no
# template file is created there: a template file the instance does not have is one it
# removed, and the template is instantiated once, never re-applied.
#
#   scripts/bootstrap.sh                         # interactive on a terminal, defaults otherwise
#   scripts/bootstrap.sh --yes --name acme-os    # headless: every answer from flags/defaults
#   scripts/bootstrap.sh --dry-run               # print the plan, write nothing
#
# Options
#   --name NAME        instance name (default: this directory's name)
#   --origin URL       your PRIVATE remote; added as `origin` (the framework becomes `upstream`)
#   --upstream URL     the framework remote (default: the public meta-os repository)
#   --packs a,b        packs to mount from the registry (systems/packs.yaml), comma-separated
#   --dashboard [DIR]  clone meta-os-dashboard next to this repo (or into DIR) and point it here
#   --backlog SPEC     the backlog, written to meta-os.config.json `backlogs[]` (repeatable):
#                        none           declare no backlog yet (backlogs: [])
#                        SPACE=PATH     a per-item backlog: SPACE is its key, PATH its directory
#                                       (${var} expands, see systems/config.md)
#                      An external tracker is not a key of this file: it is the agile pack's
#                      `tracker` setting in .packs.yaml (systems/packs.md).
#   --memory-layout L  the memory topology, written to meta-os.config.json `memory`:
#                        default        omit the block: memory/{raw,wiki,output} + vaults/*
#                        flat | tier/project | project/tier
#                                       one canon root, this instance's memory/, with that
#                                       layout (systems/memory-layer.md)
#   --project NAME     the first project node: projects/NAME.md from templates/project.md,
#                      plus its row in projects/_index.md
#   --commit           commit the instantiated files when done
#   --local            developer mode: keep the instance files out of git via .git/info/exclude
#                      and leave the remotes alone (for hacking the framework in this checkout)
#   --yes              take every default without prompting
#   --dry-run          show what would happen, write nothing
#   -h, --help         this text
set -euo pipefail

CANONICAL_UPSTREAM="https://github.com/meta-agentic/meta-os.git"
DASHBOARD_REPO="https://github.com/meta-agentic/meta-os-dashboard.git"
TEMPLATE="instance-template/root"

die() { echo "bootstrap: $*" >&2; exit 1; }
say() { printf '%s\n' "$*"; }

usage() { sed -n '2,/^set -euo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'; }

name="" origin="" upstream="$CANONICAL_UPSTREAM" packs="" dashboard="" do_commit=0 local_mode=0 yes=0 dry=0
backlogs=() memory_layout="" project=""
while [ $# -gt 0 ]; do
  case "$1" in
    --name) name="${2:?--name needs a value}"; shift 2 ;;
    --name=*) name="${1#*=}"; shift ;;
    --origin) origin="${2:?--origin needs a url}"; shift 2 ;;
    --origin=*) origin="${1#*=}"; shift ;;
    --upstream) upstream="${2:?--upstream needs a url}"; shift 2 ;;
    --upstream=*) upstream="${1#*=}"; shift ;;
    --packs) packs="${2:?--packs needs a list}"; shift 2 ;;
    --packs=*) packs="${1#*=}"; shift ;;
    --dashboard) dashboard="../meta-os-dashboard"; if [ $# -gt 1 ] && [ "${2#-}" = "$2" ]; then dashboard="$2"; shift; fi; shift ;;
    --dashboard=*) dashboard="${1#*=}"; shift ;;
    --backlog) backlogs+=("${2:?--backlog needs a value: none or SPACE=PATH}"); shift 2 ;;
    --backlog=*) backlogs+=("${1#*=}"); shift ;;
    --memory-layout) memory_layout="${2:?--memory-layout needs a value}"; shift 2 ;;
    --memory-layout=*) memory_layout="${1#*=}"; shift ;;
    --project) project="${2:?--project needs a name}"; shift 2 ;;
    --project=*) project="${1#*=}"; shift ;;
    --commit) do_commit=1; shift ;;
    --local) local_mode=1; shift ;;
    --yes|-y) yes=1; shift ;;
    --dry-run) dry=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option '$1' (see --help)" ;;
  esac
done

# --- where we are ---------------------------------------------------------------
root=$(git rev-parse --show-toplevel 2>/dev/null) || die "not inside a git checkout — clone meta-os first"
cd "$root"
[ -d "$TEMPLATE" ] || die "no $TEMPLATE/ here — this is not a meta-os checkout (or an old one: git pull first)"
[ -f CLAUDE.md ] && [ -d skills ] && [ -d systems ] || die "the framework folders are missing — this is not a meta-os checkout"
[ -x scripts/packs.sh ] || die "scripts/packs.sh is missing or not executable"

bootstrapped=0; [ -f .claude/CLAUDE.md ] && bootstrapped=1
# Committed: the instance's own history carries its contract. An uncommitted first run
# (interrupted, or not committed yet) still fills its gaps on a re-run.
committed=0
if [ "$bootstrapped" = 1 ] && git ls-files --error-unmatch .claude/CLAUDE.md >/dev/null 2>&1; then committed=1; fi

# --- answers ----------------------------------------------------------------------
interactive=0; [ "$yes" = 0 ] && [ -t 0 ] && interactive=1
ask() { # <var> <prompt> <default>
  local v="$1" prompt="$2" def="$3" ans
  if [ "$interactive" = 1 ]; then
    read -r -p "$prompt [$def]: " ans || true
    printf -v "$v" '%s' "${ans:-$def}"
  else
    printf -v "$v" '%s' "$def"
  fi
}
registry_available() { # names with status: available in systems/packs.yaml
  [ -f systems/packs.yaml ] || return 0
  awk '/^  [a-zA-Z0-9_-]+:$/ { n=$1; sub(/:$/,"",n); next }
       n && $1=="status:" && $2=="available" { print n; n="" }' systems/packs.yaml | sort | tr '\n' ' '
}
if [ -z "$name" ]; then ask name "Instance name" "$(basename "$root")"; fi
[[ "$name" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || die "instance name '$name' — use letters, digits, '.', '_' or '-'"
if [ "$bootstrapped" = 0 ] && [ "$interactive" = 1 ] && [ "$local_mode" = 0 ]; then
  if [ "${#backlogs[@]}" = 0 ]; then
    ask bl "Backlog: none, or SPACE=PATH (empty: decide later)" ""
    [ -z "$bl" ] || backlogs+=("$bl")
  fi
  [ -n "$memory_layout" ] || ask memory_layout "Memory layout: default, flat, tier/project or project/tier (empty: decide later)" ""
  [ -n "$project" ] || ask project "First project name (empty: add later)" ""
  [ -n "$origin" ] || ask origin "Your private remote URL (empty: add it later)" ""
  if [ -z "$packs" ]; then
    avail=$(registry_available)
    [ -z "$avail" ] || say "Packs in the registry: $avail"
    ask packs "Packs to mount now, comma-separated (empty: none)" ""
  fi
  if [ -z "$dashboard" ]; then
    ask dash_yn "Install the dashboard next to this repo? (y/N)" "N"
    case "$dash_yn" in y|Y|yes) dashboard="../meta-os-dashboard" ;; esac
  fi
fi

# Validate the three estate decisions before anything is written: a bad value stops the run.
for spec in ${backlogs[@]+"${backlogs[@]}"}; do
  if [ "$spec" = none ]; then [ "${#backlogs[@]}" = 1 ] || die "--backlog none cannot be combined with other --backlog values"
  elif ! [[ "$spec" =~ ^[A-Za-z][A-Za-z0-9_-]*=.+$ ]]; then
    die "--backlog '$spec' — use 'none' or SPACE=PATH (SPACE: letters, digits, '-' or '_', starting with a letter; PATH: the backlog's directory), e.g. --backlog abc='\${estate}/vault/abc'"
  fi
done
case "$memory_layout" in
  ""|default|flat|tier/project|project/tier) ;;
  *) die "--memory-layout '$memory_layout' — use one of: default, flat, tier/project, project/tier (systems/memory-layer.md)" ;;
esac
if [ -n "$project" ]; then
  [[ "$project" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || die "--project '$project' — use letters, digits, '.', '_' or '-', starting with a letter or digit"
fi

# --- helpers ----------------------------------------------------------------------
run() { if [ "$dry" = 1 ]; then say "  would: $*"; else "$@"; fi; }
today=$(date +%Y-%m-%d)
template_ref=$(git rev-parse HEAD)
subst() { # <file> — fill the placeholders in a file we just created
  local f="$1"
  sed -e "s|{{instance-name}}|$name|g" -e "s|{{bootstrapped}}|$today|g" -e "s|{{template-ref}}|$template_ref|g" \
      "$f" > "$f.bootstrap.tmp" && mv "$f.bootstrap.tmp" "$f"
}

# The estate decisions (backlog, memory topology, first project). One python helper does the
# JSON edit and the index row so both stay exact; `check` reports a conflict and writes nothing,
# `apply` writes (or, in a dry run, only says what it would write).
estate_decisions() { # check | apply
  local bl_json="null"
  if [ "${#backlogs[@]}" -gt 0 ]; then bl_json=$(printf '%s\n' "${backlogs[@]}" | python3 -c 'import json,sys; print(json.dumps([l.rstrip("\n") for l in sys.stdin]))'); fi
  MODE="$1" DRY="$dry" TEMPLATE="$TEMPLATE" BL="$bl_json" MEM="$memory_layout" PROJ="$project" python3 - <<'PY'
import json, os, re, sys
mode, dry = os.environ["MODE"], os.environ["DRY"] == "1"
tmpl = os.environ["TEMPLATE"]
bl, mem, proj = json.loads(os.environ["BL"]), os.environ["MEM"], os.environ["PROJ"]
check = mode == "check"
conflicts = []
def say(m):
    if not check: print("  " + m)

CFG = "meta-os.config.json"
cfg_missing = not os.path.exists(CFG)
placeholder = json.load(open(os.path.join(tmpl, CFG)))
cfg = {} if cfg_missing else json.load(open(CFG))
changed = False

def decide(key, label, desired, absent_ok=True):
    """already | set | conflict, against the file's value and the template's placeholder."""
    global changed
    cur = cfg.get(key)
    if cur == desired or (desired is None and key not in cfg):
        say(f"{label}: already configured"); return
    if key not in cfg or cur == placeholder.get(key):
        if cfg_missing:
            say(f"{label}: {CFG} is not in this instance (not recreated) — set it by hand"); return
        if desired is None: cfg.pop(key, None)
        else: cfg[key] = desired
        changed = True
        say(f"{label}: {'would set' if dry else 'set'} in {CFG}")
        return
    conflicts.append(f"{label}: {CFG} already holds a different '{key}' — edit it by hand (or remove the key) to change it")

if bl is not None:
    desired = []
    for spec in bl:
        if spec != "none":
            space, path = spec.split("=", 1)
            desired.append({"space": space, "path": path})
    decide("backlogs", "backlog", desired)
if mem:
    if mem == "default":
        decide("memory", "memory layout", None)
    else:
        desired = {"roots": [{"label": "instance", "path": "${instance}/memory", "layout": mem}]}
        decide("memory", "memory layout", desired)
        if changed and not dry:
            cfg.setdefault("vars", {}).setdefault("instance", os.getcwd())

if proj:
    node, idx = f"projects/{proj}.md", "projects/_index.md"
    row_re = re.compile(r"\[\[projects/" + re.escape(proj) + r"[\\|\]]")
    idx_text = open(idx).read() if os.path.exists(idx) else None
    has_node, has_row = os.path.exists(node), bool(idx_text and row_re.search(idx_text))
    if has_node and (has_row or idx_text is None):
        say(f"project: {node} already configured")
    elif idx_text is None:
        say("project: projects/ is not in this instance (not recreated) — add the node by hand")
    elif not check:
        if not has_node:
            say(f"project: {'would write' if dry else 'wrote'} {node} from templates/project.md")
        if not has_row:
            say(f"project: {'would add' if dry else 'added'} its row to {idx}")
        if not dry:
            if not has_node:
                t = open("templates/project.md").read()
                t = re.sub(r"(?m)^name:.*$", f"name: {proj}", t, count=1)
                t = t.replace("# {{Project Name}}", f"# {proj}")
                os.makedirs("projects", exist_ok=True)
                open(node, "w").write(t)
            if not has_row and idx_text is not None:
                row = f"| {proj} | [[projects/{proj}\\|{proj}]] | | |"
                lines = idx_text.split("\n")
                at = [i for i, l in enumerate(lines) if "_(none yet)_" in l]
                if at: lines[at[0]] = row
                else:
                    rows = [i for i, l in enumerate(lines) if l.startswith("|")]
                    lines.insert((rows[-1] + 1) if rows else len(lines), row)
                open(idx, "w").write("\n".join(lines))

if conflicts:
    print("bootstrap: " + "\nbootstrap: ".join(conflicts), file=sys.stderr); sys.exit(2)
if changed and not check and not dry:
    with open(CFG, "w") as fh:
        json.dump(cfg, fh, indent=2, ensure_ascii=False); fh.write("\n")
PY
}

say "meta-os bootstrap — instance '$name' in $root"
[ "$dry" = 0 ] || say "(dry run: nothing is written)"

# A decision that conflicts with what the instance already holds stops the run before it writes.
if [ "$bootstrapped" = 1 ] && { [ "${#backlogs[@]}" -gt 0 ] || [ -n "$memory_layout" ]; }; then
  estate_decisions check || exit 1
fi

# --- 1. instantiate the template ------------------------------------------------------
say ""
say "1. Instance files from $TEMPLATE/"
created=0 kept=0 created_list="" absent_list=""
while IFS= read -r rel; do
  rel="${rel#./}"
  if [ -e "$rel" ] || [ -L "$rel" ]; then
    kept=$((kept+1))
  elif [ "$committed" = 1 ]; then
    absent_list="$absent_list $rel"
  else
    created=$((created+1)); created_list="$created_list $rel"
    if [ "$dry" = 1 ]; then say "  would create: $rel"
    else
      mkdir -p "$(dirname "$rel")"
      cp -p "$TEMPLATE/$rel" "$rel"
      [ -L "$rel" ] || subst "$rel"
    fi
  fi
done < <(cd "$TEMPLATE" && find . \( -type f -o -type l \) | LC_ALL=C sort)
if [ "$dry" = 1 ]; then say "  would create $created, kept $kept already present"
else say "  created $created, kept $kept already present"; fi
if [ -n "$absent_list" ]; then
  say "  not recreated — this instance is committed and does not have them (the template is"
  say "  instantiated once, never re-applied; scripts/upgrade.sh --check reports its changes):"
  for rel in $absent_list; do say "    $rel"; done
fi
if [ "$local_mode" = 1 ] && [ "$dry" = 0 ]; then
  ex=$(git rev-parse --git-path info/exclude); mkdir -p "$(dirname "$ex")"; [ -f "$ex" ] || : > "$ex"
  marker="# >>> meta-os scripts/bootstrap.sh --local — instance files of a developer checkout >>>"
  if ! grep -qxF "$marker" "$ex"; then
    { echo "$marker"
      (cd "$TEMPLATE" && find . -mindepth 1 -maxdepth 1 | sed 's|^\./|/|' | LC_ALL=C sort)
      echo "/.packs/"; echo "/.gitmodules"
      echo "# <<< meta-os scripts/bootstrap.sh --local <<<"; } >> "$ex"
  fi
  say "  developer mode: instance paths listed in $(git rev-parse --git-path info/exclude) — they stay out of git here"
fi

# --- 1b. backlog, memory topology, first project (only what was asked for) ------------------
if [ "${#backlogs[@]}" -gt 0 ] || [ -n "$memory_layout" ] || [ -n "$project" ]; then
  say ""
  say "1b. Estate decisions"
  if [ "$dry" = 1 ] && [ "$bootstrapped" = 0 ]; then
    for spec in ${backlogs[@]+"${backlogs[@]}"}; do say "  would set backlog '$spec' in meta-os.config.json"; done
    [ -z "$memory_layout" ] || say "  would set memory layout '$memory_layout' in meta-os.config.json"
    [ -z "$project" ] || say "  would write projects/$project.md and its row in projects/_index.md"
  else
    estate_decisions apply || exit 1
  fi
fi

# --- 2. remotes -----------------------------------------------------------------------------
say ""
say "2. Remotes"
if [ "$local_mode" = 1 ]; then
  say "  developer mode: remotes left as they are"
else
  has_remote() { git remote | grep -qx "$1"; }
  norm() { printf '%s' "${1%/}" | sed -e 's|\.git$||' -e 's|^git@github\.com:|https://github.com/|'; }
  if has_remote upstream; then
    say "  upstream: $(git remote get-url upstream) (already configured)"
  elif has_remote origin && [ "$(norm "$(git remote get-url origin)")" = "$(norm "$upstream")" ]; then
    say "  origin points at the framework — renaming it to 'upstream' (the framework is fetched, never pushed to)"
    run git remote rename origin upstream
  else
    say "  adding 'upstream' = $upstream"
    run git remote add upstream "$upstream"
  fi
  run git remote set-url --push upstream no_push
  # The gate reads the framework's paths from upstream/main; unfetched, it judges the
  # instance's own files. A failed fetch (offline) is reported, not fatal.
  if [ "$dry" = 1 ]; then say "  would: git fetch upstream"
  elif git fetch -q upstream; then say "  fetched upstream"
  else say "  warn: could not fetch upstream — run 'git fetch upstream' before scripts/validate_framework.py"; fi
  if [ -n "$origin" ]; then
    if has_remote origin; then say "  origin: $(git remote get-url origin) (already configured; --origin ignored)"
    else say "  origin (your private remote): $origin"; run git remote add origin "$origin"; fi
  elif ! has_remote origin; then
    say "  no private remote yet — when you have one: git remote add origin <url> && git push -u origin $(git branch --show-current)"
  fi
fi

# --- 3. packs + discovery links ---------------------------------------------------------
say ""
say "3. Packs and discovery links"
if [ -n "$packs" ]; then
  IFS=', ' read -r -a plist <<< "$packs"
  for pk in "${plist[@]}"; do
    [ -n "$pk" ] || continue
    if [ -d ".packs/$pk" ]; then say "  pack '$pk' already mounted"
    else say "  mounting pack '$pk'"; run scripts/packs.sh add "$pk"; fi
  done
fi
# apply, not sync: a fresh clone carries the pinned packs as empty folders, which sync
# refuses and apply initialises at their pins. Developer mode keeps sync: its mounts
# are not the manifest's to reconcile.
packs_cmd=apply; [ "$local_mode" = 1 ] && packs_cmd=sync
if [ "$dry" = 1 ]; then say "  would: scripts/packs.sh $packs_cmd"; else scripts/packs.sh "$packs_cmd" | sed 's/^/  /'; fi

# --- 4. dashboard (optional) ---------------------------------------------------------------
if [ -n "$dashboard" ]; then
  say ""
  say "4. Dashboard at $dashboard"
  if [ -d "$dashboard" ]; then say "  already present"
  else say "  cloning $DASHBOARD_REPO"; run git clone -q "$DASHBOARD_REPO" "$dashboard"; fi
  if [ "$dry" = 0 ] && [ -d "$dashboard" ]; then
    cfg="$dashboard/instance.config.json"
    if [ -f "$cfg" ]; then say "  $cfg already present"
    else
      printf '{\n  "instanceRoot": "%s",\n  "frameworkRoot": "%s"\n}\n' "$root" "$root" > "$cfg"
      say "  wrote $cfg (instanceRoot = frameworkRoot = this repository)"
    fi
    if command -v npm >/dev/null 2>&1; then (cd "$dashboard" && npm install --silent >/dev/null 2>&1 && say "  npm install done") || say "  npm install failed — run it by hand in $dashboard"
    else say "  npm not found — install Node, then: cd $dashboard && npm install"; fi
    say "  start it with: (cd $dashboard && npm run dev)"
  fi
fi

# --- 5. commit (optional) --------------------------------------------------------------------
if [ "$do_commit" = 1 ] && [ "$local_mode" = 0 ]; then
  say ""
  say "5. Commit"
  if [ "$dry" = 1 ]; then say "  would: git add -A && git commit -m 'bootstrap: instantiate $name'"
  elif [ "$created" = 0 ] && git diff --quiet && git diff --cached --quiet; then say "  nothing to commit"
  else git add -A && git commit -q -m "bootstrap: instantiate $name from instance-template at ${template_ref:0:12}" && say "  committed"; fi
fi

# --- done ---------------------------------------------------------------------------------------
say ""
if [ "$dry" = 1 ]; then say "Dry run — nothing was written. Re-run without --dry-run to instantiate '$name'."; exit 0
elif [ "$bootstrapped" = 1 ] && [ "$created" = 0 ]; then say "Already bootstrapped — no instance file created."; else say "Instance '$name' is live."; fi
say "Next:"
say "  - open $root as your Obsidian vault; start at _index.md"
say "  - in Claude Code, run the bootstrap-instance skill for the guided first conversation"
say "    (backlog, memory layout, first project, packs); the instance contract is .claude/CLAUDE.md"
[ "$do_commit" = 1 ] || [ "$local_mode" = 1 ] || say "  - commit: git add -A && git commit -m 'bootstrap: instantiate $name'"
say "  - later: scripts/upgrade.sh takes the framework's next version without touching your files"
