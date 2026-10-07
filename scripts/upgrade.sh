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
# Options
#   --check          report, change nothing (exit 0 even when behind)
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
usage() { sed -n '2,/^set -euo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'; }

remote=upstream branch=main check=0 force=0 sync=1 ack=0
while [ $# -gt 0 ]; do
  case "$1" in
    --check) check=1; shift ;;
    --remote) remote="${2:?}"; shift 2 ;;  --remote=*) remote="${1#*=}"; shift ;;
    --branch) branch="${2:?}"; shift 2 ;;  --branch=*) branch="${1#*=}"; shift ;;
    --force) force=1; shift ;;
    --no-sync) sync=0; shift ;;
    --ack-template) ack=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option '$1' (see --help)" ;;
  esac
done

root=$(git rev-parse --show-toplevel 2>/dev/null) || die "not inside a git checkout"
cd "$root"
[ -f .claude/CLAUDE.md ] || die "this checkout is not bootstrapped — run scripts/bootstrap.sh first (a plain framework checkout just pulls)"
git remote | grep -qx "$remote" || die "no remote '$remote' — scripts/bootstrap.sh configures it, or: git remote add upstream https://github.com/meta-agentic/meta-os.git"
target="$remote/$branch"

cfg=meta-os.config.json
template_ref() { [ -f "$cfg" ] && sed -n 's/.*"template": *"\([0-9a-f]\{7,40\}\)".*/\1/p' "$cfg" | head -1 || true; }

# --- 0. fetch ----------------------------------------------------------------------
say "upgrade — fetching $target"
git fetch -q "$remote" "$branch" || die "fetch from '$remote' failed"
git rev-parse -q --verify "$target^{commit}" >/dev/null || die "no $target after fetch"
head=$(git rev-parse HEAD); new=$(git rev-parse "$target")
base=$(git merge-base HEAD "$target" 2>/dev/null || true)
behind=$(git rev-list --count "HEAD..$target")
say "  framework: $(git rev-parse --short "$target") on $target — this instance is $behind commit(s) behind"

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
      conflicted=$(git diff --name-only --diff-filter=U)
      bad=$(printf '%s\n' "$conflicted" | grep -vxF -f <(git ls-tree -r --name-only "$new") || true)
      if [ -n "$bad" ]; then git merge --abort; die "conflicts outside the framework paths — resolve by hand:"$'\n'"$bad"; fi
      printf '%s\n' "$conflicted" | while IFS= read -r p; do [ -n "$p" ] && git checkout -q --theirs -- "$p" && git add -- "$p"; done
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
