#!/usr/bin/env python3
"""Unit tests for the mlops pipeline CLI (ADR-0301/ADR-0302, WP-34).

Same plain-script convention as components/rag-ingestion/tests/*.py: a
flat TESTS list of bare-assert functions, no pytest, no live S3/Postgres/
Model Registry/GPU - every stage function is exercised against fakes/
mocks. torch/transformers/peft/datasets are never imported by these
tests: _run_lora_training (the one function that imports them, lazily,
internally) is monkeypatched rather than executed for real, so this file
never needs those packages installed - the "training code path exercised
with a tiny CPU-safe config" WP-34's own brief asks for is proven by
train-lora's S3 round-trip/manifest contract, not by running a real model
download in CI.

Run directly:

    cd components/mlops && python3 tests/test_mlops.py
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import unittest.mock as mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("PGHOST", "localhost")
os.environ.setdefault("PGDATABASE", "testdb")
os.environ.setdefault("MLOPS_AGENT", "comage")
os.environ.setdefault("MLOPS_RUN_ID", "run-001")

import mlops  # noqa: E402


class _FakeStore:
    """In-memory stand-in for ArtifactStore - every stage function only
    ever calls put_json/get_json/put_text/get_bytes/put_dir/list_keys/
    download_prefix, so a plain dict-backed fake covers every call site
    without touching boto3 at all."""

    def __init__(self):
        self.objects: dict = {}

    @property
    def bucket(self):
        return "test-bucket"

    def _ns(self, bucket):
        """WP-087: the real store spans several buckets in several regions.
        The fake namespaces non-default buckets by prefix so a cross-bucket
        write cannot silently land in the default one and pass a test that
        would fail live."""
        return "" if bucket in (None, "test-bucket") else f"@{bucket}/"

    def download_prefix(self, bucket, prefix, local_dir, *, region=None, endpoint=None, include=None):
        prefix = self._ns(bucket) + prefix.rstrip("/") + "/"
        count = 0
        for key, data in self.objects.items():
            if key.startswith(prefix) and (include is None or include(key[len(prefix):])):
                target = pathlib.Path(local_dir) / key[len(prefix):]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                count += 1
        return count

    def put_json(self, key, obj):
        self.objects[key] = json.dumps(obj).encode("utf-8")

    def get_json(self, key):
        raw = self.objects.get(key)
        return json.loads(raw) if raw is not None else None

    def put_text(self, key, text):
        self.objects[key] = text.encode("utf-8")

    def get_bytes(self, key, *, bucket=None, region=None, endpoint=None):
        return self.objects.get(self._ns(bucket) + key)

    def put_bytes(self, key, data, *, bucket=None):
        self.objects[self._ns(bucket) + key] = data

    def put_dir(self, prefix, local_dir, *, bucket=None, region=None, endpoint=None):
        uploaded = []
        for path in sorted(local_dir.rglob("*")):
            if path.is_file():
                key = f"{self._ns(bucket)}{prefix}/{path.relative_to(local_dir).as_posix()}"
                self.objects[key] = path.read_bytes()
                uploaded.append(key)
        return uploaded

    def list_keys(self, prefix, *, bucket=None, region=None, endpoint=None):
        full = self._ns(bucket) + prefix
        return [k for k in self.objects if k.startswith(full)]


def _config(**overrides) -> "mlops.MlopsConfig":
    base = dict(
        s3_endpoint=None,
        s3_bucket="test-bucket",
        s3_region=None,
        s3_path_style=False,
        aws_access_key_id=None,
        aws_secret_access_key=None,
        dataset_prefix="mlops/datasets",
        model_prefix="mlops/models",
        eval_prefix="mlops/evaluations",
        registry_prefix="mlops/registrations",
        pg_host="localhost",
        pg_port=5432,
        pg_database="testdb",
        pg_schema="public",
        pg_sslmode="require",
        pg_user=None,
        pg_password=None,
        agent="comage",
        run_id="run-001",
        knowledge_domains=["knowledge.sales"],
        max_dataset_rows=500,
        base_model="tiny-test-model",
        lora_r=8,
        lora_alpha=16,
        lora_dropout=0.05,
        cpu_safe=True,
        seed=42,
        deterministic=True,
        # ADR-0526 (WP-087). style_corpus_s3uri defaults to None here on
        # purpose: the default fixture must keep exercising WP-34's
        # grounding-domain branch, so the style branch is opted into
        # per-test rather than silently becoming the default everywhere.
        style_corpus_s3uri=None,
        merged_model_s3uri=None,
        merged_overwrite=False,
        models_s3_region=None,
        models_s3_endpoint=None,
        lora_target_modules=None,
        evaluations_dir="/nonexistent",
        agents_dir="/nonexistent",
        model_registry_url=None,
        model_registry_namespace="rhoai-model-registries",
        registered_model_name=None,
        model_registry_service="zuno",
        model_registry_port=8443,
        model_registry_scheme="https",
        model_registry_ca_bundle=None,
        model_registry_token_path=None,
    )
    base.update(overrides)
    return mlops.MlopsConfig(**base)


# --- _escalate ----------------------------------------------------------


def test_escalate_never_downgrades() -> None:
    assert mlops._escalate("C2", "C1") == "C2"


def test_escalate_upgrades_when_candidate_is_higher() -> None:
    assert mlops._escalate("C1", "C3") == "C3"


def test_escalate_unknown_candidate_defaults_to_c1_weight() -> None:
    assert mlops._escalate("C2", "not-a-real-level") == "C2"


# --- config parsing -------------------------------------------------------


def test_env_list_parses_comma_separated_values() -> None:
    with mock.patch.dict(os.environ, {"MLOPS_KNOWLEDGE_DOMAINS": "knowledge.sales, knowledge.project"}):
        assert mlops._env_list("MLOPS_KNOWLEDGE_DOMAINS") == ["knowledge.sales", "knowledge.project"]


def test_env_list_defaults_to_empty_when_unset() -> None:
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("MLOPS_NOT_SET_ANYWHERE", None)
        assert mlops._env_list("MLOPS_NOT_SET_ANYWHERE") == []


def test_load_config_reads_the_real_process_environment() -> None:
    config = mlops.load_config()
    assert config.agent == "comage"
    assert config.run_id == "run-001"
    assert config.s3_bucket == "test-bucket"
    # D5: the real Helm value, never the ADRs' original stale zuno-ai-build.
    assert config.model_registry_namespace == "rhoai-model-registries"


# --- prepare-dataset --------------------------------------------------------


def test_load_scenario_seed_texts_filters_to_chat_shaped_scenarios(tmp_path=None) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        agent_dir = pathlib.Path(tmp) / "comage"
        agent_dir.mkdir()
        (agent_dir / "scenarios.yaml").write_text(
            "scenarios:\n"
            "  - id: 1\n"
            "    title: chat one\n"
            "    type: chat_basic_qa\n"
            "    message: What is the deal status?\n"
            "  - id: 2\n"
            "    title: not a chat scenario\n"
            "    type: portal_requires_login\n"
        )
        config = _config(evaluations_dir=tmp)
        texts = mlops._load_scenario_seed_texts(config)
    assert texts == ["What is the deal status?"]


def test_load_scenario_seed_texts_missing_file_returns_empty_not_an_error() -> None:
    config = _config(evaluations_dir="/definitely/does/not/exist")
    assert mlops._load_scenario_seed_texts(config) == []


def test_stage_prepare_dataset_escalates_classification_and_writes_manifest() -> None:
    config = _config()
    store = _FakeStore()
    fake_rows = [
        {"source": "doc-1", "title": "Doc 1", "content": "Acme Renewal is in Negotiation.", "metadata": {"classification": "C1"}},
        {"source": "doc-2", "title": "Doc 2", "content": "Sales pipeline overview.", "metadata": {"classification": "C2"}},
    ]
    with mock.patch.object(mlops, "_fetch_domain_grounding_rows", return_value=fake_rows), \
         mock.patch.object(mlops, "_load_scenario_seed_texts", return_value=["What's the deal status?"]):
        mlops.stage_prepare_dataset(config, store)

    manifest = store.get_json("mlops/datasets/comage/run-001/dataset_manifest.json")
    assert manifest["classification"] == "C2"
    assert manifest["example_count"] == 3
    assert manifest["grounding_row_count"] == 2
    assert manifest["scenario_seed_count"] == 1

    lines = store.get_bytes("mlops/datasets/comage/run-001/examples.jsonl").decode("utf-8").splitlines()
    assert len(lines) == 3
    assert "Acme Renewal" in lines[0]


# --- train-lora --------------------------------------------------------


def test_stage_train_lora_requires_a_dataset_manifest_first() -> None:
    config = _config()
    store = _FakeStore()
    try:
        mlops.stage_train_lora(config, store)
        raised = False
    except SystemExit:
        raised = True
    assert raised, "expected SystemExit when no dataset_manifest.json exists"


def test_stage_train_lora_uploads_adapter_and_writes_train_manifest() -> None:
    config = _config()
    store = _FakeStore()
    store.put_json(
        "mlops/datasets/comage/run-001/dataset_manifest.json",
        {"classification": "C2", "example_count": 1, "knowledge_domains": ["knowledge.sales"]},
    )
    store.put_text("mlops/datasets/comage/run-001/examples.jsonl", json.dumps({"text": "hello", "source": "doc-1"}))

    def _fake_train(cfg, examples, output_dir, base_model_ref=None, held_out=None):
        # A non-s3 base model passes through _resolve_base_model untouched.
        assert base_model_ref == cfg.base_model
        # WP-087: no test.jsonl in this fixture (it is a grounding-domain
        # run, not a style one), so nothing is held out and no register
        # samples are produced - the legacy path stays untouched.
        assert held_out == []
        (output_dir / "adapter").mkdir(parents=True, exist_ok=True)
        (output_dir / "adapter" / "adapter_config.json").write_text("{}")
        (output_dir / "adapter" / "adapter_model.bin").write_bytes(b"fake-weights")
        return {"train_loss": 0.1, "steps": 5}

    with mock.patch.object(mlops, "_run_lora_training", side_effect=_fake_train):
        mlops.stage_train_lora(config, store)

    manifest = store.get_json("mlops/models/comage/run-001/train_manifest.json")
    assert manifest["classification"] == "C2"
    assert manifest["adapter_s3_prefix"] == "mlops/models/comage/run-001/adapter"
    assert sorted(manifest["adapter_files"]) == [
        "mlops/models/comage/run-001/adapter/adapter_config.json",
        "mlops/models/comage/run-001/adapter/adapter_model.bin",
    ]
    assert store.get_bytes("mlops/models/comage/run-001/adapter/adapter_model.bin") == b"fake-weights"


def test_resolve_base_model_passthrough_for_hf_repo_id() -> None:
    config = _config(base_model="ibm-granite/granite-3.1-2b-instruct")
    with tempfile.TemporaryDirectory() as tmp:
        ref = mlops._resolve_base_model(config, _FakeStore(), pathlib.Path(tmp))
    assert ref == "ibm-granite/granite-3.1-2b-instruct"


def test_resolve_base_model_downloads_s3_uri() -> None:
    config = _config(base_model="s3://some-bucket/models/qwen3.5-9b")
    store = _FakeStore()
    store.objects["models/qwen3.5-9b/config.json"] = b"{}"
    store.objects["models/qwen3.5-9b/model.safetensors"] = b"fake-weights"
    with tempfile.TemporaryDirectory() as tmp:
        ref = mlops._resolve_base_model(config, store, pathlib.Path(tmp))
        local = pathlib.Path(ref)
        assert local == pathlib.Path(tmp) / "base-model"
        assert (local / "config.json").read_bytes() == b"{}"
        assert (local / "model.safetensors").read_bytes() == b"fake-weights"


def test_resolve_base_model_fails_on_empty_or_configless_prefix() -> None:
    config = _config(base_model="s3://some-bucket/models/missing")
    store = _FakeStore()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            mlops._resolve_base_model(config, store, pathlib.Path(tmp))
        except SystemExit:
            pass
        else:
            raise AssertionError("expected SystemExit on an empty base-model prefix")


# --- evaluate --------------------------------------------------------


def test_stage_evaluate_requires_a_train_manifest_first() -> None:
    config = _config()
    store = _FakeStore()
    try:
        mlops.stage_evaluate(config, store)
        raised = False
    except SystemExit:
        raised = True
    assert raised, "expected SystemExit when no train_manifest.json exists"


def test_stage_evaluate_writes_gate_result_and_raises_on_a_failing_gate() -> None:
    config = _config()
    store = _FakeStore()
    store.put_json(
        "mlops/models/comage/run-001/train_manifest.json",
        {"classification": "C2", "adapter_s3_prefix": "mlops/models/comage/run-001/adapter"},
    )

    fake_quality_gate = mock.MagicMock()
    fake_quality_gate.QualityGateError = RuntimeError
    fake_quality_gate.evaluate = mock.MagicMock(
        return_value={"agent": "comage", "candidate": "run-001", "overall": "FAIL", "scenario_rate": 0.5}
    )
    with mock.patch.dict(sys.modules, {"quality_gate": fake_quality_gate}):
        try:
            mlops.stage_evaluate(config, store)
            raised = False
        except SystemExit:
            raised = True
    assert raised, "expected SystemExit when the gate result is not PASS"

    result = store.get_json("mlops/evaluations/comage/run-001/gate_result.json")
    assert result["overall"] == "FAIL"
    assert result["adapter_s3_prefix"] == "mlops/models/comage/run-001/adapter"
    assert result["classification"] == "C2"


def test_stage_evaluate_does_not_raise_when_the_gate_passes() -> None:
    config = _config()
    store = _FakeStore()
    store.put_json(
        "mlops/models/comage/run-001/train_manifest.json",
        {"classification": "C1", "adapter_s3_prefix": "mlops/models/comage/run-001/adapter"},
    )

    fake_quality_gate = mock.MagicMock()
    fake_quality_gate.QualityGateError = RuntimeError
    fake_quality_gate.evaluate = mock.MagicMock(
        return_value={"agent": "comage", "candidate": "run-001", "overall": "PASS", "scenario_rate": 0.9}
    )
    with mock.patch.dict(sys.modules, {"quality_gate": fake_quality_gate}):
        mlops.stage_evaluate(config, store)  # must not raise

    result = store.get_json("mlops/evaluations/comage/run-001/gate_result.json")
    assert result["overall"] == "PASS"


# --- push-registry --------------------------------------------------------


def test_stage_push_registry_refuses_without_a_passing_gate_result() -> None:
    config = _config()
    store = _FakeStore()
    store.put_json("mlops/evaluations/comage/run-001/gate_result.json", {"overall": "FAIL"})
    try:
        mlops.stage_push_registry(config, store)
        raised = False
    except SystemExit:
        raised = True
    assert raised, "expected SystemExit (no bypass, ADR-0302 point 5) when the gate result is not PASS"


def test_stage_push_registry_refuses_with_no_gate_result_at_all() -> None:
    config = _config()
    store = _FakeStore()
    try:
        mlops.stage_push_registry(config, store)
        raised = False
    except SystemExit:
        raised = True
    assert raised, "expected SystemExit when no gate_result.json exists yet"


def test_stage_push_registry_registers_the_adapter_via_the_model_registry_api() -> None:
    config = _config()
    store = _FakeStore()
    store.put_json("mlops/evaluations/comage/run-001/gate_result.json", {"overall": "PASS"})
    store.put_json(
        "mlops/models/comage/run-001/train_manifest.json",
        {
            "classification": "C2",
            "base_model": "tiny-test-model",
            "lora_r": 8,
            "adapter_s3_prefix": "mlops/models/comage/run-001/adapter",
        },
    )

    def _fake_post(url, json=None, timeout=None):
        resp = mock.MagicMock()
        resp.raise_for_status = mock.MagicMock()
        if url.endswith("/registered_models"):
            resp.json.return_value = {"id": "rm-1"}
        elif url.endswith("/versions"):
            resp.json.return_value = {"id": "mv-1"}
        else:
            resp.json.return_value = {"id": "ma-1"}
        return resp

    session = mock.MagicMock()
    session.post = mock.MagicMock(side_effect=_fake_post)
    with mock.patch.object(mlops, "_registry_session", return_value=session):
        mlops.stage_push_registry(config, store)

    mock_post = session.post
    assert mock_post.call_count == 3
    registration = store.get_json("mlops/registrations/comage/run-001/registration.json")
    assert registration["registered_model_id"] == "rm-1"
    assert registration["model_version_id"] == "mv-1"
    assert registration["artifact_uri"] == "s3://test-bucket/mlops/models/comage/run-001/adapter"
    assert registration["classification"] == "C2"


def test_model_registry_base_url_uses_the_real_namespace_env_not_a_hardcoded_one() -> None:
    config = _config(model_registry_url=None, model_registry_namespace="rhoai-model-registries")
    url = mlops._model_registry_base_url(config)
    assert "rhoai-model-registries" in url
    assert "zuno-ai-build" not in url


def test_model_registry_base_url_honors_an_explicit_override() -> None:
    config = _config(model_registry_url="http://custom-registry:9090/")
    assert mlops._model_registry_base_url(config) == "http://custom-registry:9090"


# --- WP-087 / ADR-0526 --------------------------------------------------


def test_registry_session_sends_a_bearer_token_and_trusts_the_service_ca() -> None:
    """WP-34's three bare requests.post calls carried neither, which cannot
    work against an HTTPS authenticated registry."""
    with tempfile.TemporaryDirectory() as tmp:
        token = pathlib.Path(tmp) / "token"
        token.write_text("tok-abc\n")
        ca = pathlib.Path(tmp) / "service-ca.crt"
        ca.write_text("-----BEGIN CERTIFICATE-----")
        config = _config(model_registry_token_path=str(token), model_registry_ca_bundle=str(ca))
        session = mlops._registry_session(config)
    assert session.headers["Authorization"] == "Bearer tok-abc"
    assert session.verify == str(ca)


def test_registry_base_url_is_https_and_built_from_values_not_hardcoded() -> None:
    """The WP-34 default named modelregistry-sample:8080 over plain HTTP -
    a Service that exists nowhere."""
    url = mlops._model_registry_base_url(_config())
    assert url == "https://zuno.rhoai-model-registries.svc.cluster.local:8443"
    assert "modelregistry-sample" not in url
    custom = mlops._model_registry_base_url(
        _config(model_registry_service="mr", model_registry_port=9999, model_registry_scheme="http")
    )
    assert custom == "http://mr.rhoai-model-registries.svc.cluster.local:9999"


def test_push_registry_registers_the_merged_checkpoint_uri_when_a_merge_ran() -> None:
    """ADR-0526 acceptance: the registered version's artifact URI must
    point at the MERGED checkpoint, not the adapter."""
    config = _config(merged_model_s3uri="s3://models-bucket/models/qwen3.5-9b-wesh")
    store = _FakeStore()
    store.put_json("mlops/evaluations/comage/run-001/gate_result.json", {"overall": "PASS"})
    store.put_json(
        "mlops/models/comage/run-001/train_manifest.json",
        {"classification": "C1", "base_model": "b", "lora_r": 8,
         "adapter_s3_prefix": "mlops/models/comage/run-001/adapter"},
    )
    store.put_json(
        "mlops/models/comage/run-001/merge_manifest.json",
        {"merged_model_uri": "s3://models-bucket/models/qwen3.5-9b-wesh"},
    )
    session = mock.MagicMock()
    session.post.return_value = mock.MagicMock(**{"json.return_value": {"id": "x"}})
    with mock.patch.object(mlops, "_registry_session", return_value=session):
        mlops.stage_push_registry(config, store)
    registration = store.get_json("mlops/registrations/comage/run-001/registration.json")
    assert registration["artifact_uri"] == "s3://models-bucket/models/qwen3.5-9b-wesh"


def test_merge_export_refuses_a_non_empty_destination_without_an_explicit_override() -> None:
    """That prefix is what a running KServe storage-initializer reads -
    overwriting it silently would swap a serving model's weights."""
    config = _config(merged_model_s3uri="s3://models-bucket/models/qwen3.5-9b-wesh")
    store = _FakeStore()
    store.put_json("mlops/models/comage/run-001/train_manifest.json",
                   {"classification": "C1", "adapter_s3_prefix": "mlops/models/comage/run-001/adapter"})
    store.put_bytes("models/qwen3.5-9b-wesh/config.json", b"{}", bucket="models-bucket")

    raised = ""
    try:
        mlops.stage_merge_export(config, store)
    except SystemExit as exc:
        raised = str(exc)
    assert "already holds" in raised, f"expected a refusal, got {raised!r}"
    assert "MLOPS_MERGED_OVERWRITE" in raised


def test_merge_export_requires_a_train_manifest_first() -> None:
    config = _config(merged_model_s3uri="s3://models-bucket/models/qwen3.5-9b-wesh")
    raised = False
    try:
        mlops.stage_merge_export(config, _FakeStore())
    except SystemExit:
        raised = True
    assert raised


def test_cross_region_client_does_not_inherit_a_region_pinned_endpoint() -> None:
    """The failure this guards against is silent at every layer except AWS.

    S3_ENDPOINT here is region-pinned (https://s3.<region>.amazonaws.com),
    so a cross-bucket call that overrides region_name but inherits that
    endpoint builds a client aimed at one region while dialling another's
    host. Nothing raises locally - AWS answers PermanentRedirect at request
    time, which is how it reached a live pipeline run.
    """
    built = []

    class _Rec(mlops.ArtifactStore):
        def _client_for(self, region, endpoint):
            built.append((region, endpoint))
            return f"client:{region}:{endpoint}"

    store = _Rec.__new__(_Rec)
    store._bucket = "corpus"
    store._path_style = False
    store._access_key = store._secret_key = None
    store._default_region = "us-east-1"
    store._default_endpoint = "https://s3.us-east-1.amazonaws.com"
    store._clients = {}
    store._client = "default-client"

    # same bucket -> the default client, untouched
    assert store._resolve(None, None, None)[1] == "default-client"
    assert store._resolve("corpus", None, None)[1] == "default-client"

    # other bucket + explicit region, no endpoint -> region only, endpoint None
    bucket, _ = store._resolve("models", "eu-west-2", None)
    assert bucket == "models"
    assert built[-1] == ("eu-west-2", None), built[-1]

    # an EXPLICIT endpoint is still honoured (non-AWS S3 stays reachable)
    store._resolve("models", "eu-west-2", "https://minio.local")
    assert built[-1] == ("eu-west-2", "https://minio.local")

    # no region override -> the defaults, endpoint included
    store._resolve("models", None, None)
    assert built[-1] == ("us-east-1", "https://s3.us-east-1.amazonaws.com")


def test_split_s3_uri_rejects_malformed_input() -> None:
    assert mlops._split_s3_uri("s3://b/p/q") == ("b", "p/q")
    assert mlops._split_s3_uri("s3://b/p/") == ("b", "p")
    for bad in ("https://b/p", "s3://b", "s3://", "b/p"):
        raised = False
        try:
            mlops._split_s3_uri(bad)
        except SystemExit:
            raised = True
        assert raised, f"{bad!r} should have been rejected"


def test_stages_and_stage_functions_stay_in_sync() -> None:
    """A stage in one and not the other is an argparse rejection at run
    time - and WP-087 names only STAGE_FUNCTIONS."""
    assert set(mlops.STAGES) == set(mlops.STAGE_FUNCTIONS)
    assert "merge-export" in mlops.STAGES
    # merge-export must sit between train-lora and evaluate: push-registry
    # registers the merged artifact's URI.
    order = list(mlops.STAGES)
    assert order.index("train-lora") < order.index("merge-export") < order.index("evaluate")


def test_extract_answer_drops_the_reasoning_block_and_a_restarted_turn() -> None:
    """Regression from the first end-to-end run (wesh-20260827-220749).

    A Qwen3 chat template opens the assistant turn INSIDE a <think>
    block, and generate() stopped on the base checkpoint's
    <|endoftext|> rather than the template's <|im_end|> - so all 79
    scored samples were reasoning + answer + a fabricated second turn.
    Scoring that text put ADR-0526 decision 8's rule-3 opening rate at
    31.6% when the real answers were at 44.3%: the contamination
    under-reported the very failure the rule exists to catch.
    """
    raw = (
        "Le sang, faut reflechir a deux trucs.\n</think>\n\n"
        "Wesh mon reuf, en vrai y a pas de backup.\n"
        "assistant\n<think>\n\n</think>\n\nEt une deuxieme reponse."
    )
    assert mlops._extract_answer(raw) == "Wesh mon reuf, en vrai y a pas de backup."
    # No reasoning block at all: the whole decode is the answer.
    assert mlops._extract_answer("  Wesh, direct.  ") == "Wesh, direct."
    # Reasoning only, never closed - nothing is silently invented.
    assert mlops._extract_answer("<think>je reflechis") == "<think>je reflechis"


def test_chat_stop_ids_prefer_the_templates_end_of_turn_over_tokenizer_eos() -> None:
    """<|im_end|> is what actually terminates an assistant turn; a base
    checkpoint's eos is <|endoftext|>. Both must be passed, or generation
    runs past the answer into a hallucinated next turn."""

    class _Tok:
        unk_token_id = 0
        eos_token_id = 151643  # <|endoftext|>

        def convert_tokens_to_ids(self, token):
            return {"<|im_end|>": 151645, "<|endoftext|>": 151643}.get(token, 0)

    assert mlops._chat_stop_token_ids(_Tok()) == [151645, 151643]

    class _NoChatTok:
        unk_token_id = 0
        eos_token_id = 7

        def convert_tokens_to_ids(self, token):
            return 0  # every chat token maps to unk

    # Falls back to the tokenizer's own eos rather than passing unk as a
    # stop id, which would truncate at the first unknown token.
    assert mlops._chat_stop_token_ids(_NoChatTok()) == [7]


def test_parse_tool_calls_reads_the_qwen_XML_block_not_json() -> None:
    """Qwen3.5 emits tool calls as XML (hence --tool-call-parser=qwen3_xml),
    NOT as JSON. A JSON-shaped parser finds nothing on every real decode,
    so the tool half would report 0 calls for a healthy model exactly as
    loudly as for the broken one - the metric added to catch a silent
    regression, itself silently wrong. Verified against the staged
    checkpoint's own chat_template.jinja."""
    decoded = (
        "Je prepare le visuel.\n\n<tool_call>\n<function=generate_image>\n"
        "<parameter=prompt>\nune equipe commerciale qui fete une signature\n</parameter>\n"
        "</function>\n</tool_call>"
    )
    calls = mlops._parse_tool_calls(decoded)
    assert len(calls) == 1
    assert calls[0]["name"] == "generate_image"
    assert json.loads(calls[0]["arguments"]) == {
        "prompt": "une equipe commerciale qui fete une signature"
    }
    # The prose beside the call is what the narration detector reads.
    assert "tool_call" not in mlops._strip_tool_calls(decoded)


def test_parse_tool_calls_keeps_multiline_parameter_values() -> None:
    """A mermaid source spans many lines; a line-oriented parser would keep
    only the first and score a correct call as bad arguments."""
    decoded = (
        "<tool_call>\n<function=generate_diagram>\n<parameter=mermaid_source>\n"
        "graph TD\n    A[Lead] --> B[Qualification]\n    B --> C[Signature]\n"
        "</parameter>\n</function>\n</tool_call>"
    )
    args = json.loads(mlops._parse_tool_calls(decoded)[0]["arguments"])
    assert "graph TD" in args["mermaid_source"]
    assert "C[Signature]" in args["mermaid_source"]


def test_a_truncated_tool_call_is_recorded_not_swallowed() -> None:
    """Real truncation cuts the closing tags off with everything else.
    Reporting 'no call' there blames the model for a harness limit - the
    exact wrong conclusion drawn about the base model while establishing
    the phase 1 baseline, before it was re-measured with a larger budget."""
    unterminated = mlops._parse_tool_calls(
        "<tool_call>\n<function=generate_diagram>\n<parameter=mermaid_source>\ngraph TD\n    A[Lead"
    )
    assert len(unterminated) == 1
    assert unterminated[0]["name"] == "generate_diagram"
    # A block with no function at all is a broken call, not an abstention.
    empty = mlops._parse_tool_calls("<tool_call>\nrien d'exploitable\n</tool_call>")
    assert len(empty) == 1 and empty[0]["name"] == ""


def test_no_tool_call_block_yields_no_calls() -> None:
    assert mlops._parse_tool_calls("generate_image c'est le bail.") == []


def test_load_tool_probes_returns_none_when_the_agent_has_no_probe_set() -> None:
    """None must stay a no-op: a grounding-domain run has no probe set, and
    turning that into a failure would break every non-style pipeline."""
    assert mlops._load_tool_probes(_config()) is None


def test_load_tool_probes_reads_the_real_shipped_fixture() -> None:
    """Guards the contract between the fixture and the loader - the file is
    consumed from inside the image, where a shape change fails a live run
    rather than a test."""
    repo = pathlib.Path(__file__).resolve().parents[3]
    doc = mlops._load_tool_probes(_config(evaluations_dir=str(repo / "evaluations")))
    assert doc is not None
    assert doc["task"] == "check-deal-status"
    assert {s["function"]["name"] for s in doc["tool_schemas"]} == {"generate_image", "generate_diagram"}
    assert any(p["expects_tool"] for p in doc["probes"])
    assert any(not p["expects_tool"] for p in doc["probes"])


def test_task_system_prompt_is_the_body_not_the_frontmatter() -> None:
    """The probe must run under the same system message agent-runtime
    sends. Without one the variant still calls tools correctly, so a probe
    set that dropped it would score green and measure nothing."""
    repo = pathlib.Path(__file__).resolve().parents[3]
    body = mlops._task_system_prompt(_config(agents_dir=str(repo / "agents")), "check-deal-status")
    assert body and "okf_version" not in body


# ---------------------------------------------------------------------------
# WP-087: reproducible training
# ---------------------------------------------------------------------------


class _FakeTorch:
    """Only the surface _enable_deterministic_training touches."""

    class backends:
        class cudnn:
            deterministic = False
            benchmark = True

    def __init__(self):
        self.deterministic_calls = []

    def use_deterministic_algorithms(self, flag):
        self.deterministic_calls.append(flag)


def test_cublas_workspace_is_configured_at_import_time():
    # Not merely "some value": the wrong value makes torch raise at the
    # first matmul instead of running nondeterministically, so the exact
    # string is the contract.
    assert os.environ["CUBLAS_WORKSPACE_CONFIG"] == ":4096:8", os.environ.get("CUBLAS_WORKSPACE_CONFIG")


class _FakeTransformers:
    """transformers is never installed for this suite - only set_seed is
    needed, and only to observe that it is called."""

    def __init__(self):
        self.seeds = []

    def set_seed(self, seed):
        self.seeds.append(seed)


def _run_determinism(config):
    torch = _FakeTorch()
    torch.backends.cudnn.deterministic = False
    torch.backends.cudnn.benchmark = True
    transformers = _FakeTransformers()
    with mock.patch.dict(sys.modules, {"transformers": transformers}):
        mlops._enable_deterministic_training(torch, config)
    return torch, transformers


def test_deterministic_training_pins_every_source_of_run_to_run_drift():
    torch, transformers = _run_determinism(_config())

    # The RNG seed is the part the first attempt at this MISSED: without
    # it the CUDA flags are set, the log says determinism is on, and the
    # adapter still differs between two runs because get_peft_model drew
    # lora_A's init from an unseeded RNG.
    assert transformers.seeds == [42], transformers.seeds
    # warn_only would defeat the purpose: the run would look reproducible
    # and would not be.
    assert torch.deterministic_calls == [True], torch.deterministic_calls
    assert torch.backends.cudnn.deterministic is True
    assert torch.backends.cudnn.benchmark is False


def test_the_rng_is_seeded_before_anything_can_consume_randomness():
    # An ordering regression is invisible to any behavioural test here -
    # _run_lora_training imports torch/peft, which this suite never has.
    # It is not hypothetical: seeding after get_peft_model is exactly the
    # bug that made two "deterministic" runs produce different adapters.
    src = (pathlib.Path(__file__).resolve().parent.parent / "src" / "mlops.py").read_text()
    seeded = src.index("_enable_deterministic_training(torch, config)")
    lora_init = src.index("model = get_peft_model(model, lora_config)")
    trainer = src.index("trainer = Trainer(")
    assert seeded < lora_init, "the RNG is seeded after LoRA initialisation - adapters will differ between runs"
    assert lora_init < trainer, "unexpected ordering: LoRA init should precede Trainer construction"


def test_determinism_can_be_disabled_but_only_explicitly():
    config = _config()
    object.__setattr__(config, "deterministic", False)
    torch, transformers = _run_determinism(config)

    assert torch.deterministic_calls == [], torch.deterministic_calls
    assert transformers.seeds == [], transformers.seeds


def test_the_seed_reaches_training_arguments_explicitly():
    # Asserted against the source rather than a call, because
    # _run_lora_training imports torch/peft/transformers and this suite
    # deliberately never installs them. The regression it guards is real
    # and invisible otherwise: TrainingArguments' own default is ALSO 42,
    # so dropping `seed=config.seed` leaves every test and every run
    # green while making MLOPS_SEED dead config.
    src = (pathlib.Path(__file__).resolve().parent.parent / "src" / "mlops.py").read_text()
    assert "seed=config.seed," in src, "TrainingArguments no longer passes the configured seed"
    assert _config().seed == 42


TESTS = [
    # WP-087 / ADR-0526
    test_cublas_workspace_is_configured_at_import_time,
    test_deterministic_training_pins_every_source_of_run_to_run_drift,
    test_the_rng_is_seeded_before_anything_can_consume_randomness,
    test_determinism_can_be_disabled_but_only_explicitly,
    test_the_seed_reaches_training_arguments_explicitly,
    test_parse_tool_calls_reads_the_qwen_XML_block_not_json,
    test_parse_tool_calls_keeps_multiline_parameter_values,
    test_a_truncated_tool_call_is_recorded_not_swallowed,
    test_no_tool_call_block_yields_no_calls,
    test_load_tool_probes_returns_none_when_the_agent_has_no_probe_set,
    test_load_tool_probes_reads_the_real_shipped_fixture,
    test_task_system_prompt_is_the_body_not_the_frontmatter,
    test_extract_answer_drops_the_reasoning_block_and_a_restarted_turn,
    test_chat_stop_ids_prefer_the_templates_end_of_turn_over_tokenizer_eos,
    test_registry_session_sends_a_bearer_token_and_trusts_the_service_ca,
    test_registry_base_url_is_https_and_built_from_values_not_hardcoded,
    test_push_registry_registers_the_merged_checkpoint_uri_when_a_merge_ran,
    test_merge_export_refuses_a_non_empty_destination_without_an_explicit_override,
    test_merge_export_requires_a_train_manifest_first,
    test_cross_region_client_does_not_inherit_a_region_pinned_endpoint,
    test_split_s3_uri_rejects_malformed_input,
    test_stages_and_stage_functions_stay_in_sync,
    test_escalate_never_downgrades,
    test_escalate_upgrades_when_candidate_is_higher,
    test_escalate_unknown_candidate_defaults_to_c1_weight,
    test_env_list_parses_comma_separated_values,
    test_env_list_defaults_to_empty_when_unset,
    test_load_config_reads_the_real_process_environment,
    test_load_scenario_seed_texts_filters_to_chat_shaped_scenarios,
    test_load_scenario_seed_texts_missing_file_returns_empty_not_an_error,
    test_stage_prepare_dataset_escalates_classification_and_writes_manifest,
    test_stage_train_lora_requires_a_dataset_manifest_first,
    test_stage_train_lora_uploads_adapter_and_writes_train_manifest,
    test_stage_evaluate_requires_a_train_manifest_first,
    test_stage_evaluate_writes_gate_result_and_raises_on_a_failing_gate,
    test_stage_evaluate_does_not_raise_when_the_gate_passes,
    test_stage_push_registry_refuses_without_a_passing_gate_result,
    test_stage_push_registry_refuses_with_no_gate_result_at_all,
    test_stage_push_registry_registers_the_adapter_via_the_model_registry_api,
    test_model_registry_base_url_uses_the_real_namespace_env_not_a_hardcoded_one,
    test_model_registry_base_url_honors_an_explicit_override,
]


def main() -> int:
    failed = 0
    for test in TESTS:
        try:
            test()
            print(f"PASS {test.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
