#!/usr/bin/env bash
# Skill packs — mount curated skill collections into this instance.
# Contract: systems/packs.md; registry: systems/packs.yaml. A pack is a pinned submodule
# at .packs/<name>. In the one-repository layout (systems/distribution.md) the framework's
# own skills are real folders in skills/; a mounted pack's skills are linked in BESIDE them
# as per-skill relative symlinks, and the whole of skills/ is mirrored into .claude/skills/
# for project-local discovery.
#
# Rules encoded here:
#   - the framework wins on name collision (a real folder in skills/ always wins a link);
#     earlier-mounted packs win over later ones
#   - real (non-symlink) entries in skills/ — the framework's or the instance's own —
#     are never touched; sync only manages symlinks; re-run after any framework or pack bump
#   - a dangling mount (pack or skill link pointing at nothing) is refused, never skipped
#   - every link sync writes is GENERATED and never committed: the pack links in skills/
#     are listed in $GIT_DIR/info/exclude by sync itself, .claude/{skills,agents,hooks}/
#     are ignored by the framework's .gitignore (no generated artifact is
#     version-controlled)
#   - sync also copies the instance's own ignore rules (.gitignore.instance) into the same
#     $GIT_DIR/info/exclude — the root .gitignore is the framework's, so that file is the
#     instance's extension point for root-level rules (systems/distribution.md)
#
# A first-party pack lives in a subdirectory of the disciplines monorepo (`path:` in the registry
# or the manifest): the repository is mounted at .packs/<name> as a sparse submodule and the pack
# is read from .packs/<name>/<path>. A pack key that was renamed (`renamed-from:` in the registry)
# still works for a minor version with a warning; `migrate` rewrites an instance to the new keys.
#
# This is the framework's single home of the script. Earlier it was vendored per instance
# from the instance template, and the fixes an instance made to its copy (pin enforcement,
# name validation, worktree-safe remove, config block parsing, dangling-mount refusal)
# reached no other instance; folding the template into this repository ended that.
set -euo pipefail

die() { echo "packs.sh: $*" >&2; exit 1; }
# A pack name becomes a path under .packs/: `remove 'agile/..'` would deinit -f every pack.
valid_name() { [[ "$1" =~ ^[a-zA-Z0-9_-]+$ ]] || die "invalid pack name '$1' (allowed: letters, digits, _ and -)"; }
[ -f CLAUDE.md ] && [ -d skills ] && [ -d systems ] || die "run from the repository root (the folder holding CLAUDE.md, skills/ and systems/)"

registry_name() { # <key> → the registry key now carrying it: itself, or the entry whose renamed-from lists it
  [ -f systems/packs.yaml ] || { echo "$1"; return; }
  awk -v k="$1" '
    /^  [a-zA-Z0-9_-]+:/ { cur=$1; sub(/:$/,"",cur); if (cur == k) exact=1 }
    $1 == "renamed-from:" { l=$0; sub(/^[^:]*:/,"",l); gsub(/[][,"\047]/," ",l)
                            n=split(l,a," "); for (i=1;i<=n;i++) if (a[i] == k) hit=cur }
    END { print (exact || hit == "") ? k : hit }
  ' systems/packs.yaml
}
registry_field() { # <pack> <field> → value from systems/packs.yaml, empty if absent (a renamed key reads its new entry)
  [ -f systems/packs.yaml ] || return 0
  local key; key=$(registry_name "$1")
  awk -v p="$key" -v f="$2:" '
    $0 ~ "^  "p":$" { inpack=1; next }
    inpack && /^  [a-zA-Z0-9_-]+:/ { inpack=0 }
    inpack && $1 == f { $1=""; sub(/^ /,""); gsub(/"/,""); print; exit }
  ' systems/packs.yaml
}

# Emit the skill folders a pack provides, one repo-relative path per line.
# Two layouts, in priority order:
#   1. .claude-plugin/plugin.json present → its skills[] paths are AUTHORITATIVE
#      (respects the author's own inclusions/exclusions, e.g. skipping deprecated/).
#   2. otherwise → discover SKILL.md recursively (any depth), so category-nested
#      collections (skills/<category>/<skill>/) and flat ones both work.
pack_skill_dirs() {
  local p="$1" rel
  if [ -f "$p/.claude-plugin/plugin.json" ]; then
    # every "./…" token in the manifest is a skill path (name/desc carry no ./)
    grep -o '"\./[^"]*"' "$p/.claude-plugin/plugin.json" | tr -d '"' | while read -r rel; do
      rel="${rel#./}"
      [ -f "$p/$rel/SKILL.md" ] && echo "$p/$rel"
    done
  else
    find "$p" -name .git -prune -o -name SKILL.md -print 2>/dev/null | while read -r f; do
      dirname "$f"
    done
  fi
}

# --- declarative manifest (.packs.yaml at the instance root) ------------------
# Desired-state list of packs; `apply` reconciles mounts to it. This is what makes
# headless installs possible (container/CI: write the manifest, run apply).
MANIFEST=.packs.yaml

manifest_names() {
  [ -f "$MANIFEST" ] || return 0
  awk '/^packs:/{inp=1;next} inp && /^  [a-zA-Z0-9_-]+:/{gsub(/[: ]/,"");print}' "$MANIFEST"
}
manifest_field() { # <name> <field> → that field of the pack's entry (repo, install, plugin), if any
  [ -f "$MANIFEST" ] || return 0
  awk -v p="$1" -v f="$2:" '
    $0 ~ "^  "p":" { inpack=1; next }
    inpack && /^  [a-zA-Z0-9_-]+:/ { inpack=0 }
    inpack && /^    [a-z]/ && $1 == f { gsub(/["\047]/,"",$2); print $2; exit }   # entry level, not config:
  ' "$MANIFEST"
}
# Where a pack's own tree is: .packs/<name>, or .packs/<name>/<path> for a pack that lives in
# a subdirectory of its repository (the manifest's `path:` wins over the registry's).
norm_url() { printf '%s' "${1%/}" | sed -e 's|\.git$||' -e 's|^git@github\.com:|https://github.com/|'; }
submodule_key() { # <name> → the submodule's name in .gitmodules (it keeps the name it was added under when `migrate` moves the path)
  [ -f .gitmodules ] || return 0
  git config -f .gitmodules --get-regexp '^submodule\..*\.path$' 2>/dev/null \
    | awk -v p=".packs/$1" '$2 == p { print $1 }' | sed -e 's/^submodule\.//' -e 's/\.path$//' | head -1
}
mount_url() { # <name> → the repository the mount was made from: .gitmodules, else the manifest's repo:
  local k u; k=$(submodule_key "$1")
  [ -z "$k" ] || u=$(git config -f .gitmodules "submodule.$k.url" 2>/dev/null || true)
  echo "${u:-$(manifest_field "$1" repo)}"
}
# The registry's path: describes the registry's repository. A mount made from another one (an
# instance mounted before the monorepo, from the pack's own repository) is the whole pack.
pack_subpath() { # <name> → the path inside the mount, empty for a whole-repository pack
  local sub src reg; sub=$(manifest_field "$1" path)
  if [ -z "$sub" ]; then
    sub=$(registry_field "$1" path)
    if [ -n "$sub" ]; then
      src=$(mount_url "$1"); reg=$(registry_field "$1" repo)
      if [ -n "$src" ] && [ "$(norm_url "$src")" != "$(norm_url "$reg")" ]; then sub=""; fi
    fi
  fi
  sub="${sub#/}"; sub="${sub%/}"
  if [ -n "$sub" ]; then case "/$sub/" in */../*|*//*) die "pack '$1': path '$sub' must be a plain relative directory" ;; esac; fi
  echo "$sub"
}
pack_dir() { local sub; sub=$(pack_subpath "$1"); echo ".packs/$1${sub:+/$sub}"; }

# A pack installed as a Claude Code plugin (`install: plugin`): install_mode, is_plugin,
# plugin_id, plugin_drift, plugin_pack_yaml, plugin_list, not_a_plugin.
# shellcheck source=scripts/packs_plugin.sh
. "$(dirname "${BASH_SOURCE[0]}")/packs_plugin.sh"
manifest_add() {
  [ -f "$MANIFEST" ] || printf '# Desired packs — reconciled by scripts/packs.sh apply\npacks:\n' > "$MANIFEST"
  grep -q "^  $1:" "$MANIFEST" && return 0
  # Registry packs carry no repo: line (URL lives in the registry). Guard the
  # optional line with an explicit if — a bare `[ -n "$2" ] && echo` returns
  # non-zero when $2 is empty and would trip `set -e`, aborting the caller.
  echo "  $1:" >> "$MANIFEST"
  if [ -n "${2:-}" ]; then echo "    repo: $2" >> "$MANIFEST"; fi
  return 0
}
manifest_remove() {
  [ -f "$MANIFEST" ] || return 0
  awk -v p="$1" '
    $0 ~ "^  "p":" { skip=1; next }
    skip && /^    / { next }
    { skip=0; print }
  ' "$MANIFEST" > "$MANIFEST.tmp" && mv "$MANIFEST.tmp" "$MANIFEST"
}

# --- pack config resolution ----------------------------------------------------
# A pack's parameters live under packs.<name>.config in the manifest; the pack
# declares its schema + defaults in pack.yaml. `config` prints the resolved
# key=value pairs (defaults filled in) and validates enums against the schema.
manifest_config() { # <pack> <key> → configured value, empty if unset
  # A block value (key alone on its line, children indented below) is returned as one flow
  # value — a map as `{child: v, …}`, a sequence as `[a, b]` — so it is never silently
  # resolved to empty. A bare `key:` with no children is null: empty.
  [ -f "$MANIFEST" ] || return 0
  awk -v p="$1" -v k="$2:" '
    function clean(v,  i) {           # trailing comment dropped only outside quotes
      sub(/^[ \t]+/,"",v)
      if (v ~ /^"/) { v=substr(v,2); i=index(v,"\""); if (i) v=substr(v,1,i-1); return v }
      sub(/[ \t]+#.*$/,"",v); gsub(/"/,"",v); sub(/[ \t]+$/,"",v); return v }
    function flush() { if (out != "") print (seq ? "[" out "]" : "{" out "}"); done=1 }
    inblk {
      if ($0 ~ /^[ \t]*(#|$)/) next
      if ($0 ~ /^      +- / || $0 ~ /^        /) {
        c=clean($0); if (c ~ /^- /) { seq=1; sub(/^- +/,"",c) }
        gsub(/[ \t]+/," ",c); out = out (out == "" ? "" : ", ") c; next }
      flush(); exit }
    $0 ~ "^  "p":" { inpack=1; next }
    inpack && /^  [a-zA-Z0-9_-]+:/ { inpack=0; incfg=0 }
    /^[^ #]/ { inpack=0; incfg=0 }
    inpack && /^    config:/ { incfg=1; next }
    incfg && /^    [a-zA-Z]/ { incfg=0 }
    incfg && $1 == k { $1=""; v=clean($0); if (v == "") { inblk=1; next } print v; done=1; exit }
    END { if (inblk && !done) flush() }
  ' "$MANIFEST"
}
pack_yaml_field() { # <pack.yaml> <key> <default|one_of> → value from the pack's manifest
  # Two manifest shapes are accepted, because the contract changed under the packs:
  #   inline map   key: { default: x, one_of: a | b }      ← the original shape
  #   block        key:                                    ← what pack.schema.json
  #                  default: x                              requires today (a `doc:`
  #                  one_of: a | b                            with commas cannot live
  #                  doc: "…"                                 in a comma-split inline map)
  # Every shipped first-party pack now uses the block form; reading only the inline form
  # resolved every default to empty AND skipped enum validation silently.
  local f="$1"; [ -f "$f" ] || return 0
  awk -v k="  $2:" -v want="$3" '
    function emit(v) { gsub(/[][]/,"",v); sub(/^ +/,"",v); sub(/ +$/,"",v)
                       gsub(/ *\| */,"|",v); sub(/^"/,"",v); sub(/"$/,"",v); print v; exit }
    index($0,k)==1 && index($0,"{")>0 {                       # inline map
      line=$0; sub(/[^{]*{/,"",line); sub(/}.*/,"",line)
      n=split(line,pairs,","); for(i=1;i<=n;i++){ split(pairs[i],kv,":")
        g=kv[1]; sub(/^ */,"",g); sub(/ *$/,"",g)
        if(g==want){ emit(substr(pairs[i],index(pairs[i],":")+1)) } }
      next }
    index($0,k)==1 { inkey=1; next }                          # block form starts
    inkey && /^  *[a-zA-Z_-]+:/ && !/^    / { inkey=0 }       # next key at key level ends it
    inkey && index($0,"    " want ":")==1 { emit(substr($0,index($0,":")+1)) }
  ' "$f"
}
# --- renamed pack keys ----------------------------------------------------------
# An instance still keyed by an old name (the registry's `renamed-from:`) keeps working for a
# minor version: every command reads the entry it has, and says once that the key is deprecated.
# `migrate` rewrites the keys. A name given on the command line may be either spelling.
config_key() { # <name> → the key this manifest uses for the pack that <name> names
  local want k; want=$(registry_name "$1")
  manifest_names | grep -qx -- "$1" && { echo "$1"; return; }
  for k in $(manifest_names); do
    if [ "$(registry_name "$k")" = "$want" ]; then
      echo "warn: pack '$1' is keyed '$k' in $MANIFEST — read as the same pack" >&2
      echo "$k"; return
    fi
  done
  echo "$1"
}
deprecated_keys() { # one line per manifest key the registry has renamed
  local k n
  for k in $(manifest_names); do
    n=$(registry_name "$k")
    [ "$n" = "$k" ] || echo "deprecated pack key: '$k' is now '$n' ($MANIFEST; run scripts/packs.sh migrate)"
  done
}
check_paths() { local n; for n in $(manifest_names); do pack_subpath "$n" >/dev/null; done; }   # dies in this shell on a bad path
warn_deprecated() { local l; deprecated_keys | while read -r l; do echo "warn: $l" >&2; done; }

cmd_config() {
  local pack="${1:?usage: packs.sh config <pack> [key]}" key="${2:-}"
  valid_name "$pack"
  pack=$(config_key "$pack")
  local schema keys mkeys missing=""
  [[ "$(install_mode "$pack")" =~ ^(plugin|submodule)$ ]] || die "$(plugin_drift config | grep -F "for $pack:")"
  if is_plugin "$pack"; then   # never fails for want of the plugin: the instance values still print
    schema=$(plugin_pack_yaml "$pack"); [ -n "$schema" ] || missing=1
  else
    schema="$(pack_dir "$pack")/pack.yaml"
    [ -L ".packs/$pack" ] && [ ! -e ".packs/$pack" ] \
      && die "pack '$pack' is a dangling mount (.packs/$pack -> $(readlink ".packs/$pack")) — refusing"
    [ -d ".packs/$pack" ] || die "pack '$pack' is not mounted"
  fi
  mkeys=$(awk -v p="$pack" '$0~"^  "p":"{ip=1;next} ip&&/^  [a-zA-Z0-9_-]+:/{ip=0;c=0} /^[^ #]/{ip=0;c=0} ip&&/^    config:/{c=1;next} c&&/^      [a-zA-Z]/{k=$1;sub(/:.*/,"",k);print k} c&&/^    [a-zA-Z]/{c=0}' "$MANIFEST")
  if [ -f "$schema" ]; then
    keys=$(awk '/^config:/{c=1;next} c&&/^  [a-zA-Z]/{k=$1;sub(/:.*/,"",k);print k} c&&/^[a-zA-Z]/{c=0}' "$schema")
  else
    keys=$mkeys
  fi
  if [ -n "$key" ] && [ -z "$missing" ] && ! printf '%s\n' "$keys" | grep -qxF -- "$key"; then
    die "unknown config key '$pack.$key' (known: ${keys//$'\n'/ })"
  fi
  local k v oneof rc=0
  [ -n "$key" ] || for k in $mkeys; do   # a misspelled manifest key would otherwise fall back to the default unnoticed
    printf '%s\n' "$keys" | grep -qxF -- "$k" || { echo "warn: $pack.$k in $MANIFEST is not a key of $schema" >&2; rc=1; }
  done
  for k in $keys; do
    v=$(manifest_config "$pack" "$k"); [ -z "$v" ] && v=$(pack_yaml_field "$schema" "$k" default)
    if [ -n "$key" ]; then [ "$k" = "$key" ] && printf '%s\n' "$v"; continue; fi
    printf '%s=%s\n' "$k" "$v"
    # one_of is pipe-separated in pack.yaml (commas would break the inline map)
    oneof=$(pack_yaml_field "$schema" "$k" one_of)
    if [ -n "$v" ] && [ -n "$oneof" ] && ! printf '|%s|' "$oneof" | grep -qF -- "|$v|"; then
      echo "warn: $pack.$k='$v' not in {$oneof}" >&2; rc=1
    fi
  done
  return $rc
}

# --- dangling-mount refusal ----------------------------------------------------
# A mount that points at nothing used to be skipped: `.packs/*/` never matches a broken
# symlink, an uninitialised submodule mounts zero skills, and a hand-made skill link to
# a moved pack stays advertised while resolving to nothing. Report every one, then refuse.
dangling_packs() {
  local p
  for p in .packs/*; do
    [ -e "$p" ] || [ -L "$p" ] || continue
    if [ -L "$p" ] && [ ! -e "$p" ]; then
      echo "dangling mount: $p -> $(readlink "$p")"
    elif [ -d "$p" ] && [ -z "$(ls -A "$p")" ]; then
      echo "dangling mount: $p is empty (submodule not initialised? git submodule update --init $p)"
    elif [ -d "$p" ] && manifest_names | grep -qx -- "$(basename "$p")" && ! is_plugin "$(basename "$p")" \
         && [ ! -d "$(pack_dir "$(basename "$p")")" ]; then
      echo "dangling mount: $p has no $(pack_subpath "$(basename "$p")") (the path the registry or $MANIFEST gives for the pack)"
    fi
  done
}
dangling_links() {
  local d l
  for d in skills .claude/skills .claude/agents .claude/hooks; do
    [ -d "$d" ] && [ ! -L "$d" ] || continue
    for l in "$d"/*; do
      if [ -L "$l" ] && [ ! -e "$l" ]; then echo "dangling mount: $l -> $(readlink "$l")"; fi
    done
  done
}
manifest_drift() { # mounts must match the manifest both ways
  local name p
  plugin_drift check
  for name in $(manifest_names); do
    [ "$(install_mode "$name")" != submodule ] || [ -d ".packs/$name" ] \
      || echo "declared but not mounted: $name (run scripts/packs.sh apply)"
  done
  for p in .packs/*; do
    [ -e "$p" ] || [ -L "$p" ] || continue
    name=$(basename "$p")
    manifest_names | grep -qxF -- "$name" || echo "mounted but not declared: $name (run scripts/packs.sh apply)"
  done
}
pin_drift() { # each initialised pack must sit, unmodified, at the commit its gitlink records
  local name p want have
  # The old hand-made layout (.packs/<pack> -> a dev clone) must not satisfy a pinned mount.
  for p in $(git ls-files -s -- .packs | awk '$1 == "160000" { print $4 }'); do
    if [ -L "$p" ]; then echo "symlink mount: $p -> $(readlink "$p") where a pinned submodule is recorded (remove the link, then scripts/packs.sh apply)"; fi
  done
  for name in $(manifest_names); do
    p=".packs/$name"
    [ -d "$p" ] && [ ! -L "$p" ] && [ -e "$p/.git" ] && ! is_plugin "$name" || continue
    want=$(git ls-files -s -- "$p" | awk '$1 == "160000" { print $2 }')
    [ -n "$want" ] || continue
    have=$(git -C "$p" rev-parse HEAD 2>/dev/null || echo none)
    [ "$want" = "$have" ] || echo "stale mount: $p is at ${have:0:7}, pinned ${want:0:7} (run scripts/packs.sh apply)"
    if [ -n "$(git -C "$p" status --porcelain 2>/dev/null)" ]; then
      echo "modified mount: $p has local changes — packs are edited in their own repo, then bumped (git -C $p status)"
    fi
  done
}
# The pack links to place in skills/, as name<TAB>link-target, in precedence order: packs
# in mount-name order, first name wins. A real (non-symlink) entry in skills/ — a framework
# skill or the instance's own — always wins and is left out. `warn` reports what got shadowed.
union_plan() {
  local d p name t
  {
    for p in .packs/*/; do
      [ -d "$p" ] && ! is_plugin "$(basename "$p")" || continue
      pack_skill_dirs "$(pack_dir "$(basename "$p")")" | while read -r d; do printf '%s\t../%s\n' "$(basename "$d")" "$d"; done
    done
  } | awk -F'\t' -v warn="${1:-}" '
      seen[$1]++ { if (warn) printf "warn: %s -> %s is shadowed by an earlier skill — skipped\n", $1, $2 > "/dev/stderr"; next }
      { print }' |
  while IFS=$'\t' read -r name t; do
    if [ -e "skills/$name" ] && [ ! -L "skills/$name" ]; then
      [ -z "${1:-}" ] || echo "warn: '$name' from $t is shadowed by the real skills/$name — skipped" >&2
      continue
    fi
    printf '%s\t%s\n' "$name" "$t"
  done
}
# The pack links are generated, so they are never committed: sync keeps them listed in
# $GIT_DIR/info/exclude (per clone, below the framework's .gitignore in precedence, which
# is exactly right — the framework cannot name them, an instance must not commit them).
EXCLUDE_BEGIN="# >>> meta-os scripts/packs.sh — generated pack links in skills/ (do not edit) >>>"
EXCLUDE_END="# <<< meta-os scripts/packs.sh <<<"
INSTANCE_IGNORE=.gitignore.instance
IGNORE_BEGIN="# >>> meta-os scripts/packs.sh — copied from $INSTANCE_IGNORE (edit that file, then sync) >>>"
IGNORE_END="# <<< meta-os $INSTANCE_IGNORE <<<"
exclude_generated() {
  local f; f=$(git rev-parse --git-path info/exclude 2>/dev/null) || return 0
  mkdir -p "$(dirname "$f")"; [ -f "$f" ] || : > "$f"
  { awk -v b="$EXCLUDE_BEGIN" -v e="$EXCLUDE_END" -v ib="$IGNORE_BEGIN" -v ie="$IGNORE_END" \
        '$0==b||$0==ib{skip=1;next} $0==e||$0==ie{skip=0;next} !skip' "$f"
    echo "$EXCLUDE_BEGIN"
    union_plan | while IFS=$'\t' read -r name _; do echo "/skills/$name"; done
    echo "$EXCLUDE_END"
    if [ -f "$INSTANCE_IGNORE" ]; then
      echo "$IGNORE_BEGIN"; cat "$INSTANCE_IGNORE"; echo; echo "$IGNORE_END"
    fi
  } > "$f.tmp" && mv "$f.tmp" "$f"
}
union_drift() { # skills/ links must match the plan, names and targets
  if [ -L skills ] || [ ! -d skills ]; then echo "skills/ is not a directory (run scripts/bootstrap.sh)"; return; fi
  local l have
  have=$(for l in skills/* skills/.[!.]*; do [ -L "$l" ] && printf '%s\t%s\n' "${l#skills/}" "$(readlink "$l")"; done | sort)
  [ "$(union_plan | sort)" = "$have" ] || echo "skills/ pack links are stale against the mounted packs (run scripts/packs.sh sync)"
}
refuse_found() { # <findings> — print each, then refuse
  [ -z "$1" ] && return 0
  printf '%s\n' "$1" >&2
  die "refusing: $(printf '%s\n' "$1" | wc -l | tr -d ' ') problem(s) — fix them, then re-run"
}
refuse_dangling() { refuse_found "$("$1")"; }
cmd_check() {
  check_paths
  warn_deprecated
  refuse_found "$(dangling_packs; dangling_links; manifest_drift; pin_drift; union_drift)"
  echo "check: mounts match $MANIFEST and their pins, no dangling mounts, union current"
}

cmd_sync() {
  check_paths
  refuse_dangling dangling_packs
  [ -d skills ] && [ ! -L skills ] || die "skills/ is not a directory — this is not a meta-os checkout"
  find skills -maxdepth 1 -type l -exec rm {} +
  local name t n
  union_plan warn | while IFS=$'\t' read -r name t; do ln -s "$t" "skills/$name"; done
  exclude_generated
  n=$(find skills -maxdepth 1 -mindepth 1 -type l | wc -l | tr -d ' ')
  echo "skills/ — $(find skills -maxdepth 1 -mindepth 1 -type d | wc -l | tr -d ' ') framework/instance skills, $n pack links (generated, excluded from git)"
  if [ -f "$INSTANCE_IGNORE" ]; then
    echo "$INSTANCE_IGNORE — $(grep -cv '^[[:space:]]*\(#\|$\)' "$INSTANCE_IGNORE" || true) instance ignore rule(s) applied via info/exclude"
  fi
  sync_claude
  refuse_dangling dangling_links
}

# Project-local .claude/ enrichment — the engine's discovery surface. Skills mirror
# the union; agents come from packs (framework agents/ is a docs roster, not engine
# definitions). Pack HOOKS are STAGED under .claude/hooks/<pack>/ but never wired
# into settings.json automatically — enabling third-party executable hooks is an
# explicit, per-hook user decision.
sync_claude() {
  local s
  for s in .claude/skills .claude/agents .claude/hooks; do
    [ ! -L "$s" ] || die "$s is a symlink (-> $(readlink "$s")); packs.sh manages it as a directory of links — remove the link, then re-run"
  done
  mkdir -p .claude/skills .claude/agents .claude/hooks
  local d name p pname f b root
  find .claude/skills -maxdepth 1 -type l -exec rm {} +
  for d in skills/*/; do
    name=$(basename "$d")
    [ -e ".claude/skills/$name" ] || ln -s "../../skills/$name" ".claude/skills/$name"
  done
  find .claude/agents -maxdepth 1 -type l -exec rm {} +
  find .claude/hooks -maxdepth 1 -type l -exec rm {} +
  for p in .packs/*/; do
    [ -d "$p" ] && ! is_plugin "$(basename "$p")" || continue
    pname=$(basename "$p"); root=$(pack_dir "$pname")
    if [ -d "$root/agents" ]; then
      for f in "$root/agents"/*.md; do
        [ -f "$f" ] || continue
        b=$(basename "$f")
        if [ -e ".claude/agents/$b" ]; then
          echo "warn: agent '$b' from pack '$pname' collides — skipped" >&2
        else
          ln -s "../../$root/agents/$b" ".claude/agents/$b"
        fi
      done
    fi
    if [ -d "$root/hooks" ]; then
      ln -sfn "../../$root/hooks" ".claude/hooks/$pname"
      echo "hooks from '$pname' staged at .claude/hooks/$pname — review and wire explicitly in .claude/settings.json (never auto-enabled)"
    fi
  done
  echo ".claude/ enriched — $(find .claude/skills -maxdepth 1 -type l | wc -l | tr -d ' ') skills, $(find .claude/agents -maxdepth 1 -type l | wc -l | tr -d ' ') agents"
}

# A pack that lives in a subdirectory of a bigger repository checks out only that directory
# (cone mode keeps the repository's top-level files). Best effort: a git without sparse-checkout
# gets the whole tree, which only costs space; the pack is read from the same path either way.
sparse_pack() { # <name>
  local sub err; sub=$(pack_subpath "$1")
  [ -n "$sub" ] && [ -e ".packs/$1/.git" ] || return 0
  local rc=0; git sparse-checkout -h >/dev/null 2>&1 || rc=$?
  [ "$rc" = 129 ] || return 0                                             # a git without sparse-checkout: the whole tree
  err=$(git -C ".packs/$1" sparse-checkout set --cone -- "$sub" 2>&1) \
    || echo "warn: pack '$1': sparse checkout of $sub failed (the whole tree is checked out): $(printf '%s' "$err" | tail -n 1)" >&2
}
# Take a submodule that was just added back out, so a refused add leaves nothing recorded.
unmount_half() { # <name>
  local gd; gd=$(git rev-parse --git-path "modules/$(submodule_key "$1" || echo ".packs/$1")")
  git submodule deinit -f ".packs/$1" >/dev/null 2>&1 || true
  git rm -f -q ".packs/$1" >/dev/null 2>&1 || true
  rm -rf -- "$gd" ".packs/$1"
}

cmd_add() {
  local name="${1:?usage: packs.sh add <name> [repo-url]}" url="${2:-}"
  valid_name "$name"
  [ -e ".packs/$name" ] && die "pack '$name' is already mounted"
  if [ -z "$url" ]; then
    url=$(registry_field "$name" repo)
    [ -n "$url" ] || die "'$name' is not in the registry (systems/packs.yaml) — pass a repo url"
    local status prov lic
    status=$(registry_field "$name" status); prov=$(registry_field "$name" provenance); lic=$(registry_field "$name" license)
    [ "$status" = "planned" ] && die "'$name' is registered but not published yet (status: planned)"
    echo "registry: $name — provenance: ${prov:-?} · license: ${lic:-?}"
    [ "$lic" = "verify-at-add" ] && echo "note: check the upstream LICENSE before relying on this pack" >&2
  else
    echo "warn: '$name' is not from the curated registry — provenance unverified" >&2
  fi
  git submodule add -f "$url" ".packs/$name"
  sparse_pack "$name"
  if [ ! -d "$(pack_dir "$name")" ]; then
    local sub; sub=$(pack_subpath "$name")
    unmount_half "$name"
    die "pack '$name': $sub is not in $url — the registry's (or the manifest's) path is wrong; the mount was taken back out"
  fi
  manifest_add "$name" "${2:-}"
  [ "$DEFER_SYNC" = 1 ] || cmd_sync
  echo "mounted. Review, then: git add .gitmodules .packs.yaml .packs/$name && git commit (the skills/ and .claude/ links are generated and excluded from git)"
}

cmd_remove() {
  local name="${1:?usage: packs.sh remove <name>}"
  valid_name "$name"
  not_a_plugin "$name"
  [ -d ".packs/$name" ] || die "pack '$name' is not mounted"
  if [ ! -L ".packs/$name" ] && [ -e ".packs/$name/.git" ] && [ -n "$(git -C ".packs/$name" status --porcelain 2>/dev/null)" ]; then
    die "pack '$name' has local changes that deinit -f would discard — refusing (git -C .packs/$name status)"
  fi
  # In a linked worktree .git is a file and the module gitdir lives under the worktree's own
  # gitdir; a leftover one would be reused, stale, by the next `add -f` of the same name.
  local gd; gd=$(git rev-parse --git-path "modules/$(submodule_key "$name" || true)")
  [ -n "$(submodule_key "$name")" ] || gd=$(git rev-parse --git-path "modules/.packs/$name")
  git submodule deinit -f ".packs/$name"
  git rm -f ".packs/$name"
  rm -rf "$gd"
  manifest_remove "$name"
  [ "$DEFER_SYNC" = 1 ] || cmd_sync
}

# Reconcile mounted packs to the manifest — idempotent, headless-safe.
DEFER_SYNC=0   # apply sets it: one union rebuild at the end, not one per pack
cmd_apply() {
  local name p failed=""
  DEFER_SYNC=1
  check_paths
  warn_deprecated
  refuse_found "$(plugin_drift apply)"   # a plugin pack is never mounted back, an unknown mode never guessed
  # A fresh clone or worktree carries the pins as empty dirs, and a pull or branch switch
  # can move a gitlink under an initialised mount: check both out at their recorded pin.
  for name in $(manifest_names); do
    p=".packs/$name"
    if ! is_plugin "$name" && [ -d "$p" ] && [ ! -L "$p" ] && [ -z "$(ls -A "$p")" ]; then
      echo "apply: initialising '$name'"
      git submodule update --init -- "$p" || true
      sparse_pack "$name"
    fi
  done
  for p in $(pin_drift | sed -n 's/^stale mount: \([^ ]*\) .*/\1/p'); do
    echo "apply: checking out the recorded pin of '$p'"
    git submodule update --init -- "$p" || true
  done
  refuse_dangling dangling_packs
  refuse_dangling pin_drift
  for name in $(manifest_names); do
    if [ ! -d ".packs/$name" ] && [ "$(install_mode "$name")" = submodule ]; then
      echo "apply: mounting '$name'"
      # Subshell so one pack's die doesn't stop the rest. set -e is off inside a
      # subshell under ||, so judge by the mount itself, not the exit status.
      ( cmd_add "$name" "$(manifest_field "$name" repo)" ) || true
      if [ ! -d ".packs/$name" ]; then echo "apply: '$name' failed — continuing" >&2; failed="$failed $name"; fi
    fi
  done
  for p in .packs/*/; do
    [ -d "$p" ] || continue
    name=$(basename "$p")
    if ! manifest_names | grep -qx "$name"; then
      echo "apply: unmounting '$name' (not in $MANIFEST)"
      cmd_remove "$name"
    fi
  done
  cmd_sync
  [ -z "$failed" ] || die "apply: not mounted:$failed — state does NOT match $MANIFEST"
  echo "apply: state matches $MANIFEST"
}

cmd_update() {
  local paths
  if [ -n "${1:-}" ]; then valid_name "$1"; paths=".packs/$1"
  else paths=$(git config -f .gitmodules --get-regexp path | awk '$2 ~ /^\.packs\// {print $2}'); fi
  # shellcheck disable=SC2086  # paths are .packs/<name>, no whitespace
  git submodule update --remote -- $paths
  # Stage the moved gitlinks: apply checks mounts out at the recorded pin, and would
  # otherwise put an unstaged bump straight back.
  # shellcheck disable=SC2086
  git add -- $paths
  cmd_sync
  echo "pin(s) moved and staged. Review, then commit the bump."
}

cmd_list() {
  local p pname pin n plugins
  plugins=$(plugin_list); [ -z "$plugins" ] || echo "$plugins"
  for p in .packs/*/; do
    [ -d "$p" ] || { echo "no packs mounted${plugins:+ as submodules}"; return; }
    pname=$(basename "$p")
    pin=$(git -C "$p" rev-parse --short HEAD 2>/dev/null || echo "?")
    n=$(pack_skill_dirs "$(pack_dir "$pname")" | wc -l | tr -d ' ')
    echo "$pname  @$pin  ($n skills)"
  done
}

# `git mv` of a submodule updates the module's shared config but not its per-worktree one, which a
# sparse checkout creates: its core.worktree would still name the old directory.
repoint_worktree() { # <new name>
  local gd wt
  gd=$(sed -n 's/^gitdir: //p' ".packs/$1/.git" 2>/dev/null) || return 0
  [ -n "$gd" ] && [ -f ".packs/$1/$gd/config.worktree" ] || return 0
  wt=$(git config --file ".packs/$1/$gd/config.worktree" --get core.worktree 2>/dev/null) || return 0
  git config --file ".packs/$1/$gd/config.worktree" core.worktree "${wt%/*}/$1"
}

# Rewrite an instance keyed by renamed packs to the registry's keys: the manifest entry (config
# block and all) under its new key, and a mounted submodule moved to .packs/<new>. Nothing is
# guessed: a pack whose old and new keys both appear, or whose new mount path is taken, stops it.
cmd_migrate() {
  [ -f "$MANIFEST" ] || die "migrate: there is no $MANIFEST here"
  local old new moved=0 src reg resourced=""
  for old in $(manifest_names); do
    new=$(registry_name "$old"); [ "$new" != "$old" ] || continue
    manifest_names | grep -qx -- "$new" && die "migrate: both '$old' and '$new' are in $MANIFEST — merge the two entries by hand, then re-run"
    # The mount first, the manifest last: a failed move leaves the instance as it was, and a
    # re-run after a move that did happen finds only the manifest left to rewrite.
    if [ -e ".packs/$old" ] || [ -L ".packs/$old" ]; then
      { [ -e ".packs/$new" ] || [ -L ".packs/$new" ]; } && die "migrate: both .packs/$old and .packs/$new exist — remove one, then re-run"
      src=$(mount_url "$old"); reg=$(registry_field "$new" repo)
      if [ -n "$(git ls-files -s -- ".packs/$old" 2>/dev/null)" ]; then
        git mv ".packs/$old" ".packs/$new" || die "migrate: could not move .packs/$old to .packs/$new — nothing was changed; fix what git reports and re-run"
        repoint_worktree "$new"
      else
        mv ".packs/$old" ".packs/$new" || die "migrate: could not move .packs/$old — nothing was changed"
      fi
      if [ -n "$src" ] && [ -n "$reg" ] && [ "$(norm_url "$src")" != "$(norm_url "$reg")" ]; then
        resourced="$resourced $new"
      fi
    fi
    awk -v o="$old" -v n="$new" '$0 == "  " o ":" { print "  " n ":"; next } { print }' "$MANIFEST" > "$MANIFEST.tmp" && mv "$MANIFEST.tmp" "$MANIFEST"
    echo "migrate: $old -> $new"
    moved=$((moved + 1))
  done
  if [ "$moved" = 0 ]; then echo "migrate: nothing to do — every key in $MANIFEST is current"; return; fi
  cmd_sync
  for new in $resourced; do
    echo "note: $new is still mounted from $(mount_url "$new"), not from the registry's repository ($(registry_field "$new" repo));" \
         "it keeps working as the whole pack. To move it: scripts/packs.sh remove $new, then scripts/packs.sh add $new (re-add its entry's config)" >&2
  done
  echo "migrated $moved pack(s). Review, then: git add -A .gitmodules .packs .packs.yaml && git commit (the skills/ and .claude/ links are generated and excluded from git)"
}

case "${1:-}" in
  add) shift; cmd_add "$@" ;;
  remove) shift; cmd_remove "$@" ;;
  update) shift; cmd_update "${1:-}" ;;
  list) cmd_list ;;
  sync) cmd_sync ;;
  apply) cmd_apply ;;
  check) cmd_check ;;
  config) shift; cmd_config "$@" ;;
  migrate) cmd_migrate ;;
  *) echo "usage: $0 add <name> [repo-url] | remove <name> | update [name] | list | sync | apply | check | config <pack> [key] | migrate" >&2; exit 1 ;;
esac
