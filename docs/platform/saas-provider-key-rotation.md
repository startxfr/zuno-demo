# Runbook: rotating a SaaS provider key, and what to do when a SaaS model starts failing

Last reviewed: 2026-11-19

The ai-gateway and Praxis call SaaS model providers directly with one API key per provider. The keys are in Vault, reach
the pods through ExternalSecrets, and are read once, as an environment variable, when the pod starts. A new key in Vault
therefore changes nothing until the Secret is refreshed **and** the pods are replaced. This page is the sequence, the
inventory of keys, and the symptoms that point here.

Written after 2026-11-19, when the Mistral Codestral key expired. The calls fell back to the local gpt-oss model, and
acceptance scenario 21 of the Tekos agent failed.

## When a SaaS model starts failing

The ai-gateway fails over past a provider that errors (ADR-0020), so the user sees an answer from another model, not an
error. The proof is in the traces: search Tempo for the `model_call` spans of the ai-gateway and read `zuno.error`.

| Symptom on the `model_call` span | Meaning | Action |
|---|---|---|
| `Error response 401` with `Your API key expired on <date>` or `invalid x-api-key` | The key is expired, revoked or wrong | Rotate it: the steps below |
| `404` with a model id in the message | The provider retired the model id (Anthropic retired `claude-3-5-sonnet-latest` on 2026-11-17) | Not a key problem. Change the id in Git: `model` in `platform/ai-gateway/provider-routing.yaml` and `saas.<provider>.targetModel` in `gitops/charts/praxis/values.yaml`. The owner picked `claude-sonnet-5-5` for both gateways on 2026-11-19 |
| `429` | The account is out of quota or credit, or the rate limit is reached | Wait for the window, or ask the owner to add credit. A new key does not help. Do not confuse it with a 429 from MaaS on a local model, which is the MaaS token limit and resets with its window |

## The keys

Vault KV mount `zuno`, one path per provider, each holding only the field `api_key`. The seed
(`ansible/roles/vault/tasks/install.yml`) writes a placeholder only where no key exists, and never overwrites a key
that was set another way.

| Provider | Vault path | ai-gateway Secret (`zuno-ai-run`) and variable | Praxis Secret (`zuno-ai-gateways`) and variable | Other readers |
|---|---|---|---|---|
| OpenAI | `zuno/providers/openai` | `llm-provider-openai`, `OPENAI_API_KEY` | none | none |
| Gemini | `zuno/providers/gemini` | `llm-provider-gemini`, `GEMINI_API_KEY` | none | none |
| Anthropic | `zuno/providers/anthropic` | `llm-provider-anthropic`, `ANTHROPIC_API_KEY` | `praxis-anthropic`, `ANTHROPIC_API_KEY` | none |
| Mistral | `zuno/providers/mistral` | `llm-provider-mistral`, `MISTRAL_API_KEY` | none | MaaS ExternalProvider, Secret `llm-provider-mistral-maas` |
| Mistral Codestral | `zuno/providers/mistral-codestral` | `llm-provider-mistral-codestral`, `MISTRAL_CODESTRAL_API_KEY` | `praxis-mistral-codestral`, `MISTRAL_CODESTRAL_API_KEY` | none |
| OVHcloud | `zuno/providers/ovhcloud` | `llm-provider-ovhcloud`, `OVHCLOUD_API_KEY` | none | MaaS ExternalProvider, Secret `llm-provider-ovhcloud-maas` |

Sources: `platform/ai-gateway/externalsecret-*.yaml`, `gitops/charts/ai-gateway/values.yaml` (`providerSecrets`) and its
`templates/deployment.yaml`, `gitops/charts/praxis/templates/externalsecret.yaml` and `values.yaml` (`saas`),
`gitops/charts/models/values.yaml` (the MaaS copies). Codestral has its own account on purpose (ADR-0417), so that its
credit running low is told apart from Mistral's. Praxis reads only the two keys of the SaaS routes it serves.

## Rotate a key

Each step that changes the cluster needs the owner's go. Never put the key on a command line, in a log or in a message.

1. **Write the key (the owner).** `vault kv put zuno/providers/<provider> api_key=...`, typed by the owner so that it
   stays out of shell history and logs. These paths hold only `api_key`, so `put` replaces nothing else.
   Alternative, reported by the cluster session on 2026-11-19: keep `ansible/confidential.yml` as the source. Get the
   new key from the provider console (for Mistral, `console.mistral.ai/api-keys`), set the matching variable with
   `ansible-vault edit ansible/confidential.yml` (`zuno_llm_provider_<provider>_api_key`, for example
   `zuno_llm_provider_mistral_codestral_api_key`), then run `make d0 install vault`, which writes the Vault path. The
   role re-seeds from that file on every run, so a key written only in Vault by hand can be put back to an older value
   by a later run: when you use `vault kv put`, update `confidential.yml` too.
2. **Refresh the ExternalSecrets.** The refresh interval is one hour. Force it with an annotation:

   ```sh
   EPOCH=$(date +%s)
   oc annotate externalsecret llm-provider-<provider> -n zuno-ai-run force-sync=$EPOCH --overwrite
   oc annotate externalsecret praxis-<provider> -n zuno-ai-gateways force-sync=$EPOCH --overwrite   # Anthropic and Codestral only
   oc get externalsecret -n zuno-ai-run llm-provider-<provider>   # STATUS SecretSynced, READY True
   ```

   For the MaaS copies of Mistral and OVHcloud (`llm-provider-<provider>-maas`), annotate the same way in the namespace
   that holds them (see `oc get externalsecret -A | grep maas`).
3. **Replace the pods.** Both gateways read the key into an environment variable at start, so a Secret refresh alone
   does nothing. **Delete the pods; do not use `rollout restart`**, because Argo CD self-heal can revert a restart
   (see [agents release integration](agents-release-integration.md#rolling-a-promotion)).
   - ai-gateway, two replicas: delete one pod, wait until it is `Ready` again, then delete the other. Calls keep being
     served by the other pod.

     ```sh
     oc get pod -n zuno-ai-run -l app.kubernetes.io/name=ai-gateway
     oc delete pod -n zuno-ai-run <pod>      # wait for the new pod to be Ready, then the next one
     ```
   - Praxis, one replica: deleting the pod costs about a minute without the alternative gateway. Pick a moment when
     no Claude Code or alternative-gateway demo is running.

     ```sh
     oc delete pod -n zuno-ai-gateways -l app.kubernetes.io/name=praxis
     ```
4. **Check without printing the key.**
   - The Secret and the pod hold the same value. Compare digests, which print no key:

     ```sh
     oc get secret llm-provider-<provider> -n zuno-ai-run -o jsonpath='{.data.api_key}' | sha256sum
     oc exec -n zuno-ai-run deploy/ai-gateway -c ai-gateway -- sh -c 'printf %s "$MISTRAL_CODESTRAL_API_KEY" | base64 -w0 | sha256sum'
     ```

     The two digests are equal when the pod started after the refresh. Use the variable of the provider from the table
     above, and the same comparison with the `praxis-<provider>` Secret and the Praxis pod.
   - A minimal call that prints only the status code, from inside the ai-gateway pod (a model list call, no tokens
     spent; the image has `python3`):

     ```sh
     oc exec -n zuno-ai-run deploy/ai-gateway -c ai-gateway -- python3 -c 'import os,urllib.request as u,urllib.error as e
     r=u.Request("https://api.mistral.ai/v1/models",headers={"Authorization":"Bearer "+os.environ["MISTRAL_CODESTRAL_API_KEY"]})
     try: print(u.urlopen(r,timeout=15).status)
     except e.HTTPError as x: print(x.code)'
     ```

     `200` means the key works; `401` means it is still the old one or wrong. For Anthropic use
     `https://api.anthropic.com/v1/models` with the headers `x-api-key` and `anthropic-version: 2023-06-01`. The Praxis
     image's tools were not checked: for Praxis, rely on the digest comparison and a real request through it.
5. **Prove it end to end.** `make d2 check agents` (the acceptance gate of ADR-0053); for the Codestral key, scenario 21 of the Tekos agent must pass again. If the gate sits at 15/19 or
   fails a security case after a stresstest, read the note in
   [agents release integration](agents-release-integration.md#rolling-a-promotion) before blaming the key.

## What this runbook does not cover

- Rotating the Keycloak, Vault or persona passwords: [shared-password-rotation.md](shared-password-rotation.md).
- Handing out MaaS API keys to people: [operations.md](operations.md#handing-out-maas-api-keys-what-the-token-limit-does-and-does-not-cover-wp-220).
- Whether a MaaS ExternalProvider needs a pod restart after its Secret changes: not verified here; the
  [external models scenario](../demo/scenarios/rhoai/external-models.md) shows the objects. The calls the ai-gateway
  makes to Mistral and OVHcloud do not go through MaaS.
