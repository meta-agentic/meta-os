#!/usr/bin/env bash
#
# Observability sink for harness hooks — counters, gauges and an event log.
#
# Hooks are the one part of the OS that runs with nobody watching. They fire
# inside someone else's tool call, their output is consumed by a machine, and a
# hook that quietly stops working looks exactly like a hook with nothing to say.
# This is the sink that makes the difference visible.
#
# TWO RULES, BOTH ABSOLUTE
# ------------------------
#   1. NEVER WRITE TO STDOUT. A PreToolUse hook's stdout is parsed as JSON by
#      the harness. One stray byte from here corrupts its caller's contract and
#      turns an observability tool into an outage. Diagnostics go to stderr,
#      data goes to files.
#   2. NEVER FAIL THE CALLER. This exits 0 unconditionally. A telemetry sink
#      that can break the thing it measures is worse than no telemetry: it adds
#      a failure mode to a path that previously had none.
#
# Usage
# -----
#   error-handler.sh --hook NAME --event KIND [options]
#
#     --hook NAME        originating hook (required)
#     --event KIND       error | run | <anything>  (required)
#     --code N           exit status, for error events
#     --line N           line number in the caller
#     --cmd STR          the command that failed
#     --detail STR       free-text context
#     --counter NAME[=N] increment a counter by N (default 1); repeatable
#     --gauge NAME=VALUE record a last-write-wins value; repeatable
#
# Storage  ($METAOS_OBS_DIR, default $XDG_STATE_HOME/meta-os or ~/.local/state/meta-os)
# -------
#   events.ndjson   one JSON object per event, rotated at METAOS_OBS_MAX_BYTES
#   counters.tsv    name <TAB> value          monotonic, incremented under lock
#   gauges.tsv      name <TAB> value <TAB> ts last-write-wins
#
# Counter and gauge names are namespaced by the calling hook, so two hooks
# cannot silently share a series and average each other's behaviour away.
#
# Env: METAOS_OBS_OFF=1 disables; METAOS_OBS_DEBUG=1 reports failures on stderr.
#
# NO pipefail here, deliberately. This script's normal path is full of reads
# that legitimately find nothing — an absent counter file, a key not yet
# present — and under pipefail each of those becomes a "failure" that the ERR
# net below would swallow, silently stopping the handler halfway through its
# own job. That is not hypothetical: it is what the first version did, and the
# symptom was an events log that worked while no counter was ever written.
set -u

# Rule 2, enforced structurally rather than by discipline: whatever happens
# below, the caller sees success. This is a NET, not a control-flow device —
# every expected non-zero below is guarded explicitly so this never fires on a
# healthy run.
trap 'exit 0' ERR
[ "${METAOS_OBS_OFF:-0}" = "1" ] && exit 0

OBS="${METAOS_OBS_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/meta-os}"
MAX_BYTES="${METAOS_OBS_MAX_BYTES:-1048576}"

dbg() { [ "${METAOS_OBS_DEBUG:-0}" = "1" ] && printf 'error-handler: %s\n' "$*" >&2; return 0; }

hook="" ; event="" ; code="" ; line="" ; cmd="" ; detail=""
counters=() ; gauges=()
while [ $# -gt 0 ]; do
  case "$1" in
    --hook)    hook="${2:-}"   ; shift 2 || break ;;
    --event)   event="${2:-}"  ; shift 2 || break ;;
    --code)    code="${2:-}"   ; shift 2 || break ;;
    --line)    line="${2:-}"   ; shift 2 || break ;;
    --cmd)     cmd="${2:-}"    ; shift 2 || break ;;
    --detail)  detail="${2:-}" ; shift 2 || break ;;
    --counter) counters+=("${2:-}") ; shift 2 || break ;;
    --gauge)   gauges+=("${2:-}")   ; shift 2 || break ;;
    *) dbg "ignoring unknown argument: $1" ; shift ;;
  esac
done

[ -z "$hook" ] && { dbg "no --hook; nothing recorded" ; exit 0; }
[ -z "$event" ] && event="unknown"

# A series name must not be able to inject a field separator or a newline into
# the TSV, so anything outside the allowed set becomes an underscore.
sane() { printf '%s' "${1:-}" | tr -c 'A-Za-z0-9_.:-' '_' ; }
hook_ns=$(sane "$hook")

mkdir -p "$OBS" 2>/dev/null || { dbg "cannot create $OBS" ; exit 0; }
[ -w "$OBS" ] || { dbg "$OBS not writable" ; exit 0; }

# Serialise read-modify-write on the counter file. Hooks run in parallel — this
# one is invoked from inside a parallel fetch loop — so an unlocked increment
# loses counts precisely when the system is busiest, which is when the numbers
# matter. flock when available; a bounded mkdir spin otherwise (macOS ships no
# flock), and if the lock cannot be taken we skip the write rather than racing.
_lock_fd=""
take_lock() {
  if command -v flock >/dev/null 2>&1; then
    exec {_lock_fd}>"$OBS/.lock" 2>/dev/null || return 1
    flock -w 2 "$_lock_fd" 2>/dev/null || return 1
    return 0
  fi
  local i=0
  while ! mkdir "$OBS/.lock.d" 2>/dev/null; do
    i=$((i+1)); [ "$i" -gt 40 ] && return 1
    sleep 0.05 2>/dev/null || sleep 1
  done
  return 0
}
drop_lock() {
  if [ -n "$_lock_fd" ]; then exec {_lock_fd}>&- 2>/dev/null || true
  else rmdir "$OBS/.lock.d" 2>/dev/null || true; fi
}

now_iso=$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "")
now_epoch=$(date +%s 2>/dev/null || echo 0)

# ---- events.ndjson -----------------------------------------------------------
# Rotate BEFORE appending, so the cap is a real ceiling rather than a threshold
# the file sits above until the next call.
if [ -f "$OBS/events.ndjson" ]; then
  sz=$(wc -c < "$OBS/events.ndjson" 2>/dev/null | tr -d ' ' || echo 0)
  [ -z "$sz" ] && sz=0
  [ "${sz:-0}" -ge "$MAX_BYTES" ] && mv -f "$OBS/events.ndjson" "$OBS/events.ndjson.1" 2>/dev/null
fi

if command -v jq >/dev/null 2>&1; then
  jq -cn --arg ts "$now_iso" --arg hook "$hook" --arg event "$event" \
        --arg code "$code" --arg line "$line" --arg cmd "$cmd" --arg detail "$detail" \
        --arg gauges "${gauges[*]:-}" \
        '{ts:$ts, hook:$hook, event:$event}
         + (if $code   != "" then {code:  ($code|tonumber? // $code)} else {} end)
         + (if $line   != "" then {line:  ($line|tonumber? // $line)} else {} end)
         + (if $cmd    != "" then {cmd:    $cmd}    else {} end)
         + (if $detail != "" then {detail: $detail} else {} end)
         + (if $gauges != "" then {gauges: $gauges} else {} end)' \
     >> "$OBS/events.ndjson" 2>/dev/null || dbg "event append failed"
else
  # No jq: record something rather than nothing, escaping the two characters
  # that would otherwise break the line or the string.
  esc() { printf '%s' "${1:-}" | tr -d '\n' | sed 's/\\/\\\\/g; s/"/\\"/g'; }
  printf '{"ts":"%s","hook":"%s","event":"%s","code":"%s","line":"%s","cmd":"%s","detail":"%s"}\n' \
    "$now_iso" "$(esc "$hook")" "$(esc "$event")" "$(esc "$code")" \
    "$(esc "$line")" "$(esc "$cmd")" "$(esc "$detail")" \
    >> "$OBS/events.ndjson" 2>/dev/null || dbg "event append failed"
fi

# ---- counters.tsv / gauges.tsv ----------------------------------------------
if [ "${#counters[@]}" -gt 0 ] || [ "${#gauges[@]}" -gt 0 ]; then
  if take_lock; then
    for c in "${counters[@]:-}"; do
      [ -z "$c" ] && continue
      name="${c%%=*}"; inc="${c#*=}"; [ "$inc" = "$c" ] && inc=1
      case "$inc" in ''|*[!0-9-]*) inc=1 ;; esac
      key="${hook_ns}.$(sane "$name")"
      cur=$(awk -F'\t' -v k="$key" '$1==k{print $2}' "$OBS/counters.tsv" 2>/dev/null | tail -1 || true)
      case "${cur:-}" in ''|*[!0-9-]*) cur=0 ;; esac
      new=$((cur + inc))
      if [ -f "$OBS/counters.tsv" ]; then
        awk -F'\t' -v k="$key" '$1!=k' "$OBS/counters.tsv" > "$OBS/.counters.$$" 2>/dev/null || : > "$OBS/.counters.$$"
      else : > "$OBS/.counters.$$"; fi
      printf '%s\t%s\n' "$key" "$new" >> "$OBS/.counters.$$"
      mv -f "$OBS/.counters.$$" "$OBS/counters.tsv" 2>/dev/null || rm -f "$OBS/.counters.$$"
    done
    for g in "${gauges[@]:-}"; do
      [ -z "$g" ] && continue
      case "$g" in *=*) ;; *) dbg "gauge without a value: $g"; continue ;; esac
      key="${hook_ns}.$(sane "${g%%=*}")"; val="${g#*=}"
      if [ -f "$OBS/gauges.tsv" ]; then
        awk -F'\t' -v k="$key" '$1!=k' "$OBS/gauges.tsv" > "$OBS/.gauges.$$" 2>/dev/null || : > "$OBS/.gauges.$$"
      else : > "$OBS/.gauges.$$"; fi
      printf '%s\t%s\t%s\n' "$key" "$(sane "$val")" "$now_epoch" >> "$OBS/.gauges.$$"
      mv -f "$OBS/.gauges.$$" "$OBS/gauges.tsv" 2>/dev/null || rm -f "$OBS/.gauges.$$"
    done
    drop_lock
  else
    dbg "lock unavailable; counters/gauges skipped this call"
  fi
fi

exit 0
