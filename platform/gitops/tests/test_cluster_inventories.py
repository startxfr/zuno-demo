"""Every ansible/inventories/<cluster>/ is a complete, self-consistent cluster inventory (per-cluster inventories).

A cluster's inventory directory carries its hosts.yml, its group_vars (zuno_cluster_name equal to the directory name,
which selects the cluster's files and arms resolve_cluster_name.yml's live-cluster guard) and its committed
cluster.yml, which ansible/tasks/load_cluster_vars.yml reads on a workstation and in AAP.

REQUIRED is deliberately modest: the keys a cluster.yml must define because the code reads them without a usable
default. zuno_gitops_target_revision is read without a default by apply_gitops_app.yml and the aap_config role (the
branch of every Application and of the AAP Project); zuno_build_git_ref silently falls back to main in
apply_openshift_build.yml; the ADR-0546 bucket names fall to the ADR-0547 noisy placeholder ZUNO_S3_BUCKET_NOT_SET
(models, mlflow, mlops) or fail an assert (registry_bucket, quay_registry, backups_bucket). Every other key keeps a
role default until a cluster sets it.

Run from the repository root:
    python3 platform/gitops/tests/test_cluster_inventories.py
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import unittest

import yaml

REPO = pathlib.Path(__file__).resolve().parents[3]
INVENTORIES = REPO / "ansible" / "inventories"
REFERENCE = "demo333"
REQUIRED = (
    "zuno_gitops_target_revision",
    "zuno_build_git_ref",
    "zuno_models_s3_bucket",
    "zuno_mlflow_artifacts_s3_bucket",
    "zuno_mlops_s3_bucket",
    "zuno_quay_s3_bucket",
    "zuno_backups_s3_bucket",
)
SHARED_GROUP_VARS = ("auto.yml", "passwords.yml")
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


def inventories():
    return sorted(p for p in INVENTORIES.iterdir() if p.is_dir())


def load(path: pathlib.Path):
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


class ClusterInventories(unittest.TestCase):
    def test_there_is_the_reference_inventory(self):
        self.assertIn(REFERENCE, [p.name for p in inventories()])
        tracked = subprocess.run(["git", "ls-files", "ansible/inventories/demo/", "ansible/clusters/"], cwd=REPO,
                                 capture_output=True, text=True, check=True).stdout.split()
        self.assertEqual(tracked, [], "ansible/inventories/demo is ansible/inventories/demo333, and "
                                      "ansible/clusters/<cluster>.yml is ansible/inventories/<cluster>/cluster.yml")

    def test_every_inventory_has_its_files(self):
        for inv in inventories():
            with self.subTest(inventory=inv.name):
                self.assertRegex(inv.name, NAME)
                for rel in ("hosts.yml", "cluster.yml", "group_vars/all/main.yml",
                            *(f"group_vars/all/{n}" for n in SHARED_GROUP_VARS)):
                    self.assertTrue((inv / rel).is_file(), f"{inv.name}/{rel} is missing")
                hosts = load(inv / "hosts.yml")
                self.assertEqual(list(((hosts.get("all") or {}).get("hosts") or {})), ["localhost"],
                                 f"{inv.name}/hosts.yml: every play is local")

    def test_zuno_cluster_name_is_the_directory_name(self):
        for inv in inventories():
            with self.subTest(inventory=inv.name):
                self.assertEqual(load(inv / "group_vars" / "all" / "main.yml").get("zuno_cluster_name"), inv.name)

    def test_every_cluster_file_defines_the_required_keys(self):
        for inv in inventories():
            data = load(inv / "cluster.yml")
            for key in REQUIRED:
                with self.subTest(inventory=inv.name, key=key):
                    value = data.get(key)
                    self.assertIsInstance(value, str, f"{inv.name}/cluster.yml must set {key}")
                    self.assertTrue(value.strip(), f"{inv.name}/cluster.yml: {key} is empty")
            self.assertRegex(data["zuno_gitops_target_revision"], r"^[A-Za-z0-9._/-]+$")

    def test_no_secret_shaped_key_in_a_committed_file(self):
        secret = re.compile(r"(password|secret_access_key|access_key_id|token|mainpwd)$")
        allowed = {"zuno_ai_gateway_agent_chain_public_key"}
        for inv in inventories():
            for rel in ("cluster.yml", "group_vars/all/main.yml"):
                for key in load(inv / rel):
                    with self.subTest(file=f"{inv.name}/{rel}", key=key):
                        self.assertFalse(secret.search(key) and key not in allowed,
                                         f"{key} looks like a secret: it belongs in confidential.yml")

    def test_shared_group_vars_stay_identical(self):
        for inv in inventories():
            for name in SHARED_GROUP_VARS:
                with self.subTest(inventory=inv.name, file=name):
                    self.assertEqual((inv / "group_vars" / "all" / name).read_bytes(),
                                     (INVENTORIES / REFERENCE / "group_vars" / "all" / name).read_bytes(),
                                     f"{inv.name}/group_vars/all/{name} drifted from {REFERENCE}'s: a per-cluster "
                                     "value goes in main.yml or cluster.yml")

    def test_the_skeleton_follows_main(self):
        skeleton = INVENTORIES / "demo222"
        if skeleton.is_dir():
            self.assertEqual(load(skeleton / "cluster.yml").get("zuno_gitops_target_revision"), "main")
            self.assertTrue((skeleton / "README.md").is_file())

    def test_no_confidential_file_is_tracked(self):
        tracked = subprocess.run(["git", "ls-files", "ansible"], cwd=REPO, capture_output=True, text=True,
                                 check=True).stdout.split()
        leaked = [p for p in tracked if pathlib.PurePosixPath(p).name.startswith("confidential")
                  and "example" not in pathlib.PurePosixPath(p).name]
        self.assertEqual(leaked, [])
        for inv in inventories():
            probe = f"ansible/inventories/{inv.name}/confidential.yml"
            ignored = subprocess.run(["git", "check-ignore", "-q", probe], cwd=REPO)
            self.assertEqual(ignored.returncode, 0, f"{probe} is not gitignored")


if __name__ == "__main__":
    unittest.main()
