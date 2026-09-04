#!/usr/bin/env python3
"""Trigger one real KFP run of the mlops LoRA pipeline for an agent.

WP-126. `make d3 run mlops` wraps this. Reads KFP_HOST/KFP_TOKEN from the
environment, never argv, so the bearer token never shows up in a process
list (`ps aux`) on the Ansible control node.

Resolves the per-agent Pipeline, its latest PipelineVersion, and the
"Default" Experiment by display name - the same three lookups
ansible/roles/rag_ingestion/tasks/recurring_run.yml does over the raw
v2beta1 REST API for recurring runs, done here with the `kfp` SDK instead
since `run_pipeline()` (unlike `recurringruns`) has no REST-body precedent
already proven in this repo. This exact sequence (list_pipelines ->
list_pipeline_versions -> list_experiments -> run_pipeline) was run
manually and confirmed live against a real TrainJob during WP-126
(2026-09-03/04, agent comage) before being wrapped as this script.

Usage (inside components/mlops/tooling/.venv, which already has kfp
installed - see requirements.txt):

    KFP_HOST=https://ds-pipeline-mlops-dspa-zuno-mlops.apps... \
    KFP_TOKEN=$(oc whoami -t) \
    python3 trigger_run.py --agent comage
"""
from __future__ import annotations

import argparse
import datetime
import os
import sys

import kfp

_PIPELINE_DISPLAY_NAME = "MLOps: dataset-to-model LoRA/PEFT pipeline ({agent})"
_EXPERIMENT_DISPLAY_NAME = "Default"
# Matches the system CA bundle this exact call sequence was proven against
# live (2026-09-03/04) - the DSPA route's cert chain needs it on a RHEL/UBI
# control node; Python's own default trust store does not carry it.
_SSL_CA_CERT = "/etc/pki/tls/certs/ca-bundle.crt"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", required=True)
    args = parser.parse_args()

    host = os.environ["KFP_HOST"]
    token = os.environ["KFP_TOKEN"]
    client = kfp.Client(host=host, existing_token=token, ssl_ca_cert=_SSL_CA_CERT)

    display_name = _PIPELINE_DISPLAY_NAME.format(agent=args.agent)
    pipelines = client.list_pipelines(page_size=100).pipelines or []
    matches = [p for p in pipelines if p.display_name == display_name]
    if not matches:
        print(
            f"No pipeline named {display_name!r} found - compile and apply it "
            f"first (make d2 install mlops).",
            file=sys.stderr,
        )
        return 1
    pipeline_id = matches[0].pipeline_id

    versions = (
        client.list_pipeline_versions(
            pipeline_id=pipeline_id, sort_by="created_at desc", page_size=1,
        ).pipeline_versions
        or []
    )
    if not versions:
        print(f"Pipeline {display_name!r} has no versions.", file=sys.stderr)
        return 1
    version_id = versions[0].pipeline_version_id

    experiments = client.list_experiments(page_size=100).experiments or []
    default_experiments = [e for e in experiments if e.display_name == _EXPERIMENT_DISPLAY_NAME]
    if not default_experiments:
        print(f"No {_EXPERIMENT_DISPLAY_NAME!r} KFP experiment found.", file=sys.stderr)
        return 1
    experiment_id = default_experiments[0].experiment_id

    run_id = f"wp126-{datetime.datetime.now():%Y%m%d-%H%M%S}"
    run = client.run_pipeline(
        experiment_id=experiment_id,
        job_name=run_id,
        pipeline_id=pipeline_id,
        version_id=version_id,
        params={"run_id": run_id},
    )
    print(f"run_id={run_id} kfp_run_id={run.run_id}")
    print(f"{host}/#/runs/details/{run.run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
