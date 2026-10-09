# shellcheck shell=bash
# Packs installed as Claude Code plugins — sourced by scripts/packs.sh, never run on its own.
# Contract: systems/packs.md ("A pack installed as a plugin"). A .packs.yaml entry with
# `install: plugin` has no .packs/ submodule and no links in skills/; `config` reads its
# pack.yaml where Claude Code installed the plugin (scripts/plugin_root.py). `install:
# submodule` is the default; any other value, an empty one included, is refused — never read
# as a mount. Uses packs.sh's die, manifest_field, manifest_names, registry_field, $MANIFEST.

install_mode() { # <name> → submodule | plugin | the unrecognised value, quoted ('' when empty)
  [ -f "$MANIFEST" ] || { echo submodule; return; }
  awk -v p="$1" '
    $0 ~ "^  "p":" { inpack=1; next }
    inpack && /^  [a-zA-Z0-9_-]+:/ { inpack=0 }
    inpack && /^    install:/ {                     # entry level only: config keys sit deeper
      v=substr($0, index($0,":")+1); sub(/[ \t]+#.*$/,"",v); gsub(/^[ \t]+|[ \t\r]+$/,"",v)
      gsub(/["\047]/,"",v); found=1; exit }
    END { if (!found) print "submodule"; else if (v=="plugin" || v=="submodule") print v
          else print "\047" v "\047" }
  ' "$MANIFEST"
}
is_plugin() { [ "$(install_mode "$1")" = plugin ]; }
plugin_id() { local id; id=$(manifest_field "$1" plugin); echo "${id:-$(registry_field "$1" plugin)}"; }

# <check|apply> — the findings both refuse on: an unknown mode, a plugin entry naming no
# plugin, one whose submodule is still recorded (a gitlink: any clone checks it out again).
# An untracked leftover — what `git pull` leaves behind when a commit removed the submodule —
# is not refused: sync links nothing from a plugin pack. `check` warns about it, with the remedy.
plugin_drift() {
  local name m
  for name in $(manifest_names); do
    m=$(install_mode "$name")
    if [ "$m" = plugin ]; then
      [ -n "$(plugin_id "$name")" ] || echo "installed as a plugin but names none: $name (set plugin: <plugin>@<marketplace>)"
      if [ -n "$(git ls-files -s -- ".packs/$name" 2>/dev/null)" ]; then
        echo "installed as a plugin and also mounted: $name — its skills are discovered twice (git rm .packs/$name)"
      elif [ "$1" = check ] && [ -e ".packs/$name" ]; then
        echo "warn: .packs/$name is a leftover of plugin pack $name (untracked, its submodule removed);" \
             "sync links nothing from it — delete it: rm -rf .packs/$name $(git rev-parse --git-path "modules/.packs/$name")" >&2
      fi
    elif [ "$m" != submodule ]; then echo "unknown install mode for $name: $m (plugin, or submodule — the default)"; fi
  done
}

# <pack> → the installed plugin's pack.yaml on stdout; when it cannot be found, one warning
# naming the cause and nothing on stdout — never a failure, so a skill's config still resolves.
plugin_pack_yaml() {
  local id why root rc=0 helper
  id=$(plugin_id "$1"); helper="$(dirname "${BASH_SOURCE[0]}")/plugin_root.py"
  if [ -z "$id" ]; then why="names no plugin"
  elif ! command -v python3 >/dev/null; then why="python3 not found"
  else
    root=$(python3 "$helper" "$id" 2>/dev/null) || rc=$?
    if [ "$rc" = 0 ] && [ -f "$root/pack.yaml" ]; then echo "$root/pack.yaml"; return; fi
    why=$(python3 "$helper" "$id" 2>&1 >/dev/null | tail -n 1)
    [ "$rc" = 0 ] || why="scripts/plugin_root.py failed (exit $rc): ${why:-no message}"
  fi
  echo "warn: plugin '${id:-?}' of pack '$1': ${why:-not installed here} — instance values only, no defaults or validation" >&2
}

plugin_list() { # one line per plugin pack, for `list`
  local name
  for name in $(manifest_names); do
    if is_plugin "$name"; then echo "$name  plugin $(plugin_id "$name")  (installed by Claude Code, not mounted)"; fi
  done
}
not_a_plugin() { # <name> — `remove` would drop the entry, and with it the pack's config
  is_plugin "$1" || return 0
  die "pack '$1' is installed as a plugin: uninstall it with /plugin uninstall $(plugin_id "$1")," \
      "then drop its entry from $MANIFEST (a recorded mount: git rm .packs/$1)"
}
