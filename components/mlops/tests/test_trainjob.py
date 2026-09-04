"""ADR-0539/WP-119 coverage for components/mlops/src/trainjob.py.

Proves the properties the work package's acceptance rests on, without an
API server: (1) credentials NEVER travel as literal values in a TrainJob
spec, (2) configuration does, (3) the acceptance-gate secrets are not
forwarded at all, (4) the submitted body targets the namespaced
TrainingRuntime and runs the non-recursing `train-lora-local` stage, and
(5) the terminal-state reader treats a controller vocabulary it does not
recognise as "still running" rather than as success.

Run from components/mlops:

    python3 tests/test_trainjob.py
"""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import trainjob  # noqa: E402


_ENV = {
    "MLOPS_AGENT": "comage",
    "MLOPS_RUN_ID": "wesh-20260829-145123",
    "MLOPS_LORA_R": "8",
    "S3_BUCKET": "test-bucket",  # ADR-0546/WP-131: neutral, never a real cluster bucket
    "PGHOST": "zuno-postgresql-primary.zuno-data.svc",
    "MLFLOW_TRACKING_URI": "https://mlflow.redhat-ods-applications.svc:8443/mlflow",
    "MLFLOW_WORKSPACE": "zuno-mlops",
    "MODEL_REGISTRY_URL": "https://zuno.rhoai-model-registries.svc:8443",
    "MLOPS_TRAINJOB_S3_SECRET": "mlops-s3-credentials",
    "MLOPS_TRAINJOB_PG_SECRET": "mlops-postgres-credentials",
    # Must never appear as literals:
    "AWS_ACCESS_KEY_ID": "AKIAREALKEY",
    "AWS_SECRET_ACCESS_KEY": "s3cr3t",
    "PGUSER": "mlops",
    "PGPASSWORD": "hunter2",
    "DEMO_PERSONA_PASSWORD": "persona-pw",
    "COMAGE_FRONTEND_CLIENT_SECRET": "client-secret",
    # Unrelated: must not be swept in.
    "HOME": "/opt/app-root/src",
    "PATH": "/usr/bin",
}


class SecretHygiene(unittest.TestCase):
    """The property that would otherwise be a convention.

    A literal credential in a TrainJob spec sits in etcd, readable by
    anyone holding `get trainjobs` in the namespace. This must fail the
    build, not a review.
    """

    def test_no_credential_value_appears_anywhere_in_the_body(self):
        body = trainjob.build_trainjob(run_id="r1", agent="comage", environ=_ENV)
        rendered = repr(body)
        for secret in ("AKIAREALKEY", "s3cr3t", "hunter2", "persona-pw", "client-secret"):
            self.assertNotIn(secret, rendered,
                             f"credential value {secret!r} leaked into the TrainJob spec")

    def test_credentials_travel_as_secret_refs(self):
        env = trainjob.build_env(_ENV)
        refs = {e["name"]: e["valueFrom"]["secretKeyRef"]
                for e in env if "valueFrom" in e}
        self.assertEqual(sorted(refs), ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
                                        "PGPASSWORD", "PGUSER"])
        self.assertEqual(refs["AWS_ACCESS_KEY_ID"]["name"], "mlops-s3-credentials")
        self.assertEqual(refs["PGUSER"]["name"], "mlops-postgres-credentials")

    def test_gate_credentials_are_not_forwarded_at_all(self):
        # evaluate needs these and evaluate stays a KFP step; a training
        # pod has no business holding a persona password.
        names = {e["name"] for e in trainjob.build_env(_ENV)}
        self.assertNotIn("DEMO_PERSONA_PASSWORD", names)
        self.assertNotIn("COMAGE_FRONTEND_CLIENT_SECRET", names)

    def test_missing_secret_names_emit_no_dangling_refs(self):
        env = trainjob.build_env({k: v for k, v in _ENV.items()
                                  if not k.startswith("MLOPS_TRAINJOB_")})
        self.assertEqual([e for e in env if "valueFrom" in e], [])


class ConfigForwarding(unittest.TestCase):
    def test_configuration_travels_as_literals(self):
        literals = {e["name"]: e["value"] for e in trainjob.build_env(_ENV) if "value" in e}
        for key in ("MLOPS_AGENT", "S3_BUCKET", "PGHOST", "MLFLOW_TRACKING_URI",
                    "MLFLOW_WORKSPACE", "MODEL_REGISTRY_URL", "MLOPS_LORA_R"):
            self.assertIn(key, literals)
        self.assertEqual(literals["MLFLOW_WORKSPACE"], "zuno-mlops")

    def test_unrelated_environment_is_not_swept_in(self):
        names = {e["name"] for e in trainjob.build_env(_ENV)}
        self.assertNotIn("HOME", names)
        self.assertNotIn("PATH", names)


class BodyShape(unittest.TestCase):
    def test_targets_the_namespaced_runtime_and_the_local_stage(self):
        body = trainjob.build_trainjob(run_id="r1", agent="comage", environ=_ENV)
        self.assertEqual(body["spec"]["runtimeRef"],
                         {"apiGroup": "trainer.kubeflow.org",
                          "kind": "TrainingRuntime", "name": "mlops-lora"})
        # train-lora-local, NOT train-lora: the dispatcher would otherwise
        # recurse and the trainer pod would submit another TrainJob.
        self.assertEqual(body["spec"]["trainer"]["args"],
                         ["train-lora-local", "--run-id", "r1"])
        self.assertEqual(body["metadata"]["labels"]["zuno.io/run-id"], "r1")
        # generateName, so a KFP retry cannot collide with the previous try.
        self.assertNotIn("name", body["metadata"])
        self.assertTrue(body["metadata"]["generateName"].startswith("lora-comage-"))


class TerminalState(unittest.TestCase):
    def test_recognises_complete_and_failed(self):
        self.assertEqual(trainjob._terminal(
            {"status": {"conditions": [{"type": "Complete", "status": "True"}]}}), "complete")
        self.assertEqual(trainjob._terminal(
            {"status": {"conditions": [{"type": "Failed", "status": "True"}]}}), "failed")

    def test_false_conditions_are_not_terminal(self):
        self.assertIsNone(trainjob._terminal(
            {"status": {"conditions": [{"type": "Complete", "status": "False"}]}}))

    def test_unknown_vocabulary_is_still_running_not_success(self):
        # The controller's condition vocabulary is not pinned by the CRD.
        # Guessing "done" from an unrecognised type would let merge-export
        # start against a model that was never written.
        for status in ({}, {"status": {}}, {"status": {"conditions": []}},
                       {"status": {"conditions": [{"type": "Suspended", "status": "True"}]}},
                       {"status": {"jobsStatus": [{"succeeded": 1}]}}):
            self.assertIsNone(trainjob._terminal(status), status)

    def test_a_failed_job_counter_is_terminal(self):
        self.assertEqual(trainjob._terminal(
            {"status": {"jobsStatus": [{"failed": 1}]}}), "failed")


class EnabledFlag(unittest.TestCase):
    def test_parses_the_usual_truthy_spellings(self):
        import os
        for raw, expected in (("true", True), ("True", True), ("1", True), ("yes", True),
                              ("false", False), ("", False), ("no", False)):
            os.environ["MLOPS_TRAINJOB_ENABLED"] = raw
            self.assertIs(trainjob.enabled(), expected, raw)
        del os.environ["MLOPS_TRAINJOB_ENABLED"]
        self.assertFalse(trainjob.enabled())


if __name__ == "__main__":
    unittest.main(verbosity=2)
