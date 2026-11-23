SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help
# A recipe that fails must not leave a half-written target file behind. (SHELLFLAGS stay as they are: -o pipefail would change
# the exit status of every recipe that pipes into head or grep.)
.DELETE_ON_ERROR:

ANSIBLE_PLAYBOOK ?= ansible-playbook
# One inventory per demo cluster: ansible/inventories/<CLUSTER>/ holds its hosts.yml, group_vars (zuno_cluster_name),
# the committed cluster.yml and the gitignored confidential.yml. `make CLUSTER=demo222 d1 check` selects another one;
# resolve_cluster_name.yml refuses to run when the inventory's zuno_cluster_name is not the cluster `oc` points at.
# ZUNO_CLUSTER (the environment name platform/demo/runner.py and readonly.py read) is accepted too, and exported so
# `make demo ...` plays against the same inventory.
CLUSTER ?= $(or $(ZUNO_CLUSTER),demo333)
export ZUNO_CLUSTER := $(CLUSTER)
INVENTORY ?= ansible/inventories/$(CLUSTER)/hosts.yml
EXTRA_VARS ?=

# ADR-0056/ADR-0060/ADR-0421: Day 0 (bare cluster prerequisites plus the
# "always-on infra" core: PostgreSQL, Keycloak, AAP) / Day 1 (remaining
# AI-platform-operator stack) / Day 2 (AI infrastructure + content
# ingestion) / Day 3 (agent test/stresstest/operational actions)
# sequencing. ADR-0421 moved "postgresql"/"keycloak"/"aap"/"aap-config"
# here from Day 1, right after "machines" (their only real prerequisites -
# vault, external-secrets, machines - already precede them in this same
# list), and moved "smtp"/"nfd"/"nvidia-gpu"/"custom-metrics-autoscaler"
# out to Day 1 in exchange (see Day 1 comment below) - this is the
# "always-on infra" split ADR-0418's Context section had deferred to a
# future ADR.
DAY0_COMPONENTS := admin-context argocd namespaces openshift-rbac-groups vault external-secrets cert-manager machines postgresql keycloak aap aap-config world-model-gpu
DAY0_VERBS := check install uninstall reconcile all reinstall

# Day 1 is the remainder of the AI-platform-operator stack (mesh, Kueue,
# OpenShift AI, etc.). The aiagent-operator that used to run last here was
# retired with the zuno agent stack (WP-156). No build/run split beyond ai-gateway (see
# ansible/roles/ai_gateway_build) and supply-chain-signer (ADR-0420/
# WP-068, see ansible/roles/supply_chain_signer_build) - neither has a
# matching run component, both are build-only images. ADR-0421 moved
# "smtp"/"nfd"/"nvidia-gpu"/"custom-metrics-autoscaler" here from Day 0,
# at the head of this list - none of the three GPU-node components need
# anything beyond "machines" (Day 0, unaffected), and "smtp" only needs
# "vault"/"external-secrets" (Day 0). "postgresql"/"keycloak"/"aap"/
# "aap-config" moved the other way, into Day 0 (see above) - "aap"'s only
# remaining Day 1 neighbor prerequisite was Keycloak/openshift-oauth's
# Ingress+CA-trust bootstrap, which "openshift-oauth" (staying here)
# still provides, now sourced from a Day-0-installed Keycloak instead of
# a Day-1 one. "openshift-oauth" sits where "keycloak" used to, right
# before "connectivity-link". "lightspeed" (ADR-0524/WP-085) sits after
# "openshift-ai": the OpenShift Lightspeed
# operator has no dependency beyond OLM, which is exactly why only the
# OPERATOR is here. Its configuration is a separate Day 2 component
# ("lightspeed-config") - an OLSConfig created in Day 1 would reference a
# MaaS model and an MCP endpoint that don't exist until Day 2, and would
# sit Degraded for the whole window while ArgoCD self-healed it back.
# "nfs-provisioner" (ADR-0608/WP-241) needs only OLM and provides the `nfs`
# StorageClass that Day 2's "unifai" uses for its shared volumes.
DAY1_RUN_COMPONENTS := smtp nfd nvidia-gpu custom-metrics-autoscaler nfs-provisioner redis observability service-mesh mesh-monitoring kiali grafana perses mariadb tempo openshift-oauth connectivity-link lws jobset kueue openshift-ai lightspeed rhtas rhtas-config openshift-pipelines
DAY1_BUILD_COMPONENTS := ai-gateway supply-chain-signer aap-execution-environment
DAY1_VERBS := check install build uninstall reconcile all reinstall

# Day 2 is namespace policy overlay, AI infrastructure (llm, models), and
# content ingestion (mcp, agents, mlops) -
# moved here from Day 1 (ADR-0060). "namespaces" is here despite being a
# Day 0 component everywhere else in this Makefile - only its
# quota/network-policy overlay is Day 2 now, see
# ansible/roles/namespaces/README.md (internal task/Application naming
# stays "_d1"/"-d1", an implementation detail, not renamed with the macro
# tier). "build" only knows how to build the named image groups (mcp,
# mlops, trustyai-eval, token-proxy, dify-knowledge - see
# ansible/roles/{mcp,mlops,trustyai_eval,token_proxy,dify_knowledge}_build; the
# "agent" image group was retired with the zuno agent stack, WP-156);
# "agents" no longer deploys anything (UnifAI serves the agents) and stays
# for its "check", the ADR-0053 acceptance gate against UnifAI; "check"/
# "trustyai-config" (ADR-0534/WP-107) sits right after "mlops": it depends
# only on "models" (the zuno-ai-run namespace its LMEvalJob-based health
# check reads) - TrustyAI itself needs no Day 1 operator, it is already
# Managed inside the Day 1 "openshift-ai" component. "lightspeed-config"
# (ADR-0524/WP-085) is deliberately LAST among the deployable components:
# it needs "models" (the MaaS entitlement for its ServiceAccount), "mcp"
# (the /mcp front-door plus the NetworkPolicy admitting
# openshift-lightspeed) and "agents" all already live, plus the Day 1
# "lightspeed" operator installed before any of it.
# "install" operate on the deployable components below. "supply-chain"
# (ADR-0420/WP-070) is check-only - it has no install/build of its own,
# only a signature-verification gate (ansible/roles/supply_chain) - so it
# lives in its own list, same split Day 3 already uses
# (DAY3_CHECK_ONLY_COMPONENTS): "check" accepts it, every mutating verb
# rejects it cleanly instead of dying inside Ansible on a missing
# tasks/install.yml.
# "chaos" (gitops/charts/chaos: cerberus and the krkn Tekton pipelines)
# follows zuno_chaos_enabled like praxis, and installs nothing that runs:
# a run is the Day 3 verb `make d3 chaos infra|platform`.
DAY2_RUN_COMPONENTS := namespaces llm models quay-registry mcp agents mlops trustyai-config mlflow lightspeed-config unifai open-webui openclaw dify kagent world-model praxis chaos demo-guide
DAY2_CHECK_ONLY_COMPONENTS := supply-chain
DAY2_BUILD_COMPONENTS := mcp mlops trustyai-eval token-proxy dify-knowledge world-model praxis
DAY2_VERBS := check install build uninstall reconcile all reinstall
# Day 2 components with a targeted tasks/reconcile.yml. `reconcile` is limited
# to them: a Day 2 reconcile never falls back to re-installing a component.
# models unwedges a model rollout blocked by the GPU quota (ADR-0201
# "Rollout hazard"); local only, no AAP job template.
DAY2_RECONCILE_COMPONENTS := models

# ADR-0057/ADR-0058: Day 3 was originally agent test/stresstest operations
# only; widened 2026-08-24 into the general "operational tasks" tier -
# anything that acts on an already-installed component rather than
# installing/uninstalling it (test, stresstest, backup, restore, check).
# Each verb has its own component list, same split Day 1 already uses for
# "build" vs "check/install/uninstall" (DAY1_BUILD_COMPONENTS vs
# DAY1_RUN_COMPONENTS) - not every Day 3 verb applies to every Day 3
# component. "test"/"stresstest" only ever prove availability (each agent's
# UnifAI bundle, shared platform services' /healthz+/readyz) or run
# the full per-agent test layer; component granularity matches Day 2's
# "agents" (every agent bundle, collectively) plus "platform" for the
# shared services - which agents actually exist is resolved dynamically
# from the admitted agents release (platform/okf/stack-config.generated.yaml,
# derived from platform/okf/agents.lock) at Ansible run time, never a list
# here. "backup"/"restore" are per-component pgBackRest-style operations
# (see ansible/roles/postgresql/tasks/{backup,restore}.yml); "check" spans
# every Day 3 component regardless of verb group, delegating to the same
# availability test for agents/platform and to each component's own
# precheck.yml otherwise (ansible/playbooks/day3_check.yml).
DAY3_TEST_COMPONENTS := agents platform
DAY3_BACKUP_COMPONENTS := postgresql unifai quay-registry
# Components that support "check" but neither test/stresstest nor
# backup/restore - they contribute only their own precheck.yml
# (ansible/playbooks/day3_check.yml). ADR-0524/WP-085: "lightspeed" and
# "lightspeed-config" are two entries, not one, because the component is split
# across day tiers - checking only the operator would report healthy while the
# OLSConfig operand is absent, and vice versa.
# "operators" (2026-11-04): report-only audit of the OLM operators that can be
# updated (platform/olm/audit_operator_updates.py, ansible/roles/operators).
# "recovery" (2026-11-12): read-only, is the cluster back after a node drain or a reboot
# (platform/recovery/check_recovery.py, ansible/roles/recovery).
# "chaos" (Day 2 component): `make d3 check chaos` is the same read-only check as `make d2 check chaos` (the
# Application, the Tasks and Pipelines, the cerberus signal), next to `recovery`, before and after a chaos run.
DAY3_CHECK_ONLY_COMPONENTS := lightspeed lightspeed-config trustyai-config mlflow operators drift recovery chaos
# WP-126: triggering a real pipeline run spends real, costly compute (a GPU
# burst-node scale-up, several minutes of training) against an
# already-installed platform - the same tier as backup/restore, never
# a side effect of `make d2 install mlops`. Its own component list, same
# per-verb split as backup/restore.
DAY3_RUN_COMPONENTS := mlops
# ADR-0549/WP-134: cutting a named, signed, in-cluster release is an
# on-demand operator action against an already-installed platform, spends
# real build+sign compute - same tier as run, its own component list.
DAY3_RELEASE_COMPONENTS := supply-chain
# ADR-0580/WP-160: admitting a zuno-demo-agents release verifies it offline
# (keyless signatures + attestations, platform/okf/sigstore/) and checks this
# platform can serve it; RELEASE=vX.Y.Z UPDATE_LOCK=1 also moves
# platform/okf/agents.lock. Needs cosign and oras, no cluster. It replaced
# `make d3 sign agents` and the OKF Vault Transit chain (ADR-0578, WP-165).
DAY3_ADMIT_COMPONENTS := agents
# Day 2 component chaos: `make d3 chaos infra TIER=<tier>` or `make d3 chaos platform TARGETS=<ids>` injects failures
# into the live cluster (krkn through Tekton, ansible/roles/chaos) - the kind is the word after the verb, confirmed by
# CHAOS_CONFIRM=<kind>. Routed to the AAP workflow zuno-day3-chaos-<kind>-workflow (its approval node is the pause), or
# run locally as pre-check, TTY pause, run, post-check.
DAY3_CHAOS_KINDS := infra platform
DAY3_COMPONENTS := $(sort $(DAY3_TEST_COMPONENTS) $(DAY3_BACKUP_COMPONENTS) $(DAY3_CHECK_ONLY_COMPONENTS) $(DAY3_RUN_COMPONENTS) $(DAY3_RELEASE_COMPONENTS) $(DAY3_ADMIT_COMPONENTS))
DAY3_VERBS := test stresstest stresstest-collect backup restore check admit run release scenario-failover-node chaos

# ADR-0616/WP-270: the presenter lifecycle of every catalogue demo, as
# `make demo <verb> [arguments]`. The verbs run locally, never through AAP:
# platform/demo/presenter.py runs each action or step file of the demo
# (ansible/demos/<id>/) through ansible/playbooks/demo_run.yml, then prints
# the page section. golden-path and browser are the catalogue-wide checks
# of ADR-0605/ADR-0606, dispatched here exactly as before. The WP-136
# webinar verbs and their playbooks were retired by WP-272 (ADR-0616
# clause 13); the GPU failover drill stays `make d3 scenario-failover-node`.
# ADR-0617/WP-284: record and gif take a demo's 5-minute version in a browser
# and cut its GIF under ~/.cache/zuno/demo/recordings/, locally, never AAP;
# scout (ADR-0618/WP-286) is the sign-in-only run a take needs first.
DEMO_VERBS := list use status check install start stop uninstall step freeze rehearse scout record gif guide golden-path browser

# ADR-0418 clause 6/WP-097: shared shell functions every day1/day2/day3
# recipe below sources to route mutating/read verbs through AAP when
# zuno_make_aap_mode allows it, instead of always running ansible-playbook
# from this shell. Defined once here (not duplicated per recipe) since
# each DAYn_RECIPE's `define...endef` body runs as its own separate shell
# invocation - shell functions can't be shared any other way in this file.
# resolve_aap_mode() reads this cluster's confidential.yml directly
# (ansible/inventories/$(CLUSTER)/confidential.yml, else the deprecated
# ansible/confidential.yml - the same order load_confidential_vars.yml uses): the Makefile
# has no other way to reach an Ansible-sourced variable before deciding
# whether to invoke ansible-playbook at all, and this decision must happen
# here, in the shell, before any playbook runs. When the file is
# ansible-vault encrypted it is read through `ansible-vault view` (the
# passphrase comes from ansible.cfg vault_password_file); a failed decrypt is
# reported as "undecryptable" and aap_route refuses to run, because guessing
# local or remote would be worse than stopping. Never fails even if the
# file, PyYAML, or the key itself is missing - defaults to "auto"
# throughout, matching this repo's existing "graceful if confidential.yml
# is absent" convention (see ansible/roles/aap/tasks/install.yml).
# aap_route() returns: 0 on a successful AAP launch (caller is done); 99
# as a NOT-ROUTED sentinel (local mode, or auto mode with AAP unreachable)
# meaning the caller must fall back to its own local ansible-playbook call;
# any other nonzero code is a REAL launch/job failure in remote mode (or
# auto mode once AAP was confirmed reachable) that the caller must
# propagate as-is, never silently falling back to local for it - remote
# mode's whole point is "no silent fallback" (ADR-0418 clause 6).
# WP-099 (live bug, found running `make d1 check kiali` for real): passing
# each piece as its own `-e "key=value"` argument breaks the moment
# extra_vars_json contains a space (every `{"k": "v"}` this repo builds
# does, right after the colon) - ansible-playbook's `key=value` extra-vars
# parser splits on WHITESPACE, not just `=`, so `-e "aap_launch_extra_vars=
# {\"target_component\": \"kiali\"}"` silently truncated the value at the
# first space, leaving `aap_launch.yml`'s `from_json` filter a truncated,
# invalid JSON fragment to parse. Fixed by passing ONE combined `-e` whose
# value is itself a full JSON object (ansible detects a value starting
# with `{` and parses the WHOLE argument via its YAML/JSON loader instead
# of the whitespace-splitting key=value loader) - internal spaces are then
# irrelevant, and `aap_launch_extra_vars` arrives as an already-native
# dict rather than a string needing `from_json`.
define AAP_ROUTING_SHELL_FUNCS
resolve_aap_mode() { \
  local mode="auto" conf="" f; \
  for f in ansible/inventories/$(CLUSTER)/confidential.yml ansible/confidential.yml; do \
    if [[ -f "$$f" ]]; then conf="$$f"; break; fi; \
  done; \
  if [[ -n "$$conf" ]]; then \
    local val txt; \
    if head -n 1 "$$conf" | grep -q '^[$$]ANSIBLE_VAULT;'; then \
      txt="$$(ansible-vault view "$$conf" 2>/dev/null)" || { echo "Cannot decrypt $$conf (ansible.cfg vault_password_file, see ansible/README.md)" >&2; echo "undecryptable"; return 0; }; \
    else \
      txt="$$(cat "$$conf")"; \
    fi; \
    val="$$(printf '%s' "$$txt" | python3 -c "import sys, yaml; d=yaml.safe_load(sys.stdin) or {}; print(d.get('zuno_make_aap_mode','auto'))" 2>/dev/null)"; \
    [[ -n "$$val" ]] && mode="$$val"; \
  fi; \
  case "$$mode" in \
    local|remote|auto) ;; \
    *) echo "Invalid zuno_make_aap_mode in $$conf: '$$mode' (expected local|remote|auto)" >&2; exit 2 ;; \
  esac; \
  echo "$$mode"; \
}; \
aap_route() { \
  local kind="$$1" template="$$2" extra_vars_json="$$3" mode; \
  mode="$$(resolve_aap_mode)"; \
  case "$$mode" in \
    local) return 99 ;; \
    auto) \
      if ! $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/aap_probe.yml $(EXTRA_VARS) >/dev/null 2>&1; then \
        echo "AAP not reachable - falling back to local execution (zuno_make_aap_mode=auto)" >&2; \
        return 99; \
      fi ;; \
    remote) ;; \
    *) echo "zuno_make_aap_mode could not be resolved ('$$mode'): refusing to guess between local and remote" >&2; return 2 ;; \
  esac; \
  $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/aap_launch.yml -e "{\"aap_launch_type\": \"$$kind\", \"aap_launch_template\": \"$$template\", \"aap_launch_extra_vars\": $$extra_vars_json}" $(EXTRA_VARS); \
};
endef

DAY_VERB := $(word 2,$(MAKECMDGOALS))
DAY_COMPONENT := $(word 3,$(MAKECMDGOALS))

.PHONY: help credentials-check day0 d0 day1 d1 day2 d2 day3 d3 demo new-mcp-server completion _complete-top _complete-verbs _complete-components $(DEMO_VERBS) $(DAY0_VERBS) $(DAY0_COMPONENTS) $(DAY1_VERBS) $(DAY1_RUN_COMPONENTS) $(DAY1_BUILD_COMPONENTS) $(DAY2_VERBS) $(DAY2_RUN_COMPONENTS) $(DAY2_CHECK_ONLY_COMPONENTS) $(DAY2_BUILD_COMPONENTS) $(DAY3_VERBS) $(DAY3_COMPONENTS) $(DAY3_TEST_COMPONENTS) $(DAY3_BACKUP_COMPONENTS) $(DAY3_CHECK_ONLY_COMPONENTS) $(DAY3_CHAOS_KINDS)

help:
	@printf '%s\n' \
	  'Zuno Demo operator interface' \
	  '' \
	  '  Required once, before any target below:' \
	  '    oc login https://api.mycluster.com:6443 --token=<cluster-admin token>' \
	  '  Ansible reuses that kubeconfig (K8S_AUTH_KUBECONFIG) for every cluster' \
	  '  call - no separate credentials to export.' \
	  '  This is the only manual input for the entire install - everything else' \
	  '  (Keycloak, Vault, PostgreSQL, OpenShift AI, MLOps...) is automated.' \
	  '  CLUSTER=<name> (default demo333) selects ansible/inventories/<name>/; a play' \
	  '  refuses when that inventory names another cluster than the one logged in.' \
	  '' \
	  '  make day0|d0 check [component]      Check one/all Day 0 components'"'"' install state' \
	  '  make day0|d0 install [component]    Install one/all Day 0 prerequisites' \
	  '  make day0|d0 uninstall [component]  Uninstall one/all Day 0 prerequisites (reverse order)' \
	  '  make day0|d0 reconcile [component]  Diagnose blocked resources and apply known remediations automatically' \
	  '  make day0|d0 all [component]        check + install, in order' \
	  '  make day0|d0 reinstall [component]  Uninstall then install one/all Day 0 prerequisites' \
	  '' \
	  '  make day1|d1 check [component]      Check one/all Day 1 components'"'"' install state' \
	  '  make day1|d1 build [component]      Build one/all Day 1 component images' \
	  '  make day1|d1 install [component]    Install/deploy one/all Day 1 components (no component: builds first)' \
	  '  make day1|d1 uninstall [component]  Uninstall one/all Day 1 components (reverse order)' \
	  '  make day1|d1 reconcile [component]  Diagnose blocked resources and apply known remediations automatically' \
	  '  make day1|d1 all [component]        check + build + install, whichever apply to the component' \
	  '  make day1|d1 reinstall [component]  Uninstall then install one/all Day 1 components' \
	  '' \
	  '  make day2|d2 check [component]      Check one/all Day 2 components'"'"' install state (agents runs the ADR-0053 acceptance gate)' \
	  '  make day2|d2 build [component]      Build one/all Day 2 component images' \
	  '  make day2|d2 install [component]    Install/deploy one/all Day 2 components (no component: builds first)' \
	  '  make day2|d2 uninstall [component]  Uninstall one/all Day 2 components (reverse order)' \
	  '  make day2|d2 reconcile models       Unwedge a model rollout blocked by the GPU quota (asks before the model goes down)' \
	  '  make day2|d2 all [component]        check + build + install, whichever apply to the component' \
	  '  make day2|d2 reinstall [component]  Uninstall then install one/all Day 2 components' \
	  '' \
	  '  make day3|d3 test [component]        Check availability only (ADR-0057)' \
	  '  make day3|d3 stresstest [component]  Run every existing test layer per agent, plus a bulk-interaction load pass (ADR-0058)' \
	  '  make day3|d3 admit [component]       Verify and validate the zuno-demo-agents release in platform/okf/agents.lock (ADR-0580)' \
	  '  make day3|d3 run [component]         Trigger one real pipeline run (WP-126) - AGENT=<agent> overrides the default (comage)' \
	  '  make day3|d3 chaos infra|platform    Inject failures with krkn: TIER=pods|hog|latency (infra) or TARGETS=<ids> (platform), CHAOS_CONFIRM=<kind>' \
	  '' \
	  '  make demo list                       The catalogue demos, their step counts (5/15), show-ready, last rehearsal (ADR-0616)' \
	  '  make demo use <id> 5|15              Select a demo and its version (a workshop takes no version)' \
	  '  make demo status|check|install|start|stop|uninstall [<id>]   Run the demo'"'"'s action file, then print its page section' \
	  '  make demo step next|<N>              Run the step'"'"'s reads, then print its Do, Say and You should see' \
	  '  make demo freeze on|off              Freeze marker on this workstation: install, uninstall, rehearse, scout and record refuse' \
	  '  make demo rehearse <id> 5|15         The whole sequence without pauses, with a report' \
	  '  make demo scout <id>                 Sign in as the walkthrough'"'"'s persona and open its menus: no prompt, nothing created (ADR-0618)' \
	  '  make demo record <id>                Record the 5-minute version in a browser, then cut its GIF in ~/.cache (ADR-0617)' \
	  '  make demo record <id> [render]       A terminal demo: capture and check as text; render films it after the transcript is read (ADR-0618)' \
	  '  make demo gif <id>                   Cut the newest recording again, offline; never copies into the repository' \
	  '  make demo guide [check]              Write the demo guide page (console links, every demo) for the demo-guide chart (WP-330)' \
	  '  make demo golden-path|browser        The catalogue-wide checks (ADR-0605, ADR-0606); ONLY=a,b limits them' \
	  '' \
	  '  make new-mcp-server NAME=<name> [DESCRIPTION="..."]   Scaffold a new MCP server (ADR-0119)' \
	  '' \
	  '  make completion   Print a bash completion function for day0|d0/day1|d1/day2|d2/day3|d3/demo' \
	  '                    (first-word and verb-then-component aware). Wire it up once, in ~/.bashrc:' \
	  '                    eval "$$(cd $(CURDIR) && make completion)"' \
	  '' \
	  'Day 0 components: $(DAY0_COMPONENTS)' \
	  'Day 1 components (check/install): $(DAY1_RUN_COMPONENTS)' \
	  'Day 1 components (build):         $(DAY1_BUILD_COMPONENTS)' \
	  'Day 2 components (check/install): $(DAY2_RUN_COMPONENTS)' \
	  'Day 2 components (check only):    $(DAY2_CHECK_ONLY_COMPONENTS)' \
	  'Day 2 components (build):         $(DAY2_BUILD_COMPONENTS)' \
	  'Day 3 components (test/stresstest/check): $(DAY3_TEST_COMPONENTS)' \
	  '  make day3|d3 stresstest PROFILE=smoke|standard|aggressive|soak   Profile-driven stress campaign (ADR-0624); stresstest-collect RUN=<id> reads one' \
	  'Day 3 components (backup/restore):        $(DAY3_BACKUP_COMPONENTS)' \
	  'Day 3 components (check only):            $(DAY3_CHECK_ONLY_COMPONENTS)' \
	  'Day 3 components (release):               $(DAY3_RELEASE_COMPONENTS)' \
	  'Day 3 report format: text (default) | json | csv - set via REPORT_FORMAT=<fmt> or EXTRA_VARS="-e report_format=<fmt>"'

# ADR-0119: scaffold a new MCP server from the confluence-shaped template
# instead of hand-copying an existing server directory-by-directory.
new-mcp-server:
	@if [[ -z "$(NAME)" ]]; then \
	  echo "Usage: make new-mcp-server NAME=<name> [DESCRIPTION=\"...\"]" >&2; \
	  exit 2; \
	fi
	python3 platform/scaffolding/new_mcp_server.py "$(NAME)" $(if $(DESCRIPTION),--description "$(DESCRIPTION)")

# ADR-0616/WP-270: `make demo <verb> [arguments]`. Every word after `demo`
# goes to platform/demo/presenter.py (DEMO_ARGS), which checks the
# kubeconfig itself, only for the verbs that touch the cluster - so `demo`
# no longer depends on credentials-check, except for golden-path and
# browser, which keep their exact behaviour: credentials-check, then
# ansible/playbooks/demo_golden_path.yml or demo_browser.yml with
# $(EXTRA_VARS) (ONLY= passes through the environment).
DEMO_ARGS := $(if $(filter demo,$(firstword $(MAKECMDGOALS))),$(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS)))

define DEMO_RECIPE
@verb="$(DAY_VERB)"; \
case "$$verb" in \
  golden-path|browser) $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) "ansible/playbooks/demo_$${verb//-/_}.yml" $(EXTRA_VARS) ;; \
  *) ZUNO_REPO_ROOT="$(CURDIR)" python3 platform/demo/presenter.py $(DEMO_ARGS) ;; \
esac
endef

demo: $(if $(filter golden-path browser,$(DAY_VERB)),credentials-check)
	$(DEMO_RECIPE)

# Bash completion for `make <top-level target>`, then
# `make day0|d0/day1|d1/day2|d2/day3|d3 <verb> [component]` and
# `make demo <verb>`. _complete-top/_complete-verbs/_complete-components
# are the single source of truth for what to offer at each position -
# they just echo the same DAY*_VERBS/DEMO_VERBS/DAY*_RUN_COMPONENTS/
# DAY*_BUILD_COMPONENTS variables the real recipes validate against
# above, so the completion list can never drift from what a command
# would actually accept. `completion` emits a bash function that shells
# out to them live (one `make` call per Tab press), rather than baking
# a static word list into the emitted script.
_complete-top:
	@echo "day0 d0 day1 d1 day2 d2 day3 d3 demo new-mcp-server completion help"

_complete-verbs:
	@case "$(DAY)" in \
	  0) echo "$(DAY0_VERBS)" ;; \
	  1) echo "$(DAY1_VERBS)" ;; \
	  2) echo "$(DAY2_VERBS)" ;; \
	  3) echo "$(DAY3_VERBS)" ;; \
	  demo) echo "$(DEMO_VERBS)" ;; \
	esac

_complete-components:
	@case "$(DAY)" in \
	  0) echo "$(DAY0_COMPONENTS) all" ;; \
	  1) case "$(VERB)" in \
	       build) echo "$(DAY1_BUILD_COMPONENTS) all" ;; \
	       *) echo "$(DAY1_RUN_COMPONENTS) all" ;; \
	     esac ;; \
	  2) case "$(VERB)" in \
	       build) echo "$(DAY2_BUILD_COMPONENTS) all" ;; \
	       check) echo "$(DAY2_RUN_COMPONENTS) $(DAY2_CHECK_ONLY_COMPONENTS) all" ;; \
	       reconcile) echo "$(DAY2_RECONCILE_COMPONENTS) all" ;; \
	       *) echo "$(DAY2_RUN_COMPONENTS) all" ;; \
	     esac ;; \
	  3) case "$(VERB)" in \
	       backup|restore) echo "$(DAY3_BACKUP_COMPONENTS) all" ;; \
	       admit) echo "$(DAY3_ADMIT_COMPONENTS) all" ;; \
	       run) echo "$(DAY3_RUN_COMPONENTS) all" ;; \
	       release) echo "$(DAY3_RELEASE_COMPONENTS) all" ;; \
	       chaos) echo "$(DAY3_CHAOS_KINDS)" ;; \
	       *) echo "$(DAY3_COMPONENTS) all" ;; \
	     esac ;; \
	  demo) python3 platform/demo/presenter.py --complete "$(VERB)" $(ARG) ;; \
	esac

completion:
	@printf '%s\n' \
	  '_zuno_demo_make_complete() {' \
	  '  local cur day verb' \
	  '  cur=$$2' \
	  '  if [[ $$COMP_CWORD -eq 1 ]]; then' \
	  '    COMPREPLY=( $$(compgen -W "$$(command make -s -C "$(CURDIR)" _complete-top 2>/dev/null)" -- "$$cur") )' \
	  '    return 0' \
	  '  fi' \
	  '  case "$${COMP_WORDS[1]}" in' \
	  '    day0|d0) day=0 ;;' \
	  '    day1|d1) day=1 ;;' \
	  '    day2|d2) day=2 ;;' \
	  '    day3|d3) day=3 ;;' \
	  '    demo) day=demo ;;' \
	  '    *) return 0 ;;' \
	  '  esac' \
	  '  if [[ $$COMP_CWORD -eq 2 ]]; then' \
	  '    COMPREPLY=( $$(compgen -W "$$(command make -s -C "$(CURDIR)" _complete-verbs DAY=$$day 2>/dev/null)" -- "$$cur") )' \
	  '  elif [[ $$COMP_CWORD -eq 3 ]]; then' \
	  '    verb=$${COMP_WORDS[2]}' \
	  '    COMPREPLY=( $$(compgen -W "$$(command make -s -C "$(CURDIR)" _complete-components DAY=$$day VERB=$$verb 2>/dev/null)" -- "$$cur") )' \
	  '  elif [[ $$COMP_CWORD -eq 4 && $$day == demo ]]; then' \
	  '    verb=$${COMP_WORDS[2]}' \
	  '    COMPREPLY=( $$(compgen -W "$$(command make -s -C "$(CURDIR)" _complete-components DAY=demo VERB=$$verb ARG=$${COMP_WORDS[3]} 2>/dev/null)" -- "$$cur") )' \
	  '  fi' \
	  '}' \
	  'complete -F _zuno_demo_make_complete make'

credentials-check:
	@kubeconfig="$${KUBECONFIG:-$$HOME/.kube/config}"; \
	if [[ ! -f "$$kubeconfig" ]]; then \
	  echo "No kubeconfig found at $$kubeconfig - run 'oc login <cluster-api-url>' first (see 'make help')." >&2; \
	  exit 2; \
	fi

# day0/d0 share this exact recipe (both names dispatch identically - word 2
# of MAKECMDGOALS is the verb regardless of which name was invoked as word 1).
define DAY0_RECIPE
@verb="$(DAY_VERB)"; \
component="$${TARGET_COMPONENT:-$(DAY_COMPONENT)}"; \
if [[ -z "$$verb" ]]; then \
  printf '%s\n' \
    'Zuno Demo - Day 0 (cluster prerequisites)' \
    '' \
    'Usage: make day0|d0 <verb> [component]' \
    '' \
    '  check       Check one/all Day 0 components'"'"' install state' \
    '  install     Install one/all Day 0 prerequisites' \
    '  uninstall   Uninstall one/all Day 0 prerequisites (reverse order)' \
    '  reconcile   Diagnose blocked resources and apply known remediations automatically' \
    '  all         check + install, in order' \
    '  reinstall   Uninstall then install one/all Day 0 prerequisites' \
    '' \
    'Components (optional, default: all):' \
    '  $(DAY0_COMPONENTS)' \
    '' \
    'Example: make d0 install argocd'; \
  exit 0; \
fi; \
if [[ -z "$$component" ]]; then component=all; fi; \
case " $(DAY0_VERBS) " in *" $$verb "*) ;; *) echo "Unsupported day0 verb: '$$verb' (expected one of: $(DAY0_VERBS))" >&2; exit 2;; esac; \
case " $(DAY0_COMPONENTS) all " in *" $$component "*) ;; *) echo "Unsupported day0 component: '$$component' (expected one of: $(DAY0_COMPONENTS) or all)" >&2; exit 2;; esac; \
run_one() { $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) "ansible/playbooks/day0_$$1.yml" -e "target_component=$$component" $(EXTRA_VARS); }; \
case "$$verb" in \
  check) run_one check ;; \
  install) run_one install ;; \
  uninstall) run_one uninstall ;; \
  reconcile) run_one reconcile ;; \
  all) run_one check && run_one install ;; \
  reinstall) run_one uninstall && run_one install ;; \
esac
endef

day0: $(if $(DAY_VERB),credentials-check)
	$(DAY0_RECIPE)

d0: $(if $(DAY_VERB),credentials-check)
	$(DAY0_RECIPE)

# day1/d1 share this exact recipe. Structurally generic over its
# component-list variables - see day2's identical recipe below, which
# this one is the template for.
define DAY1_RECIPE
@verb="$(DAY_VERB)"; \
component="$${TARGET_COMPONENT:-$(DAY_COMPONENT)}"; \
if [[ -z "$$verb" ]]; then \
  printf '%s\n' \
    'Zuno Demo - Day 1 (AI-platform-operator stack)' \
    '' \
    'Usage: make day1|d1 <verb> [component]' \
    '' \
    '  check       Check one/all Day 1 components'"'"' install state' \
    '  build       Build one/all Day 1 component images' \
    '  install     Install/deploy one/all Day 1 components (no component: builds first)' \
    '  uninstall   Uninstall one/all Day 1 components (reverse order)' \
    '  reconcile   Diagnose blocked resources and apply known remediations automatically' \
    '  all         check + build + install, whichever apply to the component' \
    '  reinstall   Uninstall then install one/all Day 1 components' \
    '' \
    'Components (check/install/uninstall/all; optional, default: all):' \
    '  $(DAY1_RUN_COMPONENTS)' \
    '' \
    'Components (build; optional, default: all):' \
    '  $(DAY1_BUILD_COMPONENTS)' \
    '' \
    'Example: make d1 install kiali'; \
  exit 0; \
fi; \
if [[ -z "$$component" ]]; then component=all; fi; \
case " $(DAY1_VERBS) " in *" $$verb "*) ;; *) echo "Unsupported day1 verb: '$$verb' (expected one of: $(DAY1_VERBS))" >&2; exit 2;; esac; \
$(AAP_ROUTING_SHELL_FUNCS) \
route_or_local() { \
  local verb="$$1" workflow="$$2" ev; \
  ev="{\"target_component\": \"$$component\"}"; \
  if [[ "$$component" == "all" && -n "$$workflow" ]]; then aap_route workflow "$$workflow" "{}"; \
  else aap_route job "zuno-day1-$$verb" "$$ev"; fi; \
  local rc=$$?; \
  if [[ $$rc -eq 99 ]]; then $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/day1_$${verb}.yml -e "target_component=$$component" $(EXTRA_VARS); else return $$rc; fi; \
}; \
run_check() { route_or_local check zuno-day1-check-workflow; }; \
run_build() { route_or_local build zuno-day1-build-workflow; }; \
run_install() { route_or_local install zuno-day1-install-workflow; }; \
run_reconcile() { route_or_local reconcile zuno-day1-reconcile-workflow; }; \
run_uninstall() { $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/day1_uninstall.yml -e "target_component=$$component" $(EXTRA_VARS); }; \
case "$$verb" in \
  check) \
    case " $(DAY1_RUN_COMPONENTS) all " in *" $$component "*) ;; *) echo "Unsupported day1 check component: '$$component' (expected one of: $(DAY1_RUN_COMPONENTS) or all)" >&2; exit 2;; esac; \
    run_check ;; \
  build) \
    case " $(DAY1_BUILD_COMPONENTS) all " in *" $$component "*) ;; *) echo "Unsupported day1 build component: '$$component' (expected one of: $(DAY1_BUILD_COMPONENTS) or all)" >&2; exit 2;; esac; \
    run_build ;; \
  install) \
    case " $(DAY1_RUN_COMPONENTS) all " in *" $$component "*) ;; *) echo "Unsupported day1 install component: '$$component' (expected one of: $(DAY1_RUN_COMPONENTS) or all)" >&2; exit 2;; esac; \
    if [[ "$$component" == "all" ]]; then run_build || exit $$?; fi; \
    run_install ;; \
  uninstall) \
    case " $(DAY1_RUN_COMPONENTS) all " in *" $$component "*) ;; *) echo "Unsupported day1 uninstall component: '$$component' (expected one of: $(DAY1_RUN_COMPONENTS) or all)" >&2; exit 2;; esac; \
    run_uninstall ;; \
  reconcile) \
    case " $(DAY1_RUN_COMPONENTS) all " in *" $$component "*) ;; *) echo "Unsupported day1 reconcile component: '$$component' (expected one of: $(DAY1_RUN_COMPONENTS) or all)" >&2; exit 2;; esac; \
    run_reconcile ;; \
  all) \
    is_run=0; is_build=0; \
    case " $(DAY1_RUN_COMPONENTS) all " in *" $$component "*) is_run=1;; esac; \
    case " $(DAY1_BUILD_COMPONENTS) all " in *" $$component "*) is_build=1;; esac; \
    if [[ $$is_run -eq 0 && $$is_build -eq 0 ]]; then \
      echo "Unsupported day1 component: '$$component' (expected one of: $(DAY1_RUN_COMPONENTS) $(DAY1_BUILD_COMPONENTS) or all)" >&2; exit 2; \
    fi; \
    if [[ $$is_run -eq 1 ]]; then run_check || exit $$?; fi; \
    if [[ $$is_build -eq 1 ]]; then run_build || exit $$?; fi; \
    if [[ $$is_run -eq 1 ]]; then run_install || exit $$?; fi ;; \
  reinstall) \
    case " $(DAY1_RUN_COMPONENTS) all " in *" $$component "*) ;; *) echo "Unsupported day1 reinstall component: '$$component' (expected one of: $(DAY1_RUN_COMPONENTS) or all)" >&2; exit 2;; esac; \
    run_uninstall && run_install ;; \
esac
endef

day1: $(if $(DAY_VERB),credentials-check)
	$(DAY1_RECIPE)

d1: $(if $(DAY_VERB),credentials-check)
	$(DAY1_RECIPE)

# day2/d2 share this exact recipe - structurally identical to Day 1's
# (ADR-0060: Day 2 is now a full install tier, not the old test tier;
# see day3 below for where the old day2 test/stresstest moved).
define DAY2_RECIPE
@verb="$(DAY_VERB)"; \
component="$${TARGET_COMPONENT:-$(DAY_COMPONENT)}"; \
if [[ -z "$$verb" ]]; then \
  printf '%s\n' \
    'Zuno Demo - Day 2 (AI infrastructure + content ingestion)' \
    '' \
    'Usage: make day2|d2 <verb> [component]' \
    '' \
    '  check       Check one/all Day 2 components'"'"' install state (agents runs the ADR-0053 acceptance gate)' \
    '  build       Build one/all Day 2 component images' \
    '  install     Install/deploy one/all Day 2 components (no component: builds first)' \
    '  uninstall   Uninstall one/all Day 2 components (reverse order)' \
    '  reconcile   Unwedge a model rollout blocked by the GPU quota; asks before the model goes down' \
    '              (EXTRA_VARS="-e confirm=yes" skips the question, "-e model=<name>" limits it to one model)' \
    '  all         check + build + install, whichever apply to the component' \
    '  reinstall   Uninstall then install one/all Day 2 components' \
    '' \
    'Components (check/install/uninstall/all; optional, default: all):' \
    '  $(DAY2_RUN_COMPONENTS)' \
    '' \
    'Components (reconcile):' \
    '  $(DAY2_RECONCILE_COMPONENTS)' \
    '' \
    'Components (check only):' \
    '  $(DAY2_CHECK_ONLY_COMPONENTS)' \
    '' \
    'Components (build; optional, default: all):' \
    '  $(DAY2_BUILD_COMPONENTS)' \
    '' \
    'Example: make d2 install mcp'; \
  exit 0; \
fi; \
if [[ -z "$$component" ]]; then component=all; fi; \
case " $(DAY2_VERBS) " in *" $$verb "*) ;; *) echo "Unsupported day2 verb: '$$verb' (expected one of: $(DAY2_VERBS))" >&2; exit 2;; esac; \
$(AAP_ROUTING_SHELL_FUNCS) \
route_or_local() { \
  local verb="$$1" workflow="$$2" ev; \
  ev="{\"target_component\": \"$$component\"}"; \
  if [[ "$$component" == "all" && -n "$$workflow" ]]; then aap_route workflow "$$workflow" "{}"; \
  else aap_route job "zuno-day2-$$verb" "$$ev"; fi; \
  local rc=$$?; \
  if [[ $$rc -eq 99 ]]; then $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/day2_$${verb}.yml -e "target_component=$$component" $(EXTRA_VARS); else return $$rc; fi; \
}; \
run_check() { route_or_local check zuno-day2-check-workflow; }; \
run_build() { route_or_local build zuno-day2-build-workflow; }; \
run_install() { route_or_local install zuno-day2-install-workflow; }; \
run_uninstall() { $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/day2_uninstall.yml -e "target_component=$$component" $(EXTRA_VARS); }; \
run_reconcile() { $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/day2_reconcile.yml -e "target_component=$$component" $(EXTRA_VARS); }; \
case "$$verb" in \
  check) \
    case " $(DAY2_RUN_COMPONENTS) $(DAY2_CHECK_ONLY_COMPONENTS) all " in *" $$component "*) ;; *) echo "Unsupported day2 check component: '$$component' (expected one of: $(DAY2_RUN_COMPONENTS) $(DAY2_CHECK_ONLY_COMPONENTS) or all)" >&2; exit 2;; esac; \
    run_check ;; \
  build) \
    case " $(DAY2_BUILD_COMPONENTS) all " in *" $$component "*) ;; *) echo "Unsupported day2 build component: '$$component' (expected one of: $(DAY2_BUILD_COMPONENTS) or all)" >&2; exit 2;; esac; \
    run_build ;; \
  install) \
    case " $(DAY2_RUN_COMPONENTS) all " in *" $$component "*) ;; *) echo "Unsupported day2 install component: '$$component' (expected one of: $(DAY2_RUN_COMPONENTS) or all)" >&2; exit 2;; esac; \
    if [[ "$$component" == "all" ]]; then run_build || exit $$?; fi; \
    run_install ;; \
  uninstall) \
    case " $(DAY2_RUN_COMPONENTS) all " in *" $$component "*) ;; *) echo "Unsupported day2 uninstall component: '$$component' (expected one of: $(DAY2_RUN_COMPONENTS) or all)" >&2; exit 2;; esac; \
    run_uninstall ;; \
  reconcile) \
    case " $(DAY2_RECONCILE_COMPONENTS) all " in *" $$component "*) ;; *) echo "Unsupported day2 reconcile component: '$$component' (expected one of: $(DAY2_RECONCILE_COMPONENTS) or all)" >&2; exit 2;; esac; \
    run_reconcile ;; \
  all) \
    is_run=0; is_build=0; \
    case " $(DAY2_RUN_COMPONENTS) all " in *" $$component "*) is_run=1;; esac; \
    case " $(DAY2_BUILD_COMPONENTS) all " in *" $$component "*) is_build=1;; esac; \
    if [[ $$is_run -eq 0 && $$is_build -eq 0 ]]; then \
      echo "Unsupported day2 component: '$$component' (expected one of: $(DAY2_RUN_COMPONENTS) $(DAY2_BUILD_COMPONENTS) or all)" >&2; exit 2; \
    fi; \
    if [[ $$is_run -eq 1 ]]; then run_check || exit $$?; fi; \
    if [[ $$is_build -eq 1 ]]; then run_build || exit $$?; fi; \
    if [[ $$is_run -eq 1 ]]; then run_install || exit $$?; fi ;; \
  reinstall) \
    case " $(DAY2_RUN_COMPONENTS) all " in *" $$component "*) ;; *) echo "Unsupported day2 reinstall component: '$$component' (expected one of: $(DAY2_RUN_COMPONENTS) or all)" >&2; exit 2;; esac; \
    run_uninstall && run_install ;; \
esac
endef

day2: $(if $(DAY_VERB),credentials-check)
	$(DAY2_RECIPE)

d2: $(if $(DAY_VERB),credentials-check)
	$(DAY2_RECIPE)

# day3/d3 share this exact recipe. Only two components (agents, platform)
# and two verbs (test, stresstest) - no build/run split like Day 1/Day 2,
# since neither verb ever changes cluster state, only observes/exercises
# it. report_format defaults to "text" (ADR-0057 decision 4: raw table
# always printed; json/csv are additional artifacts, selected via
# REPORT_FORMAT= or EXTRA_VARS="-e report_format=..."). "stresstest"
# additionally reads BULK (ADR-0058 decision 3): unset in an interactive
# shell prompts for a bulk-interaction count with a default of 10; unset
# in a non-interactive shell (stdin not a TTY, e.g. CI) silently defaults
# to 10 without prompting, so this recipe never blocks a non-interactive
# caller. BULK=0 runs the functional layers only, no bulk-interaction
# load pass.
define DAY3_RECIPE
@verb="$(DAY_VERB)"; \
component="$${TARGET_COMPONENT:-$(DAY_COMPONENT)}"; \
if [[ -z "$$verb" ]]; then \
  printf '%s\n' \
    'Zuno Demo - Day 3 (operational tasks)' \
    '' \
    'Usage: make day3|d3 <verb> [component]' \
    '' \
    '  test         Check availability only (agent bundles served by UnifAI, shared platform services'"'"' /healthz+/readyz)' \
    '  stresstest   Run every existing test layer per agent, plus an optional bulk-interaction load pass (ADR-0058)' \
    '               PROFILE=<name> runs a profile-driven campaign instead (evaluations/stress/profile_<name>.yaml, ADR-0624)' \
    '  stresstest-collect   Read the rows of a stress campaign launched with PROFILE= (RUN=<run id>, default the newest)' \
    '  backup       Trigger an on-demand backup' \
    '  restore      Restore from the most recent backup (fails if none exists)' \
    '  check        Check state/health across every Day 3 component (test for agents/platform, precheck otherwise)' \
    '  admit        Verify offline and validate the zuno-demo-agents release pinned in platform/okf/agents.lock (ADR-0580)' \
    '               RELEASE=vX.Y.Z admits that release instead; UPDATE_LOCK=1 also writes it to the lock' \
    '  run          Trigger one real KFP pipeline run (WP-126) - spends real GPU burst-node compute' \
    '  release      Cut a named, signed, in-cluster release (ADR-0549/WP-134) - builds+RHTAS-signs' \
    '               every component at TAG, records it in pinned-releases.yaml. Never touches' \
    '               values.yaml/targetRevision - main keeps deploying `:latest` unchanged.' \
    '  scenario-failover-node   Live GPU-node failover drill (WP-105/ADR-0536): cordon+kill the qwen3.5-9b-wesh' \
    '               pod, verify Comage fails over to qwen3.5-9b (Tekos pinned to ovhcloud-gpt-oss-120b as the' \
    '               decoupling control), pause for human' \
    '               confirmation, then uncordon+reschedule and verify the return to normal. Requires a TTY' \
    '               (refuses to run non-interactively) and mutates live shared GPU infra - coordinate with' \
    '               any other session on this cluster first.' \
    '  chaos        Inject failures into the live cluster with krkn (Day 2 component chaos): pre-check, approval,' \
    '               ONE PipelineRun in zuno-chaos, post-check. The kind is the word after the verb, typed again in' \
    '               CHAOS_CONFIRM: infra TIER=pods|hog|latency, or platform TARGETS=<ids of platform/chaos/targets.yaml>.' \
    '               Routed to the AAP workflow zuno-day3-chaos-<kind>-workflow (approve there); locally, needs a TTY.' \
    '' \
    'Components (test/stresstest/check; optional, default: all):' \
    '  $(DAY3_TEST_COMPONENTS)' \
    '' \
    'Components (backup/restore; optional, default: all):' \
    '  $(DAY3_BACKUP_COMPONENTS)' \
    '' \
    'Components (admit; optional, default: all):' \
    '  $(DAY3_ADMIT_COMPONENTS)' \
    '' \
    'Components (run; optional, default: all):' \
    '  $(DAY3_RUN_COMPONENTS)' \
    '' \
    'Components (release; optional, default: all):' \
    '  $(DAY3_RELEASE_COMPONENTS)' \
    '' \
    'Day 3 check-only components:' \
    '  $(DAY3_CHECK_ONLY_COMPONENTS)' \
    '' \
    'Report format: text (default) | json | csv - REPORT_FORMAT=<fmt> or EXTRA_VARS="-e report_format=<fmt>"' \
    'Bulk interaction count (stresstest only): BULK=<n> (skips the interactive prompt; BULK=0 disables it)' \
    'Remove test-generated conversations after the run (stresstest only): CLEANUP=<0|1> (default: remove; skips the interactive prompt)' \
    'Run agents one at a time instead of in parallel (stresstest only, default: parallel): SEQUENTIAL=1' \
    'Stress campaign (stresstest only, ADR-0624): PROFILE=<smoke|standard|aggressive|soak>, overridden by ITERATIONS=<n> CONCURRENCY=<n> DURATION=<seconds> SHARDS=<n> FAMILIES=<a,b> DRIVERS=<id,id>' \
    'Disruptions of a profile that lists them (aggressive; evaluations/stress/chaos.yaml, ADR-0624): CHAOS_CONFIRM=<the profile name again>, otherwise none is inflicted' \
    'Read a stress campaign (stresstest-collect only): RUN=<run id printed at launch> (default: the newest)' \
    'Agent to train (run only): AGENT=<agent> (default: comage - the only agent with a compiled pipeline version today)' \
    'Release tag (release only, REQUIRED, no default): TAG=<tag> - must already be a real, pushed git tag' \
    '' \
    'Example: make d3 test agents' \
    'Example: make d3 stresstest BULK=25' \
    'Example: make d3 stresstest CLEANUP=0   # keep test conversations for inspection' \
    'Example: make d3 stresstest SEQUENTIAL=1   # one agent at a time, like every run before ADR-0561' \
    'Example: make d3 stresstest PROFILE=smoke   # every driver once, under a token cap' \
    'Example: make d3 stresstest PROFILE=standard CONCURRENCY=4 FAMILIES=tools,models' \
    'Example: make d3 stresstest PROFILE=soak   # async: prints a run id' \
    'Example: make d3 stresstest PROFILE=aggressive CHAOS_CONFIRM=aggressive   # load AND one pod deleted at a time, one provider cut' \
    'Example: make d3 stresstest-collect RUN=soak-20261119-014500' \
    'Example: make d3 backup postgresql' \
    'Example: make d3 restore postgresql' \
    'Example: make d3 admit agents RELEASE=v0.1.1 UPDATE_LOCK=1   # admit a zuno-demo-agents release and pin it (ADR-0580)' \
    'Example: make d3 run mlops   # triggers one real LoRA training run (WP-126) - scales up zuno-gpu-burst-a' \
    'Example: git tag v0.2.0 && git push origin v0.2.0 && make d3 release TAG=v0.2.0   # named in-cluster release (ADR-0549)' \
    'Example: make d3 release TAG=v0.2.0 RENDER_DIGESTS=1   # also writes the ledgered digests into the chart values (ADR-0603 M16; a deployment pin, needs the go)' \
    'Example: make d3 scenario-failover-node   # interactive - pauses for confirmation between cordon+kill and uncordon+restore' \
    'Example: make d3 chaos infra TIER=pods CHAOS_CONFIRM=infra   # one monitoring, router and apiserver pod each' \
    'Example: make d3 chaos platform TARGETS=pod-ai-gateway,pod-mcp-gateway CHAOS_CONFIRM=platform' \
    'Example: make d3 chaos platform TARGETS=provider-cut-mistral CHAOS_CONFIRM=platform   # a provider cut runs alone'; \
  exit 0; \
fi; \
if [[ -z "$$component" ]]; then component=all; fi; \
case " $(DAY3_VERBS) " in *" $$verb "*) ;; *) echo "Unsupported day3 verb: '$$verb' (expected one of: $(DAY3_VERBS))" >&2; exit 2;; esac; \
report_format="$${REPORT_FORMAT:-text}"; \
$(AAP_ROUTING_SHELL_FUNCS) \
case "$$verb" in \
  test) \
    case " $(DAY3_TEST_COMPONENTS) all " in *" $$component "*) ;; *) echo "Unsupported day3 test component: '$$component' (expected one of: $(DAY3_TEST_COMPONENTS) or all)" >&2; exit 2;; esac; \
    aap_route job zuno-day3-test "{\"target_component\": \"$$component\", \"report_format\": \"$$report_format\"}"; rc=$$?; \
    if [[ $$rc -eq 99 ]]; then $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/day3_test.yml -e "target_component=$$component" -e "report_format=$$report_format" $(EXTRA_VARS); else exit $$rc; fi ;; \
  stresstest) \
    case " $(DAY3_TEST_COMPONENTS) all " in *" $$component "*) ;; *) echo "Unsupported day3 stresstest component: '$$component' (expected one of: $(DAY3_TEST_COMPONENTS) or all)" >&2; exit 2;; esac; \
    profile="$${PROFILE:-}"; \
    if [[ -n "$$profile" ]] && ! [[ "$$profile" =~ ^[a-z0-9][a-z0-9-]*$$ ]]; then echo "PROFILE must be a profile name: evaluations/stress/profile_<name>.yaml" >&2; exit 2; fi; \
    for knob in ITERATIONS CONCURRENCY DURATION SHARDS; do \
      val="$${!knob:-}"; \
      if [[ -n "$$val" ]] && ! [[ "$$val" =~ ^[0-9]+$$ ]]; then echo "$$knob must be a number (got '$$val')" >&2; exit 2; fi; \
    done; \
    for knob in FAMILIES DRIVERS; do \
      val="$${!knob:-}"; \
      if [[ -n "$$val" ]] && ! [[ "$$val" =~ ^[a-z0-9,_.-]+$$ ]]; then echo "$$knob must be a comma list of names (got '$$val')" >&2; exit 2; fi; \
    done; \
    if [[ -n "$${CHAOS_CONFIRM:-}" ]] && ! [[ "$${CHAOS_CONFIRM}" =~ ^[a-z0-9-]+$$ ]]; then echo "CHAOS_CONFIRM must be the name of the profile (it is typed twice on purpose)" >&2; exit 2; fi; \
    if [[ -z "$$profile" && -n "$${ITERATIONS:-}$${CONCURRENCY:-}$${DURATION:-}$${SHARDS:-}$${FAMILIES:-}$${DRIVERS:-}$${CHAOS_CONFIRM:-}" ]]; then echo "ITERATIONS, CONCURRENCY, DURATION, SHARDS, FAMILIES, DRIVERS and CHAOS_CONFIRM need PROFILE=<name>" >&2; exit 2; fi; \
    stress_json=""; stress_args=""; \
    if [[ -n "$$profile" ]]; then \
      stress_json=", \"stress_profile\": \"$$profile\""; stress_args="-e stress_profile=$$profile"; \
      if [[ -n "$${ITERATIONS:-}" ]]; then stress_json="$$stress_json, \"stress_iterations\": $$ITERATIONS"; stress_args="$$stress_args -e stress_iterations=$$ITERATIONS"; fi; \
      if [[ -n "$${CONCURRENCY:-}" ]]; then stress_json="$$stress_json, \"stress_concurrency\": $$CONCURRENCY"; stress_args="$$stress_args -e stress_concurrency=$$CONCURRENCY"; fi; \
      if [[ -n "$${DURATION:-}" ]]; then stress_json="$$stress_json, \"stress_duration\": $$DURATION"; stress_args="$$stress_args -e stress_duration=$$DURATION"; fi; \
      if [[ -n "$${SHARDS:-}" ]]; then stress_json="$$stress_json, \"stress_shards\": $$SHARDS"; stress_args="$$stress_args -e stress_shards=$$SHARDS"; fi; \
      if [[ -n "$${FAMILIES:-}" ]]; then stress_json="$$stress_json, \"stress_families\": \"$$FAMILIES\""; stress_args="$$stress_args -e stress_families=$$FAMILIES"; fi; \
      if [[ -n "$${DRIVERS:-}" ]]; then stress_json="$$stress_json, \"stress_drivers\": \"$$DRIVERS\""; stress_args="$$stress_args -e stress_drivers=$$DRIVERS"; fi; \
      if [[ -n "$${CHAOS_CONFIRM:-}" ]]; then stress_json="$$stress_json, \"stress_chaos_confirm\": \"$$CHAOS_CONFIRM\""; stress_args="$$stress_args -e stress_chaos_confirm=$$CHAOS_CONFIRM"; fi; \
    fi; \
    bulk="$${BULK:-}"; \
    if [[ -z "$$bulk" ]]; then \
      if [[ -n "$$profile" ]]; then \
        bulk=0; \
      elif [[ -t 0 ]]; then \
        read -r -p "Bulk interaction count [10]: " bulk; \
        bulk="$${bulk:-10}"; \
      else \
        bulk=10; \
      fi; \
    fi; \
    cleanup="$${CLEANUP:-}"; \
    if [[ -z "$$cleanup" ]]; then \
      if [[ -n "$$profile" ]]; then \
        cleanup=1; \
      elif [[ -t 0 ]]; then \
        read -r -p "Remove test-generated conversations after the run? [Y/n]: " cleanup_answer; \
        case "$$cleanup_answer" in [nN]*) cleanup=0 ;; *) cleanup=1 ;; esac; \
      else \
        cleanup=1; \
      fi; \
    fi; \
    sequential="$${SEQUENTIAL:-0}"; \
    parallel="true"; case "$$sequential" in 1|true|yes) parallel="false" ;; esac; \
    aap_route job zuno-day3-stresstest "{\"target_component\": \"$$component\", \"report_format\": \"$$report_format\", \"bulk_interactions\": $$bulk, \"cleanup_test_data\": $$cleanup, \"day2_stresstest_parallel\": $$parallel$$stress_json}"; rc=$$?; \
    if [[ $$rc -eq 99 ]]; then $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/day3_stresstest.yml -e "target_component=$$component" -e "report_format=$$report_format" -e "bulk_interactions=$$bulk" -e "cleanup_test_data=$$cleanup" -e "day2_stresstest_parallel=$$parallel" $$stress_args $(EXTRA_VARS); else exit $$rc; fi ;; \
  stresstest-collect) \
    run="$${RUN:-}"; \
    if [[ -n "$$run" ]] && ! [[ "$$run" =~ ^[a-z0-9-]+$$ ]]; then echo "RUN must be a run id such as smoke-20261119-014500 (printed when the campaign was launched)" >&2; exit 2; fi; \
    aap_route job zuno-day3-stresstest-collect "{\"stress_run\": \"$$run\", \"report_format\": \"$$report_format\"}"; rc=$$?; \
    if [[ $$rc -eq 99 ]]; then $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/day3_stresstest_collect.yml -e "stress_run=$$run" -e "report_format=$$report_format" $(EXTRA_VARS); else exit $$rc; fi ;; \
  backup) \
    case " $(DAY3_BACKUP_COMPONENTS) all " in *" $$component "*) ;; *) echo "Unsupported day3 backup component: '$$component' (expected one of: $(DAY3_BACKUP_COMPONENTS) or all)" >&2; exit 2;; esac; \
    aap_route job zuno-day3-backup "{\"target_component\": \"$$component\"}"; rc=$$?; \
    if [[ $$rc -eq 99 ]]; then $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/day3_backup.yml -e "target_component=$$component" $(EXTRA_VARS); else exit $$rc; fi ;; \
  restore) \
    case " $(DAY3_BACKUP_COMPONENTS) all " in *" $$component "*) ;; *) echo "Unsupported day3 restore component: '$$component' (expected one of: $(DAY3_BACKUP_COMPONENTS) or all)" >&2; exit 2;; esac; \
    aap_route job zuno-day3-restore "{\"target_component\": \"$$component\"}"; rc=$$?; \
    if [[ $$rc -eq 99 ]]; then $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/day3_restore.yml -e "target_component=$$component" $(EXTRA_VARS); else exit $$rc; fi ;; \
  check) \
    case " $(DAY3_COMPONENTS) all " in *" $$component "*) ;; *) echo "Unsupported day3 check component: '$$component' (expected one of: $(DAY3_COMPONENTS) or all)" >&2; exit 2;; esac; \
    aap_route job zuno-day3-check "{\"target_component\": \"$$component\", \"report_format\": \"$$report_format\"}"; rc=$$?; \
    if [[ $$rc -eq 99 ]]; then $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/day3_check.yml -e "target_component=$$component" -e "report_format=$$report_format" $(EXTRA_VARS); else exit $$rc; fi ;; \
  run) \
    case " $(DAY3_RUN_COMPONENTS) all " in *" $$component "*) ;; *) echo "Unsupported day3 run component: '$$component' (expected one of: $(DAY3_RUN_COMPONENTS) or all)" >&2; exit 2;; esac; \
    agent="$${AGENT:-comage}"; \
    aap_route job zuno-day3-run "{\"target_component\": \"$$component\", \"agent\": \"$$agent\"}"; rc=$$?; \
    if [[ $$rc -eq 99 ]]; then $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/day3_run.yml -e "target_component=$$component" -e "agent=$$agent" $(EXTRA_VARS); else exit $$rc; fi ;; \
  admit) \
    case " $(DAY3_ADMIT_COMPONENTS) all " in *" $$component "*) ;; *) echo "Unsupported day3 admit component: '$$component' (expected one of: $(DAY3_ADMIT_COMPONENTS) or all)" >&2; exit 2;; esac; \
    admit_args=(); \
    if [[ -n "$${RELEASE:-}" ]]; then admit_args+=(--release "$$RELEASE"); fi; \
    case "$${UPDATE_LOCK:-0}" in 1|true|yes) admit_args+=(--update-lock) ;; esac; \
    python3 platform/supply-chain/admit_okf_bundle.py admit "$${admit_args[@]}" || exit $$?; \
    if [[ -n "$${OKF_MIRROR_TO:-}" ]]; then \
      mirror_args=(--to "$$OKF_MIRROR_TO"); \
      case "$${OKF_MIRROR_PLAIN_HTTP:-0}" in 1|true|yes) mirror_args+=(--plain-http) ;; esac; \
      python3 platform/supply-chain/admit_okf_bundle.py mirror "$${mirror_args[@]}" || exit $$?; \
      prune_args=(--mirror "$$OKF_MIRROR_TO" --keep "$${OKF_MIRROR_KEEP:-3}"); \
      case "$${OKF_MIRROR_PLAIN_HTTP:-0}" in 1|true|yes) prune_args+=(--plain-http) ;; esac; \
      case "$${OKF_MIRROR_PRUNE:-0}" in 1|true|yes) prune_args+=(--apply) ;; esac; \
      case "$${OKF_MIRROR_QUAY:-0}" in 1|true|yes) prune_args+=(--quay) ;; esac; \
      python3 platform/supply-chain/admit_okf_bundle.py prune "$${prune_args[@]}"; \
    fi ;; \
  release) \
    case " $(DAY3_RELEASE_COMPONENTS) all " in *" $$component "*) ;; *) echo "Unsupported day3 release component: '$$component' (expected one of: $(DAY3_RELEASE_COMPONENTS) or all)" >&2; exit 2;; esac; \
    if [[ -z "$${TAG:-}" ]]; then echo "day3 release requires TAG=<release_tag>, e.g. TAG=v0.2.0 (must already be a real, pushed git tag)" >&2; exit 2; fi; \
    tag="$$TAG"; \
    aap_route job zuno-day3-release "{\"target_component\": \"$$component\", \"release_tag\": \"$$tag\"}"; rc=$$?; \
    release_ran_locally=0; \
    if [[ $$rc -eq 99 ]]; then $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/day3_release.yml -e "target_component=$$component" -e "release_tag=$$tag" $(EXTRA_VARS) || exit $$?; release_ran_locally=1; elif [[ $$rc -ne 0 ]]; then exit $$rc; fi; \
    case "$${RENDER_DIGESTS:-0}" in 1|true|yes) \
      if [[ $$release_ran_locally -eq 1 ]]; then python3 platform/supply-chain/render_release_digests.py --release "$$tag"; \
      else echo "RENDER_DIGESTS: the release ran in AAP, so its ledger entry is not in this checkout - pull the ledger commit, then run python3 platform/supply-chain/render_release_digests.py --release $$tag"; fi ;; \
    esac ;; \
  scenario-failover-node) \
    if [[ ! -t 0 ]]; then \
      echo "day3 scenario-failover-node requires an interactive terminal - it mutates live shared GPU infra and needs a human to confirm the failover before restoring (ADR-0536). Refusing to run non-interactively." >&2; \
      exit 2; \
    fi; \
    aap_route workflow zuno-day3-scenario-failover-node-workflow "{}"; rc=$$?; \
    if [[ $$rc -eq 99 ]]; then \
      $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/day3_scenario_failover_node_inject.yml $(EXTRA_VARS) || exit $$?; \
      read -r -p "Inject phase complete (see the verdict above). Press Enter to uncordon and restore, or Ctrl-C to abort and leave the node cordoned for inspection: " _scenario_failover_confirm; \
      $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/day3_scenario_failover_node_restore.yml $(EXTRA_VARS); \
    else \
      exit $$rc; \
    fi ;; \
  chaos) \
    case " $(DAY3_CHAOS_KINDS) " in *" $$component "*) ;; *) echo "Usage: make d3 chaos infra TIER=pods|hog|latency CHAOS_CONFIRM=infra, or make d3 chaos platform TARGETS=<id,id> CHAOS_CONFIRM=platform" >&2; exit 2;; esac; \
    kind="$$component"; tier="$${TIER:-}"; targets="$${TARGETS:-}"; \
    if [[ "$$kind" == "infra" ]]; then \
      if ! [[ "$$tier" =~ ^(pods|hog|latency)$$ ]]; then echo "make d3 chaos infra needs TIER=pods|hog|latency" >&2; exit 2; fi; \
      if [[ -n "$$targets" ]]; then echo "TARGETS is for make d3 chaos platform" >&2; exit 2; fi; \
    else \
      if ! [[ "$$targets" =~ ^[a-z0-9][a-z0-9,-]*$$ ]]; then echo "make d3 chaos platform needs TARGETS=<id,id> (ids of platform/chaos/targets.yaml)" >&2; exit 2; fi; \
      if [[ -n "$$tier" ]]; then echo "TIER is for make d3 chaos infra" >&2; exit 2; fi; \
    fi; \
    if [[ "$${CHAOS_CONFIRM:-}" != "$$kind" ]]; then echo "make d3 chaos $$kind injects failures into the live cluster: type the kind again, CHAOS_CONFIRM=$$kind" >&2; exit 2; fi; \
    python3 platform/chaos/targets.py plan --kind "$$kind" --tier "$$tier" --targets "$$targets" >/dev/null || exit 2; \
    chaos_args=(-e "chaos_kind=$$kind" -e "chaos_tier=$$tier" -e "chaos_targets=$$targets"); \
    aap_route workflow "zuno-day3-chaos-$$kind-workflow" "{\"chaos_kind\": \"$$kind\", \"chaos_tier\": \"$$tier\", \"chaos_targets\": \"$$targets\"}"; rc=$$?; \
    if [[ $$rc -eq 99 ]]; then \
      if [[ ! -t 0 ]]; then echo "make d3 chaos runs locally only from an interactive terminal: it pauses for a person between the pre-check and the run" >&2; exit 2; fi; \
      $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/day3_chaos_precheck.yml "$${chaos_args[@]}" $(EXTRA_VARS) || exit $$?; \
      read -r -p "Pre-check passed (see above). Press Enter to start the chaos run, or Ctrl-C to stop here with nothing started: " _chaos_confirm; \
      run_rc=0; $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/day3_chaos_run.yml "$${chaos_args[@]}" $(EXTRA_VARS) || run_rc=$$?; \
      post_rc=0; $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/day3_chaos_postcheck.yml "$${chaos_args[@]}" $(EXTRA_VARS) || post_rc=$$?; \
      if [[ $$run_rc -ne 0 ]]; then exit $$run_rc; fi; exit $$post_rc; \
    else \
      exit $$rc; \
    fi ;; \
esac
endef

day3: $(if $(DAY_VERB),credentials-check)
	$(DAY3_RECIPE)

d3: $(if $(DAY_VERB),credentials-check)
	$(DAY3_RECIPE)

# Verb/component tokens are intentionally no-op Make targets. The day0/d0/
# day1/d1/day2/d2/day3/d3/demo recipes read MAKECMDGOALS words 2 and 3
# directly, so e.g. `make d0 check postgresql` or `make demo step next`
# needs "check"/"postgresql"/"next" to resolve to *something* as Make
# goals without erroring as unknown targets.
NOOP_WORDS := $(sort $(DAY0_VERBS) $(DAY0_COMPONENTS) $(DAY1_VERBS) $(DAY1_RUN_COMPONENTS) $(DAY1_BUILD_COMPONENTS) $(DAY2_VERBS) $(DAY2_RUN_COMPONENTS) $(DAY2_CHECK_ONLY_COMPONENTS) $(DAY2_BUILD_COMPONENTS) $(DAY3_VERBS) $(DAY3_COMPONENTS) $(DAY3_TEST_COMPONENTS) $(DAY3_BACKUP_COMPONENTS) $(DAY3_CHECK_ONLY_COMPONENTS) $(DAY3_CHAOS_KINDS) $(DEMO_VERBS))
$(NOOP_WORDS):
	@:

# ADR-0616/WP-270: after `demo`, every other word (a demo id, next, a step
# number, 5, 15, on, off) is a no-op goal too - except the words that are
# already targets, so `make demo help` never redefines `help`.
DEMO_REAL_TARGETS := help credentials-check day0 d0 day1 d1 day2 d2 day3 d3 demo new-mcp-server completion _complete-top _complete-verbs _complete-components
DEMO_NOOP_WORDS := $(sort $(filter-out $(NOOP_WORDS) $(DEMO_REAL_TARGETS),$(DEMO_ARGS)))
ifneq ($(DEMO_NOOP_WORDS),)
$(DEMO_NOOP_WORDS):
	@:
endif
