#!/usr/bin/env bash
#
# PreToolUse(Bash) — fetch every tracked repo before any commit, and say which
# checkouts are behind their default branch.
#
# Why this exists
# ---------------
# An agent working across several repos accumulates stale checkouts without
# noticing. Committing into one is usually harmless. DERIVING A FIGURE from one
# is not: a count, a total or a status roll-up computed over a tree that is
# missing commits is arithmetically correct and factually wrong, and it looks
# exactly like a correct one. Nothing downstream can catch it, because the
# reasoning over the visible data is sound — the data was the problem.
#
# The mitigation cannot be analytical: no amount of care while reading the wrong
# tree produces the right answer. It has to be mechanical. Fetch before you
# compute, and never commit into a repo whose state you have not refreshed.
#
# Behaviour
# ---------
#   * Runs on every Bash call, exits immediately unless the command commits.
#   * Fetches the default branch of every git repo directly under the repos
#     root, in parallel.
#   * Reports only the repos that are behind. Silence means everything is
#     current.
#   * NEVER blocks. It reports; the decision stays with the human and the
#     agent. Being behind is often fine — hearing about it late is not.
#
# Environment
# -----------
#   METAOS_REPOS_ROOT   directory holding the repo checkouts   (default: $HOME)
#   METAOS_PREFETCH_TTL  seconds before a repo is re-fetched    (default: 90)
#   METAOS_PREFETCH_OFF  set to 1 to disable entirely
#
# Install: see hooks/_index.md. Staged, never auto-wired — enabling a hook is
# an explicit user decision, always ([[systems/packs]]).
#
set -uo pipefail

[ "${METAOS_PREFETCH_OFF:-0}" = "1" ] && exit 0

payload=$(cat)
command -v jq >/dev/null 2>&1 || exit 0
cmd=$(printf '%s' "$payload" | jq -r '.tool_input.command // ""' 2>/dev/null) || exit 0

# Only commands that actually create a commit. `git` must sit in COMMAND
# POSITION — start of a line, or after ; && || | & ( { — so that prose merely
# containing the words does not trigger a fetch. `echo git commit …` and a
# commit message body quoting the phrase are both common enough to matter.
# An optional wrapper word (sudo, env, time, nice, xargs) is allowed through.
# Catches `git commit`, `git -C <dir> commit`, `git add x && git commit …`.
#
# Deliberately biased toward firing: a false positive costs one fetch, a false
# negative costs a commit made against a stale tree, which is the whole point.
printf '%s' "$cmd" | grep -Eq \
  '(^|[;&|(){}]|&&|\|\|)[[:space:]]*((sudo|env|time|nice|xargs)[[:space:]]+)?git([[:space:]]+-[^[:space:]]+([[:space:]]+[^[:space:]]+)?)*[[:space:]]+commit([[:space:]]|$)' \
  || exit 0

# Resolve the repos root by probing, not by assuming. $HOME is NOT reliable:
# containers and CI images routinely run as a user whose $HOME is nowhere near
# the checkouts, and then a $HOME default scans an empty directory and the hook
# reports nothing — indistinguishable from "everything is current", which is
# exactly the failure this hook exists to prevent. Probe, and require evidence
# (an actual */.git) before accepting a candidate.
has_repos() { [ -n "${1:-}" ] && [ -d "$1" ] && compgen -G "$1/*/.git" > /dev/null 2>&1; }

ROOT=""
payload_cwd=$(printf '%s' "$payload" | jq -r '.cwd // ""' 2>/dev/null)
for cand in \
  "${METAOS_REPOS_ROOT:-}" \
  "${CLAUDE_PROJECT_DIR:+$(dirname "$CLAUDE_PROJECT_DIR")}" \
  "${CLAUDE_PROJECT_DIR:-}" \
  "${payload_cwd:+$(dirname "$payload_cwd")}" \
  "$(dirname "$PWD")" \
  "$PWD" \
  "$HOME"
do
  if has_repos "$cand"; then ROOT="$cand"; break; fi
done
[ -z "$ROOT" ] && exit 0

TTL="${METAOS_PREFETCH_TTL:-90}"
CACHE="${TMPDIR:-/tmp}/.claude-prefetch"
mkdir -p "$CACHE" 2>/dev/null || true
now=$(date +%s)

# Resolve the remote's default branch. origin/HEAD is authoritative when the
# clone has it; otherwise probe the conventional names rather than guessing one.
default_branch() {
  local repo=$1 ref
  ref=$(git -C "$repo" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null)
  if [ -n "$ref" ]; then printf '%s' "${ref#origin/}"; return; fi
  for c in main master trunk; do
    git -C "$repo" show-ref --verify --quiet "refs/remotes/origin/$c" && { printf '%s' "$c"; return; }
  done
  printf ''
}

fetch_one() {
  local repo=$1 name def stamp last
  name=$(basename "$repo")
  def=$(default_branch "$repo")
  [ -z "$def" ] && return 0

  # Rate-limit per repo: a run of commits in one turn should not re-fetch each
  # time. The refs are already current from the first fetch.
  stamp="$CACHE/$name"
  last=$(cat "$stamp" 2>/dev/null || echo 0)
  if [ $((now - last)) -ge "$TTL" ]; then
    if git -C "$repo" fetch --quiet origin "$def" 2>/dev/null; then
      printf '%s' "$now" > "$stamp" 2>/dev/null || true
    else
      printf '%s\tFETCH-FAILED\t%s\n' "$name" "$def"
      return 0
    fi
  fi

  local behind branch
  branch=$(git -C "$repo" rev-parse --abbrev-ref HEAD 2>/dev/null) || return 0
  [ "$branch" = "HEAD" ] && return 0   # detached; nothing meaningful to compare
  behind=$(git -C "$repo" rev-list --count "HEAD..origin/$def" 2>/dev/null) || return 0
  [ "${behind:-0}" -gt 0 ] && printf '%s\t%s\t%s\t%s\n' "$name" "$behind" "$branch" "$def"
  return 0
}

results=""
pids=()
tmp=$(mktemp -d "${TMPDIR:-/tmp}/prefetch.XXXXXX") || exit 0
for gitdir in "$ROOT"/*/.git; do
  [ -e "$gitdir" ] || continue
  repo=${gitdir%/.git}
  ( fetch_one "$repo" > "$tmp/$(basename "$repo")" 2>/dev/null ) &
  pids+=($!)
done
for p in "${pids[@]:-}"; do [ -n "$p" ] && wait "$p" 2>/dev/null; done
results=$(cat "$tmp"/* 2>/dev/null)
rm -rf "$tmp" 2>/dev/null || true

[ -z "$results" ] && exit 0

lines=""
failed=""
while IFS=$'\t' read -r name a b c; do
  [ -z "$name" ] && continue
  if [ "$a" = "FETCH-FAILED" ]; then
    failed="${failed}${failed:+, }${name}"
  else
    lines="${lines}  - ${name}: ${b} is ${a} commit(s) behind origin/${c}"$'\n'
  fi
done <<< "$results"

msg=""
[ -n "$lines" ] && msg="Stale checkouts (fetched just now):"$'\n'"$lines"
[ -n "$failed" ] && msg="${msg}${msg:+
}Could not fetch: ${failed} (offline or no access — treat those as unknown, not current)."

[ -z "$msg" ] && exit 0

ctx="$msg
Committing into a repo that is behind is often fine. Deriving a NUMBER from one
is not: a sum over a stale tree looks identical to a correct one. If this commit
records a count, a total, a roll-up or any other derived figure, rebase or
restart the branch onto the fetched ref first and recompute."

jq -n --arg m "$msg" --arg c "$ctx" \
  '{systemMessage: $m, hookSpecificOutput: {hookEventName: "PreToolUse", additionalContext: $c}}'
exit 0
