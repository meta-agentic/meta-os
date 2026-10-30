#!/usr/bin/env bash
#
# SessionStart — tell the operator, in one line, when the framework in this instance needs
# their attention. Check only: it never merges, never fetches into the working tree, never
# changes a skill. An unattended upgrade would merge code mid-session, change skills an open
# session is using, bypass review, and execute whatever `upstream` holds (systems/distribution.md).
#
# Prints nothing when there is nothing to do. When there is, it prints one JSON object (the
# harness shows `systemMessage` to the operator and adds `additionalContext` to the session):
#
#   * the framework is N commits behind            -> scripts/upgrade.sh --check
#   * the framework moved since the last fetch      -> scripts/upgrade.sh --check
#   * this repository predates the one-repository layout -> the adoption command, dry run
#   * framework paths edited in this instance       -> scripts/upgrade.sh --check
#   * the template changed since instantiation      -> scripts/upgrade.sh --check
#
# What it may write: one small stamp file under the git directory (`meta-os-status`), nothing
# else. No fetch (a fetch moves refs), no `git status` (it refreshes the index): the freshness
# of the remote is one `git ls-remote`, bounded, at most once a day; everything else is read
# from what is already in the repository.
#
# Silent and fast offline: a failed or slow `ls-remote` is given up after the bound, and the
# attempt is stamped, so a machine without a network pays the bound once a day, not every session.
#
# Environment
# -----------
#   METAOS_STATUS_OFF       set to 1 to disable entirely
#   METAOS_STATUS_TTL       seconds between remote checks              (default: 86400)
#   METAOS_STATUS_TIMEOUT   seconds the remote check may take           (default: 3)
#   METAOS_FRAMEWORK_REMOTE the framework remote                        (default: upstream)
#   METAOS_FRAMEWORK_BRANCH the framework branch                        (default: main)
#
# Enabling it: instances bootstrapped from the template have it wired in .claude/settings.json;
# any other instance wires it once (hooks/_index.md, "Framework status"). Staged, never switched
# on by the framework itself: enabling a hook is an explicit decision ([[systems/packs]]).
set -u
export GIT_OPTIONAL_LOCKS=0 GIT_TERMINAL_PROMPT=0
export GIT_SSH_COMMAND="${GIT_SSH_COMMAND:-ssh -o BatchMode=yes -o ConnectTimeout=3}"

[ "${METAOS_STATUS_OFF:-0}" = 1 ] && exit 0
remote="${METAOS_FRAMEWORK_REMOTE:-upstream}" branch="${METAOS_FRAMEWORK_BRANCH:-main}"
ttl="${METAOS_STATUS_TTL:-86400}" bound="${METAOS_STATUS_TIMEOUT:-3}"
case "$ttl$bound" in *[!0-9]*) exit 0 ;; esac

root=$(git -C "${CLAUDE_PROJECT_DIR:-.}" rev-parse --show-toplevel 2>/dev/null) || exit 0
cd "$root" || exit 0
git remote 2>/dev/null | grep -qx "$remote" || exit 0       # no framework remote: not an instance (or the framework itself)
target="$remote/$branch"
stamp=$(git rev-parse --git-path meta-os-status 2>/dev/null) || exit 0

now=$(date +%s)
checked=0 seen=""
if [ -f "$stamp" ]; then
  checked=$(sed -n 's/^checked=//p' "$stamp" | head -1); seen=$(sed -n 's/^remote=//p' "$stamp" | head -1)
  case "$checked" in ''|*[!0-9]*) checked=0 ;; esac
fi

# --- the one remote look: bounded, once per ttl, never fatal ---------------------------------
bounded() { # <seconds> <outfile> cmd... — kill the command when the time is up
  local t=$1 out=$2; shift 2
  "$@" >"$out" 2>/dev/null & local p=$!
  ( sleep "$t"; kill -9 "$p" 2>/dev/null ) >/dev/null 2>&1 & local w=$!
  wait "$p" 2>/dev/null; local rc=$?
  kill "$w" 2>/dev/null; wait "$w" 2>/dev/null
  return $rc
}
if [ $((now - checked)) -ge "$ttl" ]; then
  tmp=$(mktemp "${TMPDIR:-/tmp}/metaos-status.XXXXXX") || exit 0
  if bounded "$bound" "$tmp" git ls-remote "$remote" "refs/heads/$branch"; then
    sha=$(awk 'NR==1 {print $1}' "$tmp"); [ -z "$sha" ] || seen=$sha
  fi
  rm -f "$tmp"
  printf 'checked=%s\nremote=%s\n' "$now" "$seen" >"$stamp" 2>/dev/null || true   # the only write
fi

# --- what the repository itself says ---------------------------------------------------------------
items=()
have_ref=0; git rev-parse -q --verify "$target^{commit}" >/dev/null 2>&1 && have_ref=1
base=""; [ "$have_ref" = 0 ] || base=$(git merge-base HEAD "$target" 2>/dev/null || true)
looks_like_instance() { local f; for f in .packs.yaml meta-os.config.json projects memory vaults automations; do [ -e "$f" ] && return 0; done; return 1; }

if [ ! -f .claude/CLAUDE.md ] || { [ "$have_ref" = 1 ] && [ -z "$base" ]; }; then
  # A repository with its own history (or a contract at the root) that never took the framework's.
  if looks_like_instance; then
    items+=("this repository predates the one-repository layout: git fetch $remote && git show $target:scripts/upgrade.sh | bash -s -- --adopt --dry-run")
  fi
else
  if [ "$have_ref" = 1 ]; then
    behind=$(git rev-list --count "HEAD..$target" 2>/dev/null || echo 0)
    if [ "${behind:-0}" -gt 0 ]; then
      items+=("the framework is $behind commit(s) behind: scripts/upgrade.sh --check")
    elif [ -n "$seen" ] && [ "$seen" != "$(git rev-parse "$target")" ] && ! git merge-base --is-ancestor "$seen" HEAD 2>/dev/null; then
      items+=("the framework moved since your last fetch: scripts/upgrade.sh --check")
    fi
    # framework paths edited here: what the framework tracked at the merge base, changed since
    if [ -n "$base" ]; then
      edited=$(git diff --name-only --diff-filter=MDT "$base" HEAD -- 2>/dev/null \
               | grep -xF -f <(git ls-tree -r --name-only "$base") | grep -c . || true)
      [ "${edited:-0}" -eq 0 ] || items+=("$edited framework path(s) edited in this instance: scripts/upgrade.sh --check")
    fi
    # template drift since instantiation, unless acknowledged (--ack-template moves the recorded ref)
    tref=$(sed -n 's/.*"template": *"\([0-9a-f]\{7,40\}\)".*/\1/p' meta-os.config.json 2>/dev/null | head -1)
    git rev-parse -q --verify "${tref:-x}^{commit}" >/dev/null 2>&1 || tref=$base
    if [ -n "$tref" ] && ! git diff --quiet "$tref" "$target" -- instance-template/ 2>/dev/null; then
      items+=("instance-template/ changed since it was instantiated: scripts/upgrade.sh --check")
    fi
  elif [ -n "$seen" ]; then
    items+=("the framework has not been fetched here yet: scripts/upgrade.sh --check")
  fi
fi

[ "${#items[@]}" -gt 0 ] || exit 0
msg="meta-os: "; sep=""
for i in "${items[@]}"; do msg="$msg$sep$i"; sep="; "; done
esc=${msg//\\/\\\\}; esc=${esc//\"/\\\"}
printf '{"systemMessage":"%s","hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' "$esc" "$esc"
exit 0
