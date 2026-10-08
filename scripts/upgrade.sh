#!/usr/bin/env bash
# In-place framework upgrade for a bootstrapped meta-os instance.
#
# The framework and the instance share one repository but own disjoint paths
# (systems/distribution.md), so taking a new framework version is a merge that cannot
# collide with your files — provided you never edited a framework path. This script
# checks exactly that first, then merges the framework's main from the `upstream`
# remote, rebuilds the pack links, and reports what instance-template/ changed since this
# instance was instantiated (your instantiated copies are yours; nothing rewrites them).
#
#   scripts/upgrade.sh             # upgrade
#   scripts/upgrade.sh --check     # report only: commits behind, integrity, template drift
#
# A repository that was an instance BEFORE it had the framework's history (its own
# contract in the root CLAUDE.md, framework folders mounted as symlinks, its own hooks
# and ignores) is adopted once, with the copy of this script on the fetched framework.
# That pipes whatever `upstream` serves into bash, so check the remote first:
#
#   git remote get-url upstream      # https://github.com/meta-agentic/meta-os.git, or a fork you trust
#   git fetch upstream && git show upstream/main:scripts/upgrade.sh | bash -s -- --adopt --dry-run
#
# Options
#   --check          report, change nothing (exit 0 even when behind)
#   --adopt          first merge into a pre-existing instance (scripts/adopt.py): moves the
#                    root contract to .claude/CLAUDE.md, removes symlink mounts at framework
#                    paths, moves instance hooks and ignore rules to their extension points,
#                    lists every other instance file the framework's version would replace
#   --dry-run        print the plan and write nothing — no fetch, merge, commit, index or
#                    exclude change (with --adopt: the adoption plan; without: as --check)
#   --yes            with --adopt: accept replacing the instance content the plan lists
#   --remote NAME    the framework remote (default: upstream)
#   --branch NAME    the framework branch (default: main)
#   --force          merge even though a framework path was edited here (you resolve what conflicts)
#   --no-sync        skip scripts/packs.sh sync after the merge
#   --ack-template   record the merged framework commit as the template ref in meta-os.config.json,
#                    after you have reviewed the template diff this script reports
#   -h, --help       this text
set -euo pipefail

die() { echo "upgrade: $*" >&2; exit 1; }
say() { printf '%s\n' "$*"; }
usage() { if [ -f "$0" ]; then sed -n '2,/^set -euo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'; else echo "see systems/distribution.md"; fi; }

remote=upstream branch=main check=0 force=0 sync=1 ack=0 adopt=0 dry=0 yes=0
while [ $# -gt 0 ]; do
  case "$1" in
    --check) check=1; shift ;;
    --remote) remote="${2:?}"; shift 2 ;;  --remote=*) remote="${1#*=}"; shift ;;
    --branch) branch="${2:?}"; shift 2 ;;  --branch=*) branch="${1#*=}"; shift ;;
    --force) force=1; shift ;;
    --no-sync) sync=0; shift ;;
    --ack-template) ack=1; shift ;;
    --adopt) adopt=1; shift ;;
    --dry-run) dry=1; shift ;;
    --yes|-y) yes=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option '$1' (see --help)" ;;
  esac
done
[ "$adopt" = 0 ] || [ "$check" = 0 ] || dry=1    # --adopt --check is the adoption's dry run
[ "$dry" = 0 ] || check=1        # a dry run never merges, with --adopt or without

root=$(git rev-parse --show-toplevel 2>/dev/null) || die "not inside a git checkout"
cd "$root"
target="$remote/$branch"
if [ ! -f .claude/CLAUDE.md ] && [ "$adopt" = 0 ]; then
  cat >&2 <<MSG
upgrade: this checkout is not bootstrapped (no .claude/CLAUDE.md).
  A fresh clone of meta-os:            scripts/bootstrap.sh   (a plain framework checkout just pulls)
  An instance with its own history:    git fetch $remote && git show $target:scripts/upgrade.sh | bash -s -- --adopt --dry-run
MSG
  exit 1
fi
git remote | grep -qx "$remote" || die "no remote '$remote' — scripts/bootstrap.sh configures it, or: git remote add upstream https://github.com/meta-agentic/meta-os.git"
# The gate scopes itself to the paths the framework tracks at this ref (scripts/validate_framework.py).
export META_OS_FRAMEWORK_REF="$target"

cfg=meta-os.config.json
template_ref() { [ -f "$cfg" ] && sed -n 's/.*"template": *"\([0-9a-f]\{7,40\}\)".*/\1/p' "$cfg" | head -1 || true; }

# --- 0. fetch ----------------------------------------------------------------------
if [ "$dry" = 1 ]; then
  say "upgrade — dry run on the already fetched $target (nothing is fetched or written)"
  git rev-parse -q --verify "$target^{commit}" >/dev/null || die "no $target yet — git fetch $remote first"
else
  say "upgrade — fetching $target"
  git fetch -q "$remote" "$branch" || die "fetch from '$remote' failed"
  git rev-parse -q --verify "$target^{commit}" >/dev/null || die "no $target after fetch"
fi
# This run executes (and merges) what that remote serves: name it, and flag one that is not
# the public framework repository.
url=$(git remote get-url "$remote")
norm() { printf '%s' "${1%/}" | sed -e 's|\.git$||' -e 's|^git@github\.com:|https://github.com/|'; }
if [ "$(norm "$url")" != "https://github.com/meta-agentic/meta-os" ]; then
  say "  note: $remote is $url, not the public framework repository — make sure you trust it"
fi
head=$(git rev-parse HEAD); new=$(git rev-parse "$target")
base=$(git merge-base HEAD "$target" 2>/dev/null || true)
behind=$(git rev-list --count "HEAD..$target")
say "  framework: $(git rev-parse --short "$target") on $target ($url) — this instance is $behind commit(s) behind"

# --- adopt: the first merge into a pre-existing instance -----------------------------------
if [ "$adopt" = 1 ]; then
  if [ -n "$base" ]; then
    say "  this repository already shares history with $target — nothing to adopt; this is an ordinary upgrade$([ "$check" = 1 ] && echo ", reported only")"
    [ -f .claude/CLAUDE.md ] || die "no .claude/CLAUDE.md — move the instance contract there by hand, then re-run"
  else
    command -v python3 >/dev/null 2>&1 || die "--adopt needs python3"
    aargs=(--target "$target"); [ "$dry" = 0 ] || aargs+=(--dry-run); [ "$yes" = 0 ] || aargs+=(--yes)
    # Read from the fetched framework, not the working tree: the instance may not carry it yet.
    # stdin stays the caller's (this script may itself be arriving on it).
    python3 <(git show "$target:scripts/adopt.py") "${aargs[@]}" </dev/null || exit 1
    [ "$dry" = 0 ] || exit 0
    if [ "$sync" = 1 ]; then scripts/packs.sh sync | sed 's/^/  /'; fi
    if command -v python3 >/dev/null 2>&1 && python3 -c 'import yaml' 2>/dev/null; then
      if python3 scripts/validate_framework.py >/dev/null 2>&1; then say "  framework self-check: ok"
      else say "  framework self-check reports problems — run: python3 scripts/validate_framework.py"; fi
    fi
    say "done — adopted; from now on scripts/upgrade.sh is an ordinary merge"
    say "  enable the hooks once per clone: git config core.hooksPath .githooks"
    exit 0
  fi
fi

# --- 1. core integrity: has this instance edited a framework path? ----------------------
# Framework paths = what the framework tracks at the merge base (or at the target, for an
# unrelated history). An instance may ADD paths anywhere; it may not modify or delete these.
say "  integrity: framework paths edited in this instance"
ref_for_core="${base:-$new}"
violations=$(git diff --name-only --diff-filter=MDT "${base:-$(git hash-object -t tree /dev/null)}" HEAD -- 2>/dev/null \
             | grep -xF -f <(git ls-tree -r --name-only "$ref_for_core") || true)
if [ -n "$violations" ]; then
  say "$violations" | sed 's/^/    edited: /'
  if [ "$check" = 0 ] && [ "$force" = 0 ]; then
    cat >&2 <<MSG
upgrade: refusing — the paths above belong to the framework and were changed here.
  A framework change is made in a public checkout of meta-os and proposed upstream; this
  instance takes it with the next upgrade. To restore a path to the framework's version:
    git checkout $ref_for_core -- <path>
  To carry the edit anyway and resolve any conflict yourself: scripts/upgrade.sh --force
MSG
    exit 1
  fi
else
  say "    none"
fi

# --- 2. template drift since instantiation -------------------------------------------
tref=$(template_ref)
if [ -n "$tref" ] && git rev-parse -q --verify "$tref^{commit}" >/dev/null 2>&1; then
  drift=$(git diff --stat "$tref" "$target" -- instance-template/ || true)
else
  [ -z "$tref" ] || say "  template ref '$tref' from $cfg is not a known commit — comparing from the merge base instead"
  tref="${base:-}"; drift=""
  [ -z "$tref" ] || drift=$(git diff --stat "$tref" "$target" -- instance-template/ || true)
fi
if [ -n "$drift" ]; then
  say "  template: instance-template/ changed since this instance was instantiated (${tref:0:12}):"
  say "$drift" | sed 's/^/    /'
  say "    your instantiated copies are yours and were not rewritten; review a file with"
  say "      git diff ${tref:0:12} $target -- instance-template/root/<path>"
  say "    apply what you want by hand, then: scripts/upgrade.sh --ack-template"
else
  say "  template: unchanged since instantiation"
fi

if [ "$check" = 1 ]; then
  say "check only — nothing changed"
  exit 0
fi

# --- 3. merge -------------------------------------------------------------------------
if [ "$behind" = 0 ]; then
  say "  already current"
else
  git diff --quiet && git diff --cached --quiet || die "the working tree has uncommitted changes — commit or stash them first"
  if [ -z "$base" ]; then
    say "  no shared history with $target (the repository was created from a template rather than cloned) — first merge"
    if ! git merge -q --allow-unrelated-histories --no-edit "$target" >/dev/null 2>&1; then
      # Every conflict here is add/add on a framework path whose two sides differ only by
      # the framework's own later changes (integrity passed above), so the framework's
      # version is the right one. An instance path cannot conflict: the framework tracks none.
      # A path is the framework's if the framework tracks it or a file below it. A symlink or
      # a file where the framework has a folder conflicts under a renamed path: git parks
      # that side as <path>~HEAD (or <path>~<remote>_<branch>), so the suffix is stripped.
      conflicted=$(git diff --name-only --diff-filter=U)
      fw_paths=$(git ls-tree -r --name-only "$new")
      parked="~${target//\//_}"
      real_path() { local p="${1%~HEAD}"; printf '%s' "${p%"$parked"}"; }
      is_fw() { printf '%s\n' "$fw_paths" | awk -v p="$1" '$0 == p || index($0, p "/") == 1 { f = 1; exit } END { exit !f }'; }
      bad=$(printf '%s\n' "$conflicted" | while IFS= read -r c; do [ -z "$c" ] || is_fw "$(real_path "$c")" || echo "$c"; done)
      if [ -n "$bad" ]; then git merge --abort; die "conflicts outside the framework paths — resolve by hand:"$'\n'"$bad"; fi
      printf '%s\n' "$conflicted" | while IFS= read -r c; do
        [ -n "$c" ] || continue
        p=$(real_path "$c")
        git rm -q -r --cached --ignore-unmatch -- "$c" "$p" >/dev/null
        rm -rf -- "$c" "$p"
        git checkout -q "$new" -- "$p"
      done
      git commit -q --no-edit
      say "  resolved $(printf '%s\n' "$conflicted" | grep -c .) framework path(s) to the framework's version (first merge of unrelated histories)"
    fi
  else
    if ! git merge -q --no-edit "$target"; then
      cat >&2 <<MSG
upgrade: the merge has conflicts — resolve them, then: git commit && scripts/packs.sh sync
  (a conflict can only involve a framework path this instance changed, or a path both
  sides added; the instance's own paths are never touched by the framework)
MSG
      exit 1
    fi
  fi
  say "  merged: $(git rev-parse --short "$head")..$(git rev-parse --short HEAD) ($behind framework commit(s))"
fi

# --- 4. rebuild the generated links ------------------------------------------------------------
if [ "$sync" = 1 ]; then scripts/packs.sh sync | sed 's/^/  /'; fi

# --- 5. self-check (framework paths only in an instance) ------------------------------------------
if command -v python3 >/dev/null 2>&1 && python3 -c 'import yaml' 2>/dev/null; then
  if python3 scripts/validate_framework.py >/dev/null 2>&1; then say "  framework self-check: ok"
  else say "  framework self-check reports problems — run: python3 scripts/validate_framework.py"; fi
fi

# --- 6. record the reviewed template ref ------------------------------------------------------------
if [ "$ack" = 1 ]; then
  cur=$(template_ref)
  if [ -n "$cur" ] && [ -f "$cfg" ]; then
    sed -e "s/\"template\": *\"$cur\"/\"template\": \"$new\"/" "$cfg" > "$cfg.tmp" && mv "$cfg.tmp" "$cfg"
    say "  template ref recorded: ${new:0:12} (commit $cfg)"
  else
    say "  no template ref in $cfg to update"
  fi
fi
say "done — instance paths untouched; framework at $(git rev-parse --short "$target")"
