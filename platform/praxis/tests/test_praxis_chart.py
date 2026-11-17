"""The Praxis chart (ADR-0619, WP-292): what its rendered configuration says, without the Praxis image or a cluster.

`helm template` renders the chart with the values of the Application manifest and with the defaults; the two
ConfigMaps (praxis.yaml, policy.yaml) and the routing overlay are read as YAML/JSON and checked for the properties the
local rig of 2026-11-17 proved against the real image (docs/roadmap/evidence/wp-292-praxis-chart-2026-11-17.md):

  - the policy is the zuno JWT (https JWKS, audience zuno-admin-api) and refuses an unlisted model;
  - the local models go MaaS first, one path_rewrite per model conditioned on X-Model, then direct KServe on 429/5xx;
  - each router is the last filter of a chain of its own (a router must end its chain);
  - the SaaS chains exist only when saas.enabled, and the policy refuses them for the denied clients;
  - the routing overlay's content digest is the SHA-256 of the canonical form of {candidates, local_site, network};
  - no Deployment without an image digest, and the Deployment is hardened.

Run from the repository root: python3 platform/praxis/tests/test_praxis_chart.py   (needs helm and PyYAML)
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[3]
CHART = ROOT / "gitops" / "charts" / "praxis"
DIGEST = "sha256:" + "a" * 64


def render(*sets):
    cmd = ["helm", "template", "t", str(CHART)]
    for s in sets:
        cmd += ["--set", s]
    out = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True).stdout
    return [d for d in yaml.safe_load_all(out) if d]


def by_kind(docs, kind):
    return [d for d in docs if d["kind"] == kind]


def config(docs):
    cm = next(d for d in docs if d["kind"] == "ConfigMap" and d["metadata"]["name"] == "praxis-config")
    return yaml.safe_load(cm["data"]["praxis.yaml"])


def policy(docs):
    cm = next(d for d in docs if d["kind"] == "ConfigMap" and d["metadata"]["name"] == "praxis-policy")
    return yaml.safe_load(cm["data"]["policy.yaml"])


def chain(cfg, name):
    return next(c for c in cfg["filter_chains"] if c["name"] == name)


def walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk(v)


@unittest.skipUnless(shutil.which("helm"), "helm is not installed")
class Chart(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.local = render("image.digest=" + DIGEST)
        cls.saas = render("image.digest=" + DIGEST, "saas.enabled=true")

    def test_no_image_no_deployment(self):
        # The chart default pins the WP-291 fork build; an empty digest still renders no Deployment.
        self.assertRegex(by_kind(render(), "Deployment")[0]["spec"]["template"]["spec"]["containers"][0]["image"],
                         r"^quay\.io/zuno/praxis-ai@sha256:[0-9a-f]{64}$")
        self.assertEqual(by_kind(render("image.digest="), "Deployment"), [])
        self.assertEqual(len(by_kind(self.local, "Deployment")), 1)
        with self.assertRaises(subprocess.CalledProcessError):
            render("image.digest=latest")

    def test_policy_is_the_zuno_jwt_and_refuses_unlisted_models(self):
        pol = policy(self.local)
        trusted = pol["plugins"][0]["config"]["trusted_issuers"][0]
        self.assertEqual(trusted["issuer"], "https://keycloak.apps.mycluster.example.com/realms/zuno")
        self.assertEqual(trusted["audiences"], ["zuno-admin-api"])
        self.assertTrue(trusted["decoding_key"]["url"].startswith("https://"))
        llm = [r for r in pol["routes"] if "llm" in r]
        self.assertEqual(llm[0]["llm"], ["auto", "qwen3.6-27b-instruct", "gpt-oss-20b", "qwen3.5-9b", "qwen3.5-9b-wesh"])
        self.assertEqual(llm[-1]["llm"], "*")
        self.assertTrue(llm[-1]["authorization"]["pre_invocation"][0].startswith("deny("))
        # Local only: Claude and Codestral are unlisted, so refused.
        self.assertNotIn("claude", json.dumps(pol))
        # The JWKS is read through the Route: its host is the one private address the policy engine may reach.
        policy_filter = chain(config(self.local), "main")["filters"][0]
        self.assertEqual(policy_filter["trusted_private_endpoints"], ["keycloak.apps.mycluster.example.com"])

    def test_saas_models_are_refused_for_the_denied_clients(self):
        route = next(r for r in policy(self.saas)["routes"] if r.get("llm") == ["claude", "codestral-latest"])
        rules = route["authorization"]["pre_invocation"]
        self.assertEqual(rules[0], "require(authenticated)")
        self.assertIn("claim.azp == 'claude-code': deny(", rules[1])

    def test_each_router_ends_a_chain_of_its_own(self):
        for docs, names in ((self.local, ["main", "local"]), (self.saas, ["main", "local", "claude", "codestral"])):
            cfg = config(docs)
            self.assertEqual([c["name"] for c in cfg["filter_chains"]], names)
            self.assertEqual(cfg["listeners"][0]["filter_chains"], names)
            for c in cfg["filter_chains"]:
                routers = [i for i, f in enumerate(c["filters"]) if f["filter"] == "iterative_request_router"]
                self.assertTrue(routers == [] or routers == [len(c["filters"]) - 1], c["name"])
        # The local router is skipped for the SaaS models, and only then.
        self.assertNotIn("conditions", chain(config(self.local), "local")["filters"][0])
        conds = chain(config(self.saas), "local")["filters"][0]["conditions"]
        self.assertEqual({c["unless"]["headers"]["x-model"] for c in conds}, {"claude", "codestral-latest"})

    def test_local_models_go_maas_first_then_direct(self):
        router = chain(config(self.local), "local")["filters"][0]
        self.assertEqual(router["timeout_ms"], 600000)
        maas, direct = router["steps"]
        self.assertEqual((maas["name"], direct["name"]), ("maas", "direct"))
        self.assertEqual(maas["on_result"][0], {"status": [429, 502, 503, 504], "next": "direct"})
        rewrites = [f for f in maas["filters"] if f["filter"] == "path_rewrite"]
        self.assertEqual([r["conditions"][0]["when"]["headers"]["x-model"] for r in rewrites],
                         ["qwen3.6-27b-instruct", "gpt-oss-20b", "qwen3.5-9b", "qwen3.5-9b-wesh"])
        self.assertEqual(rewrites[0]["replace"]["replacement"], "/zuno-ai-run/qwen36-27b-instruct/v1/chat/completions")
        self.assertNotIn("allow_rewrite_override", rewrites[0])
        self.assertTrue(all(r["allow_rewrite_override"] for r in rewrites[1:]))
        token = next(f for f in maas["filters"] if f["filter"] == "credential_inject")["credentials"][0]
        self.assertEqual(token["file"], "/var/run/secrets/maas/token")
        lb = next(f for f in maas["filters"] if f["filter"] == "load_balancer")["clusters"][0]
        self.assertEqual(lb["tls"]["ca"]["ca_path"], "/etc/ssl/openshift-service-ca/service-ca.crt")
        clusters = next(f for f in direct["filters"] if f["filter"] == "load_balancer")["clusters"]
        self.assertEqual([c["name"] for c in clusters],
                         ["direct-qwen36-27b-instruct", "direct-gpt-oss-20b", "direct-qwen35-9b", "direct-qwen35-9b-wesh"])
        self.assertTrue(clusters[0]["endpoints"][0].endswith("-kserve-workload-svc.zuno-ai-run.svc.cluster.local.:8000"))

    def test_the_alias_models_and_the_metrics_port(self):
        cfg = config(self.local)
        main = chain(cfg, "main")["filters"]
        alias = next(f for f in main if f["filter"] == "model_to_provider")["models"][0]
        self.assertEqual((alias["model"], alias["target_model"]), ("auto", "qwen3.6-27b-instruct"))
        listing = next(f for f in main if f["filter"] == "static_response")
        self.assertEqual([m["id"] for m in json.loads(listing["body"])["data"]],
                         ["auto", "qwen3.6-27b-instruct", "gpt-oss-20b", "qwen3.5-9b", "qwen3.5-9b-wesh"])
        self.assertEqual(cfg["admin"], {"address": "127.0.0.1:9901", "metrics_address": "0.0.0.0:9902"})
        self.assertNotIn("telemetry", cfg)
        for f in walk(cfg):
            self.assertNotIn(f.get("filter"), ("token_rate_limit", "token_count"))

    def test_the_overlay_digest_is_the_hash_of_the_canonical_semantic_object(self):
        cm = next(d for d in self.saas if d["kind"] == "ConfigMap" and d["metadata"]["name"] == "praxis-routing")
        env = json.loads(cm["data"]["routing-overlay.json"])
        overlay = env["overlay"]
        semantic = {"candidates": overlay["candidates"], "local_site": overlay["local_site"], "network": overlay["network"]}
        # RFC 8785 for strings, booleans and sorted keys is json.dumps(sort_keys, no whitespace, UTF-8 as is).
        canonical = json.dumps(semantic, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        digest = hashlib.sha256(canonical).hexdigest()
        self.assertEqual(env["content_digest"]["value"], digest)
        self.assertEqual(env["revision"]["value"], digest)
        candidate = overlay["candidates"][0]
        self.assertEqual((candidate["api_format"], candidate["path"]), ("messages", "/v1/messages"))
        self.assertEqual(env["scope"], {"network": "zuno", "gateway": "praxis", "namespace": "zuno-ai-gateways",
                                        "local_site": "zuno"})
        self.assertEqual(by_kind(self.local, "ExternalSecret"), [])
        self.assertEqual({d["spec"]["data"][0]["remoteRef"]["key"] for d in by_kind(self.saas, "ExternalSecret")},
                         {"providers/anthropic", "providers/mistral-codestral"})
        claude = chain(config(self.saas), "claude")["filters"][0]
        translate = next(f for f in claude["steps"][0]["filters"] if f["filter"] == "openai_chat_completions_to_anthropic")
        self.assertTrue(translate["api_translation_enabled"])

    def test_the_two_switches_of_our_build(self):
        docs = render("image.digest=" + DIGEST, "tokenRateLimit.enabled=true", "opentelemetry.enabled=true")
        cfg = config(docs)
        limit = next(f for f in chain(cfg, "main")["filters"] if f["filter"] == "token_rate_limit")
        self.assertEqual(limit["key"], "authenticated_subject")
        self.assertEqual(limit["backend"]["kind"], "redis")
        # The filter takes the whole URL from one variable; the ExternalSecret builds it, the password percent-encoded.
        self.assertEqual(limit["backend"]["url"], "${REDIS_URL}")
        redis = next(d for d in by_kind(docs, "ExternalSecret") if d["metadata"]["name"] == "praxis-redis")
        self.assertEqual(redis["spec"]["target"]["template"]["data"]["REDIS_URL"],
                         "redis://:{{ .password | urlquery }}@zuno-redis-master.zuno-auth.svc:6379")
        self.assertEqual(cfg["telemetry"]["otlp_endpoint"], "http://zuno-otel-collector-collector.zuno-monitoring.svc:4317")
        names = [f["filter"] for f in chain(cfg, "main")["filters"]]
        # Declared before token_count (response hooks run in reverse), and token_count after the translation filters.
        self.assertLess(names.index("token_rate_limit"), names.index("anthropic_messages_to_chat_completions"))
        self.assertLess(names.index("anthropic_messages_to_chat_completions_stream"), names.index("token_count"))
        self.assertEqual({d["spec"]["data"][0]["remoteRef"]["key"] for d in by_kind(docs, "ExternalSecret")},
                         {"redis/session-store"})

    def test_the_deployment_is_hardened_and_mounts_three_config_directories(self):
        dep = by_kind(self.local, "Deployment")[0]
        pod = dep["spec"]["template"]["spec"]
        container = pod["containers"][0]
        self.assertEqual(container["image"], "quay.io/zuno/praxis-ai@" + DIGEST)
        self.assertTrue(container["securityContext"]["readOnlyRootFilesystem"])
        self.assertEqual(container["securityContext"]["capabilities"], {"drop": ["ALL"]})
        self.assertTrue(pod["securityContext"]["runAsNonRoot"])
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertEqual(dep["spec"]["replicas"], 1)
        mounts = {m["name"]: m["mountPath"] for m in container["volumeMounts"]}
        self.assertEqual((mounts["config"], mounts["policy"]), ("/etc/praxis/config", "/etc/praxis/policy"))
        self.assertEqual(len(set(mounts.values())), len(mounts))        # no two volumes share a directory
        token = next(v for v in pod["volumes"] if v["name"] == "maas-sa-token")["projected"]["sources"][0]["serviceAccountToken"]
        self.assertEqual((token["audience"], token["path"]), ("https://kubernetes.default.svc", "token"))
        self.assertEqual(mounts["maas-sa-token"] + "/" + token["path"], "/var/run/secrets/maas/token")
        annotations = dep["spec"]["template"]["metadata"]["annotations"]
        self.assertEqual(annotations["traffic.sidecar.istio.io/excludeOutboundPorts"], "8000")
        self.assertIn("checksum/config", annotations)
        # The probes use the metrics port: `/` on 8080 goes through the policy and answers 401.
        self.assertEqual(container["readinessProbe"]["httpGet"]["port"], "metrics")

    def test_ingress_is_the_clients_on_8080_and_monitoring_on_the_metrics_port(self):
        policy_ = by_kind(self.local, "NetworkPolicy")[0]
        clients, monitoring = policy_["spec"]["ingress"]
        self.assertEqual(clients["ports"][0]["port"], 8080)
        self.assertEqual(monitoring["ports"][0]["port"], 9902)
        peers = clients["from"]
        self.assertEqual(peers[0]["namespaceSelector"]["matchLabels"], {"zuno.io/experience-client": "true"})
        self.assertEqual(peers[1]["podSelector"]["matchLabels"], {"app.kubernetes.io/name": "multiagent"})
        self.assertEqual(len(peers), 2)                                   # no workstation entry until its switch
        with_entry = render("image.digest=" + DIGEST, "networkPolicy.workstationEntry=true")
        entry = by_kind(with_entry, "NetworkPolicy")[0]["spec"]["ingress"][0]["from"][-1]
        self.assertEqual(entry["podSelector"]["matchLabels"], {"gateway.networking.k8s.io/gateway-name": "zuno-agent-gateway"})


if __name__ == "__main__":
    unittest.main()
