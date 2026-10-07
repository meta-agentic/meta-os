#!/usr/bin/env bash
# First run of a meta-os checkout: turn it into YOUR instance.
#
# One repository, two owners split by path (systems/distribution.md). This script copies
# instance-template/root/ to the repository root — path for path, never overwriting —
# fills the placeholders, points the remotes the right way round (the framework becomes
# the fetch-only `upstream`), mounts the packs you ask for and builds the engine's
# discovery links. Re-running it is safe: every step reports what already exists and
# changes nothing there.
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

# --- helpers ----------------------------------------------------------------------
run() { if [ "$dry" = 1 ]; then say "  would: $*"; else "$@"; fi; }
today=$(date +%Y-%m-%d)
template_ref=$(git rev-parse HEAD)
subst() { # <file> — fill the placeholders in a file we just created
  local f="$1"
  sed -e "s|{{instance-name}}|$name|g" -e "s|{{bootstrapped}}|$today|g" -e "s|{{template-ref}}|$template_ref|g" \
      "$f" > "$f.bootstrap.tmp" && mv "$f.bootstrap.tmp" "$f"
}

say "meta-os bootstrap — instance '$name' in $root"
[ "$dry" = 0 ] || say "(dry run: nothing is written)"

# --- 1. instantiate the template ------------------------------------------------------
say ""
say "1. Instance files from $TEMPLATE/"
created=0 kept=0 created_list=""
while IFS= read -r rel; do
  rel="${rel#./}"
  if [ -e "$rel" ] || [ -L "$rel" ]; then
    kept=$((kept+1))
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
say "  created $created, kept $kept already present"
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
if [ "$dry" = 1 ]; then say "  would: scripts/packs.sh sync"; else scripts/packs.sh sync | sed 's/^/  /'; fi

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
if [ "$bootstrapped" = 1 ] && [ "$created" = 0 ]; then say "Already bootstrapped — nothing changed."; else say "Instance '$name' is live."; fi
say "Next:"
say "  - open $root as your Obsidian vault; start at _index.md"
say "  - in Claude Code, run the bootstrap-instance skill for the guided first conversation"
say "    (backlog model, first project, packs); the instance contract is .claude/CLAUDE.md"
[ "$do_commit" = 1 ] || [ "$local_mode" = 1 ] || say "  - commit: git add -A && git commit -m 'bootstrap: instantiate $name'"
say "  - later: scripts/upgrade.sh takes the framework's next version without touching your files"
