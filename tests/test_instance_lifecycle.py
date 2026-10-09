#!/usr/bin/env python3
"""The one-repository lifecycle, driven end to end: bootstrap → commit → upgrade.

    python3 -m unittest tests.test_instance_lifecycle

Every case builds a throwaway "upstream" from THIS working tree (tracked and untracked,
minus what git ignores), so what is tested is the framework as it is about to be
committed, not a hand-made stand-in. Instances are then cloned from it, bootstrapped
with `scripts/bootstrap.sh`, and upgraded with `scripts/upgrade.sh` after the upstream
moves — the exact sequence an adopter runs, with no network and no real remote.

The load-bearing assertions are the ones `systems/distribution.md` promises:

  * an upgrade changes framework paths and no instance path;
  * an instance that edited a framework path is refused, and told which path;
  * the framework's own gate passes inside an instance (it scopes itself);
  * an instance created from a template snapshot (no shared history) upgrades too;
  * nothing bootstrap generates is tracked, and bootstrap is idempotent.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
    # a fixture pack is a local repository, mounted as a submodule from a path
    "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "protocol.file.allow",
    "GIT_CONFIG_VALUE_0": "always",
    "GIT_CONFIG_NOSYSTEM": "1", "HOME": tempfile.gettempdir(),
}


def run(cmd, cwd: Path, check=True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True,
                          timeout=180, env={**os.environ, **GIT_ENV})


def git(cwd: Path, *args: str) -> str:
    return run(["git", *args], cwd).stdout.strip()


def working_tree_files() -> list[str]:
    """What this checkout would publish: tracked plus untracked-but-not-ignored files.

    Instance files of a developer checkout (bootstrap --local) are excluded by git
    itself; an unexpected real instance file here would be the gate's problem, not
    this fixture's.
    """
    out = run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
              ROOT).stdout
    return [n for n in out.split("\0") if n and not n.startswith(".idea/")]


class LifecycleTest(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="metaos-lifecycle-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.upstream = self.tmp / "upstream"
        self.upstream.mkdir()
        for rel in working_tree_files():
            src = ROOT / rel
            if not src.is_file():          # a gitlink or a vanished path
                continue
            dst = self.upstream / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst, follow_symlinks=False)
        git(self.upstream, "init", "-q", "-b", "main")
        git(self.upstream, "add", "-A")
        git(self.upstream, "commit", "-q", "-m", "framework v1")
        self.v1 = git(self.upstream, "rev-parse", "HEAD")

    # --- helpers -----------------------------------------------------------------

    def clone_instance(self, name="inst") -> Path:
        inst = self.tmp / name
        git(self.tmp, "clone", "-q", str(self.upstream), str(inst))
        return inst

    def bootstrap(self, inst: Path, *extra: str) -> str:
        r = run(["scripts/bootstrap.sh", "--yes", "--name", inst.name,
                 "--upstream", str(self.upstream), *extra], inst)
        return r.stdout

    def upstream_commit(self, msg: str, edits: dict[str, str]) -> str:
        for rel, text in edits.items():
            p = self.upstream / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a") as fh:
                fh.write(text)
        git(self.upstream, "add", "-A")
        git(self.upstream, "commit", "-q", "-m", msg)
        return git(self.upstream, "rev-parse", "HEAD")

    def instance_files(self, inst: Path) -> dict[str, str]:
        """Content of every instantiated file, keyed by its root-relative path."""
        payload = inst / "instance-template" / "root"
        out = {}
        for p in payload.rglob("*"):
            if p.is_file():
                rel = p.relative_to(payload)
                out[str(rel)] = (inst / rel).read_text()
        return out

    # --- bootstrap ------------------------------------------------------------------

    def test_bootstrap_instantiates_every_payload_path_and_fills_placeholders(self):
        inst = self.clone_instance()
        out = self.bootstrap(inst)
        self.assertIn("is live", out)
        payload = inst / "instance-template" / "root"
        for p in payload.rglob("*"):
            if p.is_file():
                rel = p.relative_to(payload)
                self.assertTrue((inst / rel).is_file(), f"{rel} not instantiated")
                text = (inst / rel).read_text()
                self.assertNotIn("{{", text, f"{rel} still carries a placeholder")
        contract = (inst / ".claude" / "CLAUDE.md").read_text()
        self.assertIn(f"# {inst.name} — Agentic OS instance", contract)
        cfg = (inst / "meta-os.config.json").read_text()
        self.assertIn(f'"name": "{inst.name}"', cfg)
        self.assertIn(f'"template": "{self.v1}"', cfg)
        # the payload itself is never touched
        self.assertIn("{{instance-name}}", (payload / "_index.md").read_text())

    def test_the_instantiated_config_validates_against_the_framework_schema(self):
        try:
            import jsonschema  # the gates' own dependency; CI installs it
        except ModuleNotFoundError:
            self.skipTest("jsonschema not installed")
        import json
        inst = self.clone_instance()
        self.bootstrap(inst)
        schema = json.loads((inst / "systems" / "meta-os.config.schema.json").read_text())
        cfg = json.loads((inst / "meta-os.config.json").read_text())
        jsonschema.Draft7Validator(schema).validate(cfg)
        self.assertEqual(cfg["instance"]["template"], self.v1)

    def test_bootstrap_points_the_remotes_the_right_way_round(self):
        inst = self.clone_instance()
        self.bootstrap(inst, "--origin", "https://example.invalid/me/private.git")
        remotes = git(inst, "remote", "-v")
        self.assertIn("upstream\t" + str(self.upstream) + " (fetch)", remotes)
        self.assertIn("upstream\tno_push (push)", remotes)
        self.assertIn("origin\thttps://example.invalid/me/private.git", remotes)

    def test_bootstrap_builds_the_discovery_links_and_tracks_none_of_them(self):
        inst = self.clone_instance()
        self.bootstrap(inst, "--commit")
        for d in (ROOT / "skills").iterdir():
            if d.is_dir() and not d.is_symlink() and (d / "SKILL.md").is_file():
                link = inst / ".claude" / "skills" / d.name
                self.assertTrue(link.is_symlink(), f".claude/skills/{d.name} missing")
                self.assertTrue(link.resolve().is_dir())
        tracked = git(inst, "ls-files").splitlines()
        self.assertNotIn(".claude/skills/graphify", tracked)
        self.assertIn(".claude/CLAUDE.md", tracked)
        self.assertIn("meta-os.config.json", tracked)
        self.assertEqual(git(inst, "status", "--porcelain"), "")

    def test_bootstrap_is_idempotent(self):
        inst = self.clone_instance()
        self.bootstrap(inst, "--commit")
        before = git(inst, "rev-parse", "HEAD")
        out = self.bootstrap(inst)
        payload = sum(1 for p in (inst / "instance-template" / "root").rglob("*") if p.is_file())
        self.assertIn(f"created 0, kept {payload} already present", out)
        self.assertIn("Already bootstrapped", out)
        self.assertEqual(before, git(inst, "rev-parse", "HEAD"))
        self.assertEqual(git(inst, "status", "--porcelain"), "")

    def test_an_uncommitted_first_bootstrap_fills_its_gaps_on_a_rerun(self):
        inst = self.clone_instance()
        self.bootstrap(inst)
        (inst / "_index.md").unlink()
        out = self.bootstrap(inst)
        self.assertIn("created 1,", out)
        self.assertTrue((inst / "_index.md").is_file())
        self.assertNotIn("not recreated", out)

    def test_a_second_checkout_of_a_committed_instance_bootstraps_clean(self):
        # A new machine clones the INSTANCE's repository: its pinned pack arrives as an
        # empty folder, it has no upstream remote, and a template file the instance
        # removed is missing on purpose. Bootstrap must finish, fetch the framework,
        # initialise the pack, recreate nothing, and leave the gate green.
        pack = self.tmp / "src" / "demo"
        (pack / "skills" / "demo-skill").mkdir(parents=True)
        (pack / "skills" / "demo-skill" / "SKILL.md").write_text(
            "---\nname: demo-skill\ndescription: fixture\n---\n# demo\n")
        (pack / "pack.yaml").write_text("name: demo\nversion: 0.1.0\ndescription: fixture\n")
        git(pack, "init", "-q", "-b", "main")
        git(pack, "add", "-A"); git(pack, "commit", "-q", "-m", "pack")
        first = self.clone_instance("first")
        self.bootstrap(first, "--commit")
        run(["scripts/packs.sh", "add", "demo", str(pack)], first)
        git(first, "rm", "-q", ".githooks.d/README.md")
        git(first, "add", "-A"); git(first, "commit", "-q", "-m", "mount a pack, drop a template file")
        origin = self.tmp / "instance-origin.git"
        git(self.tmp, "clone", "-q", "--bare", str(first), str(origin))

        second = self.tmp / "second"
        git(self.tmp, "clone", "-q", str(origin), str(second))
        self.assertEqual(list((second / ".packs" / "demo").iterdir()), [])   # the clone's empty pin
        self.assertNotIn("upstream", git(second, "remote"))
        out = self.bootstrap(second)
        self.assertIn("not recreated", out)
        self.assertIn(".githooks.d/README.md", out)
        self.assertFalse((second / ".githooks.d" / "README.md").exists())
        self.assertIn("fetched upstream", out)
        self.assertEqual(git(second, "rev-parse", "upstream/main"), self.v1)
        self.assertTrue((second / ".packs" / "demo" / "pack.yaml").is_file())
        self.assertTrue((second / ".claude" / "skills" / "demo-skill").is_symlink())
        self.assertEqual(git(second, "status", "--porcelain"), "")
        r = run(["python3", "scripts/validate_framework.py"], second, check=False)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_bootstrap_dry_run_writes_nothing(self):
        inst = self.clone_instance()
        out = self.bootstrap(inst, "--dry-run")
        self.assertIn("would create: .claude/CLAUDE.md", out)
        self.assertIn("would create ", out)
        self.assertNotIn("  created ", out)
        self.assertNotIn("is live", out)
        self.assertIn("Dry run — nothing was written", out)
        self.assertFalse((inst / ".claude" / "CLAUDE.md").exists())
        self.assertEqual(git(inst, "status", "--porcelain"), "")
        self.assertIn("origin", git(inst, "remote"))

    def test_developer_mode_keeps_the_instance_files_out_of_git(self):
        inst = self.clone_instance("dev")
        out = self.bootstrap(inst, "--local")
        self.assertIn("developer mode", out)
        self.assertTrue((inst / ".claude" / "CLAUDE.md").is_file())
        self.assertEqual(git(inst, "status", "--porcelain"), "")
        self.assertIn("origin", git(inst, "remote"))       # remotes untouched
        self.assertNotIn("upstream", git(inst, "remote"))

    # --- the gate inside an instance ----------------------------------------------

    def test_the_framework_gate_passes_inside_a_bootstrapped_instance(self):
        inst = self.clone_instance()
        self.bootstrap(inst, "--commit")
        # the instance adds its own content at instance paths, including a tracker-key
        # lookalike assembled at run time: the gate must not judge instance paths
        key = "AB" + "C-" + "42"
        note = inst / "memory" / "raw" / "capture.md"
        note.write_text("---\ntype: note\n---\nsee " + key + " in the tracker\n")
        # ...and additions of its own beside the framework's files: a workflow in
        # .github/workflows/, a top-level folder with no _index.md, a file at the root
        (inst / ".github" / "workflows" / "estate.yml").write_text(f"name: estate  # {key}\n")
        (inst / "harness").mkdir()
        (inst / "harness" / "run.md").write_text(f"# run {key}\n")
        (inst / "ontology.yaml").write_text(f"types: [{key}]\n")
        git(inst, "add", "-A"); git(inst, "commit", "-q", "-m", "a capture")
        r = run(["python3", "scripts/validate_framework.py"], inst, check=False)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_the_framework_gate_refuses_a_tracked_instance_path_in_the_framework(self):
        fw = self.tmp / "fw"
        git(self.tmp, "clone", "-q", str(self.upstream), str(fw))
        (fw / "memory").mkdir()
        (fw / "memory" / "_index.md").write_text("---\ntype: index\ntags: [x]\n---\n# memory\n")
        git(fw, "add", "-A"); git(fw, "commit", "-q", "-m", "oops")
        r = run(["python3", "scripts/validate_framework.py"], fw, check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("instance-path-tracked", r.stdout)
        self.assertIn("memory/_index.md", r.stdout)

    # --- upgrade --------------------------------------------------------------------------

    def test_upgrade_takes_the_framework_and_leaves_every_instance_path_alone(self):
        inst = self.clone_instance()
        self.bootstrap(inst, "--commit")
        before = self.instance_files(inst)
        v2 = self.upstream_commit("framework v2", {
            "systems/engine.md": "\nv2 line\n",
            "skills/new-skill/SKILL.md": "---\nname: new-skill\ndescription: test\n---\n# new\n",
            "instance-template/root/_index.md": "\ntemplate v2\n",
        })
        r = run(["scripts/upgrade.sh"], inst)
        self.assertIn("1 commit(s) behind", r.stdout)
        self.assertIn("instance-template/root/_index.md", r.stdout)   # drift reported
        self.assertIn("v2 line", (inst / "systems" / "engine.md").read_text())
        self.assertTrue((inst / ".claude" / "skills" / "new-skill").is_symlink())
        self.assertEqual(before, self.instance_files(inst))
        self.assertEqual(git(inst, "status", "--porcelain"), "")
        self.assertEqual(git(inst, "rev-parse", "upstream/main"), v2)
        # --check reports and changes nothing; --ack-template records the reviewed ref
        r = run(["scripts/upgrade.sh", "--check"], inst)
        self.assertIn("0 commit(s) behind", r.stdout)
        run(["scripts/upgrade.sh", "--ack-template"], inst)
        self.assertIn(f'"template": "{v2}"', (inst / "meta-os.config.json").read_text())
        git(inst, "commit", "-qam", "ack template")
        r = run(["scripts/upgrade.sh", "--check"], inst)
        self.assertIn("template: unchanged", r.stdout)

    def test_upgrade_refuses_when_the_instance_edited_a_framework_path(self):
        inst = self.clone_instance()
        self.bootstrap(inst, "--commit")
        with (inst / "systems" / "engine.md").open("a") as fh:
            fh.write("\nlocal hack\n")
        git(inst, "commit", "-qam", "instance edits a framework path")
        self.upstream_commit("framework v2", {"README.md": "\nv2\n"})
        r = run(["scripts/upgrade.sh"], inst, check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("edited: systems/engine.md", r.stdout)
        self.assertIn("refusing", r.stderr)
        self.assertNotIn("v2", (inst / "README.md").read_text())
        r = run(["scripts/upgrade.sh", "--check"], inst)      # check still reports
        self.assertIn("edited: systems/engine.md", r.stdout)

    def test_an_instance_created_from_a_template_snapshot_upgrades_too(self):
        # GitHub's "Use this template" copies the files into a new history. The first
        # upgrade has no merge base; every conflict is a framework path the framework
        # itself moved, resolved to the framework's version.
        inst = self.tmp / "tpl"
        inst.mkdir()
        archive = subprocess.run(["git", "archive", self.v1], cwd=self.upstream, check=True,
                                 capture_output=True, env={**os.environ, **GIT_ENV}).stdout
        subprocess.run(["tar", "-xf", "-"], cwd=inst, input=archive, check=True)
        git(inst, "init", "-q", "-b", "main")
        git(inst, "add", "-A"); git(inst, "commit", "-q", "-m", "Initial commit")
        self.bootstrap(inst, "--commit")
        before = self.instance_files(inst)
        self.upstream_commit("framework v2", {"systems/engine.md": "\nv2 line\n", "README.md": "\nv2\n"})
        r = run(["scripts/upgrade.sh"], inst)
        self.assertIn("unrelated", r.stdout + r.stderr)
        self.assertIn("v2 line", (inst / "systems" / "engine.md").read_text())
        self.assertEqual(before, self.instance_files(inst))
        self.assertEqual(git(inst, "status", "--porcelain"), "")
        # from here on there is a merge base: a second upgrade is an ordinary merge
        self.upstream_commit("framework v3", {"README.md": "\nv3\n"})
        r = run(["scripts/upgrade.sh"], inst)
        self.assertNotIn("unrelated", r.stdout)
        self.assertIn("v3", (inst / "README.md").read_text())

    def test_upgrade_refuses_an_unbootstrapped_checkout(self):
        inst = self.clone_instance()
        r = run(["scripts/upgrade.sh"], inst, check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not bootstrapped", r.stderr)
        self.assertIn("--adopt", r.stderr)          # the way in for an instance with its own history


if __name__ == "__main__":
    unittest.main()
