"""The public-safety scan: no instance identifier in a tracked file of this public repository.

Split out of `validate_framework.py` (check 5). This class NEVER enters the baseline (see
`framework_findings.BASELINEABLE`) and NEVER downgrades to a warning.
"""
from __future__ import annotations

import re
from pathlib import Path

from framework_findings import BASELINE, ROOT, Finding
from framework_scope import tracked_files

# ---------------------------------------------------------------------------
# Public-safety scan. This repo is public; a leaked instance identifier is not
# retractable once pushed, so this class NEVER enters the baseline (see
# BASELINEABLE) and NEVER downgrades to a warning.
# ---------------------------------------------------------------------------
# `<PREFIX>-<number>` at a token boundary — the shape of an instance tracker key.
TRACKER_KEY_RE = re.compile(r"(?<![A-Za-z0-9])([A-Z]{2,5}-[0-9]+)")
# An absolute macOS home path — a machine path, i.e. instance data.
ABS_HOME_RE = re.compile(r"/Users/[A-Za-z0-9._-]+")

# Narrow allow-list for the tracker-key pattern: EXACT tokens only, never
# prefixes and never regex, so widening it is always a visible one-line diff.
# Add a token here only when it is a published standard/encoding identifier that
# merely happens to look like a tracker key. Never add a real key: the correct
# fix for a real key is to remove it from the file.
PUBLIC_SAFETY_ALLOWED_TOKENS = frozenset({
    "UTF-8", "UTF-16", "UTF-32",     # character encodings
    "ISO-8601", "ISO-8859",          # date/charset standards
    "RFC-3339", "RFC-7231",          # IETF documents
    "SHA-1", "SHA-256", "SHA-512",   # digest algorithms
    "AES-128", "AES-256",            # ciphers
    "MIT-0",                         # SPDX licence identifier
})
# File suffixes worth scanning as text. Everything else (images, binaries) is
# skipped rather than decoded.
TEXT_SUFFIXES = {".md", ".markdown", ".yaml", ".yml", ".json", ".py", ".sh",
                 ".txt", ".toml", ".cfg", ".ini", ".xml", ".iml", ".js", ".ts", ""}



def check_public_safety(findings: list[Finding]) -> None:
    """5. No instance identifiers in tracked content. Never baselined, never a warning."""
    self_path = Path(__file__).resolve()
    for p in tracked_files():
        if p.resolve() == self_path or p == BASELINE:
            continue          # the gate states the patterns it hunts for
        if p.suffix.lower() not in TEXT_SUFFIXES or not p.is_file():
            continue
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        rel = str(p.relative_to(ROOT))
        for n, line in enumerate(lines, 1):
            for token in TRACKER_KEY_RE.findall(line):
                if token in PUBLIC_SAFETY_ALLOWED_TOKENS:
                    continue
                findings.append(Finding(
                    "public-safety", f"{rel}:{n}",
                    f"looks like an instance tracker key: {token!r} — this repo is public "
                    f"(if it is a standards identifier, add the exact token to "
                    f"PUBLIC_SAFETY_ALLOWED_TOKENS)"))
            if ABS_HOME_RE.search(line):
                findings.append(Finding(
                    "public-safety", f"{rel}:{n}",
                    "absolute /Users/ home path — a machine path is instance data"))

