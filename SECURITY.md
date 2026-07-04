# Security Policy

## What a vulnerability means here

This repository ships **prompt-based skills and conventions** executed by AI coding
assistants (Claude Code and compatible hosts) — not a runtime service. Security issues
that matter in this context:

- **Prompt-injection vectors** — skill or reference content that could steer an assistant
  into unintended actions (exfiltrating data, running destructive commands, bypassing
  confirmation gates).
- **Dangerous instructions** — skill steps that would make an assistant execute unsafe
  shell commands, leak secrets, or weaken a host's safety configuration.
- **Supply-chain issues** — vendored skill content (see [PROVENANCE.md](PROVENANCE.md))
  diverging maliciously from its upstream, or instructions pinning known-vulnerable tool
  versions.

## Reporting

Use **GitHub private vulnerability reporting**: *Security → Report a vulnerability* on
this repository. Reports are triaged on a best-effort basis — this is a solo-maintained
project.

Please do **not** open public issues for security-sensitive findings.

## Supported versions

Rolling `main` only. No release branches are maintained; fixes land on `main` via PR.

## Scope notes

- Skills here are inert text until a host executes them; hardening of the *host*
  (permission modes, sandboxes, hooks) is out of scope for this repo but strongly
  recommended — see your assistant's security documentation.
- Instance data (private registries, memory, credentials) must never live in this repo by
  design; report any leak you find as a vulnerability.
