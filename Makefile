SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

ANSIBLE_PLAYBOOK ?= ansible-playbook
INVENTORY ?= ansible/inventories/demo/hosts.yml
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
DAY0_COMPONENTS := admin-context argocd namespaces openshift-rbac-groups vault cert-manager external-secrets machines postgresql keycloak aap aap-config
DAY0_VERBS := check install uninstall reconcile all reinstall

# Day 1 is the remainder of the AI-platform-operator stack (mesh, Kueue,
# OpenShift AI, etc.) plus aiagent-operator, which runs last - standard
# operator-before-CR ordering, since Day 2's "agents" component creates
# the AIAgent CRs it reconciles. No build/run split beyond ai-gateway (see
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
# "openshift-ai" and before "aiagent-operator": the OpenShift Lightspeed
# operator has no dependency beyond OLM, which is exactly why only the
# OPERATOR is here. Its configuration is a separate Day 2 component
# ("lightspeed-config") - an OLSConfig created in Day 1 would reference a
# MaaS model and an MCP endpoint that don't exist until Day 2, and would
# sit Degraded for the whole window while ArgoCD self-healed it back.
DAY1_RUN_COMPONENTS := smtp nfd nvidia-gpu custom-metrics-autoscaler redis observability service-mesh mesh-monitoring kiali grafana mariadb tempo openshift-oauth connectivity-link lws jobset kueue openshift-ai lightspeed rhtas aiagent-operator
DAY1_BUILD_COMPONENTS := ai-gateway supply-chain-signer aiagent-operator aap-execution-environment
DAY1_VERBS := check install build uninstall reconcile all reinstall

# Day 2 is namespace policy overlay, AI infrastructure (llm, models), and
# content ingestion (rag, rag-ingestion, mcp, agents, mlops) -
# moved here from Day 1 (ADR-0060). "namespaces" is here despite being a
# Day 0 component everywhere else in this Makefile - only its
# quota/network-policy overlay is Day 2 now, see
# ansible/roles/namespaces/README.md (internal task/Application naming
# stays "_d1"/"-d1", an implementation detail, not renamed with the macro
# tier). "build" only knows how to build the 5 named image groups (mcp,
# rag, rag-ingestion, agent, mlops - see
# ansible/roles/{mcp,rag,rag_ingestion,agent,mlops}_build); "check"/
# "trustyai-config" (ADR-0534/WP-107) sits right after "mlops": it depends
# only on "models" (the zuno-ai-run namespace its LMEvalJob-based health
# check reads) - TrustyAI itself needs no Day 1 operator, it is already
# Managed inside the Day 1 "openshift-ai" component. "lightspeed-config"
# (ADR-0524/WP-085) is deliberately LAST among the deployable components:
# it needs "models" (the MaaS entitlement for its ServiceAccount), "mcp"
# (the /mcp front-door plus the NetworkPolicy admitting
# openshift-lightspeed) and "agents" all already live, plus the Day 1
# "lightspeed" operator installed before any of it.
# "install" operate on the 11 deployable components, plus "supply-chain"
# (ADR-0420/WP-070) for "check" only - it has no install/build of its own,
# only a signature-verification gate (ansible/roles/supply_chain).
DAY2_RUN_COMPONENTS := namespaces llm models rag rag-ingestion mcp agents mlops trustyai-config mlflow lightspeed-config supply-chain
DAY2_BUILD_COMPONENTS := mcp rag rag-ingestion agent mlops trustyai-eval
DAY2_VERBS := check install build uninstall all reinstall

# ADR-0057/ADR-0058: Day 3 was originally agent test/stresstest operations
# only; widened 2026-08-24 into the general "operational tasks" tier -
# anything that acts on an already-installed component rather than
# installing/uninstalling it (test, stresstest, backup, restore, check).
# Each verb has its own component list, same split Day 1 already uses for
# "build" vs "check/install/uninstall" (DAY1_BUILD_COMPONENTS vs
# DAY1_RUN_COMPONENTS) - not every Day 3 verb applies to every Day 3
# component. "test"/"stresstest" only ever prove availability (agent
# frontends' /healthz, shared platform services' /healthz+/readyz) or run
# the full per-agent test layer; component granularity matches Day 2's
# "agents" (every agent bundle, collectively) plus "platform" for the
# shared services - which agents/services actually exist is resolved
# dynamically from agents/*/agent.okf.md at Ansible run time, never a list
# here. "backup"/"restore" are per-component pgBackRest-style operations
# (see ansible/roles/postgresql/tasks/{backup,restore}.yml); "check" spans
# every Day 3 component regardless of verb group, delegating to the same
# availability test for agents/platform and to each component's own
# precheck.yml otherwise (ansible/playbooks/day3_check.yml).
DAY3_TEST_COMPONENTS := agents platform
DAY3_BACKUP_COMPONENTS := postgresql
# ADR-0420/WP-069: re-signing the OKF bundles acts on already-installed
# agent bundles - it builds nothing - so it belongs in this tier by the
# definition above, not inside `make d2 build agent`. Its own component
# list, same per-verb split as backup/restore.
DAY3_SIGN_COMPONENTS := agents
# Components that support "check" but neither test/stresstest nor
# backup/restore - they contribute only their own precheck.yml
# (ansible/playbooks/day3_check.yml). ADR-0524/WP-085: "lightspeed" and
# "lightspeed-config" are two entries, not one, because the component is split
# across day tiers - checking only the operator would report healthy while the
# OLSConfig operand is absent, and vice versa.
DAY3_CHECK_ONLY_COMPONENTS := lightspeed lightspeed-config trustyai-config mlflow
# WP-126: triggering a real pipeline run spends real, costly compute (a GPU
# burst-node scale-up, several minutes of training) against an
# already-installed platform - the same tier as backup/restore/sign, never
# a side effect of `make d2 install mlops`. Its own component list, same
# per-verb split as backup/restore.
DAY3_RUN_COMPONENTS := mlops
# ADR-0549/WP-134: cutting a named, signed, in-cluster release is an
# on-demand operator action against an already-installed platform, spends
# real build+sign compute - same tier as sign/run, its own component list.
DAY3_RELEASE_COMPONENTS := supply-chain
DAY3_COMPONENTS := $(sort $(DAY3_TEST_COMPONENTS) $(DAY3_BACKUP_COMPONENTS) $(DAY3_SIGN_COMPONENTS) $(DAY3_CHECK_ONLY_COMPONENTS) $(DAY3_RUN_COMPONENTS) $(DAY3_RELEASE_COMPONENTS))
DAY3_VERBS := test stresstest backup restore check sign run release scenario-failover-node

# ADR-0418 clause 6/WP-097: shared shell functions every day1/day2/day3
# recipe below sources to route mutating/read verbs through AAP when
# zuno_make_aap_mode allows it, instead of always running ansible-playbook
# from this shell. Defined once here (not duplicated per recipe) since
# each DAYn_RECIPE's `define...endef` body runs as its own separate shell
# invocation - shell functions can't be shared any other way in this file.
# resolve_aap_mode() reads ansible/confidential.yml directly: the Makefile
# has no other way to reach an Ansible-sourced variable before deciding
# whether to invoke ansible-playbook at all, and this decision must happen
# here, in the shell, before any playbook runs. Never fails even if the
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
  local mode="auto"; \
  if [[ -f ansible/confidential.yml ]]; then \
    local val; \
    val="$$(python3 -c "import yaml; d=yaml.safe_load(open('ansible/confidential.yml')) or {}; print(d.get('zuno_make_aap_mode','auto'))" 2>/dev/null)"; \
    [[ -n "$$val" ]] && mode="$$val"; \
  fi; \
  case "$$mode" in \
    local|remote|auto) ;; \
    *) echo "Invalid zuno_make_aap_mode in ansible/confidential.yml: '$$mode' (expected local|remote|auto)" >&2; exit 2 ;; \
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
  esac; \
  $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/aap_launch.yml -e "{\"aap_launch_type\": \"$$kind\", \"aap_launch_template\": \"$$template\", \"aap_launch_extra_vars\": $$extra_vars_json}" $(EXTRA_VARS); \
};
endef

DAY_VERB := $(word 2,$(MAKECMDGOALS))
DAY_COMPONENT := $(word 3,$(MAKECMDGOALS))

.PHONY: help credentials-check day0 d0 day1 d1 day2 d2 day3 d3 new-mcp-server completion _complete-verbs _complete-components $(DAY0_VERBS) $(DAY0_COMPONENTS) $(DAY1_VERBS) $(DAY1_RUN_COMPONENTS) $(DAY1_BUILD_COMPONENTS) $(DAY2_VERBS) $(DAY2_RUN_COMPONENTS) $(DAY2_BUILD_COMPONENTS) $(DAY3_VERBS) $(DAY3_COMPONENTS) $(DAY3_TEST_COMPONENTS) $(DAY3_BACKUP_COMPONENTS) $(DAY3_CHECK_ONLY_COMPONENTS)

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
	  '  make day2|d2 all [component]        check + build + install, whichever apply to the component' \
	  '  make day2|d2 reinstall [component]  Uninstall then install one/all Day 2 components' \
	  '' \
	  '  make day3|d3 test [component]        Check availability only (ADR-0057)' \
	  '  make day3|d3 stresstest [component]  Run every existing test layer per agent, plus a bulk-interaction load pass (ADR-0058)' \
	  '  make day3|d3 sign [component]        Re-sign the OKF bundles and verify them (ADR-0420) - run after ANY change under agents/<name>/' \
	  '  make day3|d3 run [component]         Trigger one real pipeline run (WP-126) - AGENT=<agent> overrides the default (comage)' \
	  '' \
	  '  make new-mcp-server NAME=<name> [DESCRIPTION="..."]   Scaffold a new MCP server (ADR-0119)' \
	  '' \
	  '  make completion   Print a bash completion function for day0|d0/day1|d1/day2|d2/day3|d3' \
	  '                    (verb-then-component aware). Wire it up once, in ~/.bashrc:' \
	  '                    eval "$$(cd $(CURDIR) && make completion)"' \
	  '' \
	  'Day 0 components: $(DAY0_COMPONENTS)' \
	  'Day 1 components (check/install): $(DAY1_RUN_COMPONENTS)' \
	  'Day 1 components (build):         $(DAY1_BUILD_COMPONENTS)' \
	  'Day 2 components (check/install): $(DAY2_RUN_COMPONENTS)' \
	  'Day 2 components (build):         $(DAY2_BUILD_COMPONENTS)' \
	  'Day 3 components (test/stresstest/check): $(DAY3_TEST_COMPONENTS)' \
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

# Bash completion for `make day0|d0/day1|d1/day2|d2/day3|d3 <verb> [component]`.
# _complete-verbs/_complete-components are the single source of truth for
# what to offer at each position - they just echo the same
# DAY*_VERBS/DAY*_RUN_COMPONENTS/DAY*_BUILD_COMPONENTS variables the real
# recipes validate against above, so the completion list can never drift
# from what a command would actually accept. `completion` emits a bash
# function that shells out to them live (one `make` call per Tab press),
# rather than baking a static word list into the emitted script.
_complete-verbs:
	@case "$(DAY)" in \
	  0) echo "$(DAY0_VERBS)" ;; \
	  1) echo "$(DAY1_VERBS)" ;; \
	  2) echo "$(DAY2_VERBS)" ;; \
	  3) echo "$(DAY3_VERBS)" ;; \
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
	       *) echo "$(DAY2_RUN_COMPONENTS) all" ;; \
	     esac ;; \
	  3) case "$(VERB)" in \
	       backup|restore) echo "$(DAY3_BACKUP_COMPONENTS) all" ;; \
	       sign) echo "$(DAY3_SIGN_COMPONENTS) all" ;; \
	       run) echo "$(DAY3_RUN_COMPONENTS) all" ;; \
	       release) echo "$(DAY3_RELEASE_COMPONENTS) all" ;; \
	       *) echo "$(DAY3_COMPONENTS) all" ;; \
	     esac ;; \
	esac

completion:
	@printf '%s\n' \
	  '_zuno_demo_make_complete() {' \
	  '  local cur day verb' \
	  '  cur=$$2' \
	  '  case "$${COMP_WORDS[1]}" in' \
	  '    day0|d0) day=0 ;;' \
	  '    day1|d1) day=1 ;;' \
	  '    day2|d2) day=2 ;;' \
	  '    day3|d3) day=3 ;;' \
	  '    *) return 0 ;;' \
	  '  esac' \
	  '  if [[ $$COMP_CWORD -eq 2 ]]; then' \
	  '    COMPREPLY=( $$(compgen -W "$$(command make -s -C "$(CURDIR)" _complete-verbs DAY=$$day 2>/dev/null)" -- "$$cur") )' \
	  '  elif [[ $$COMP_CWORD -eq 3 ]]; then' \
	  '    verb=$${COMP_WORDS[2]}' \
	  '    COMPREPLY=( $$(compgen -W "$$(command make -s -C "$(CURDIR)" _complete-components DAY=$$day VERB=$$verb 2>/dev/null)" -- "$$cur") )' \
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
    '  all         check + build + install, whichever apply to the component' \
    '  reinstall   Uninstall then install one/all Day 2 components' \
    '' \
    'Components (check/install/uninstall/all; optional, default: all):' \
    '  $(DAY2_RUN_COMPONENTS)' \
    '' \
    'Components (build; optional, default: all):' \
    '  $(DAY2_BUILD_COMPONENTS)' \
    '' \
    'Example: make d2 install rag'; \
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
case "$$verb" in \
  check) \
    case " $(DAY2_RUN_COMPONENTS) all " in *" $$component "*) ;; *) echo "Unsupported day2 check component: '$$component' (expected one of: $(DAY2_RUN_COMPONENTS) or all)" >&2; exit 2;; esac; \
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
    '  test         Check availability only (agent frontends'"'"' /healthz, shared platform services'"'"' /healthz+/readyz)' \
    '  stresstest   Run every existing test layer per agent, plus an optional bulk-interaction load pass (ADR-0058)' \
    '  backup       Trigger an on-demand backup' \
    '  restore      Restore from the most recent backup (fails if none exists)' \
    '  check        Check state/health across every Day 3 component (test for agents/platform, precheck otherwise)' \
    '  sign         Re-sign every OKF bundle against the deployed agent-runtime image, then verify (ADR-0420)' \
    '               The signed digest covers every file under agents/<name>/, tasks/ included - not just agent.okf.md' \
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
    '' \
    'Components (test/stresstest/check; optional, default: all):' \
    '  $(DAY3_TEST_COMPONENTS)' \
    '' \
    'Components (backup/restore; optional, default: all):' \
    '  $(DAY3_BACKUP_COMPONENTS)' \
    '' \
    'Components (sign; optional, default: all):' \
    '  $(DAY3_SIGN_COMPONENTS)' \
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
    'Agent to train (run only): AGENT=<agent> (default: comage - the only agent with a compiled pipeline version today)' \
    'Release tag (release only, REQUIRED, no default): TAG=<tag> - must already be a real, pushed git tag' \
    '' \
    'Example: make d3 test agents' \
    'Example: make d3 stresstest BULK=25' \
    'Example: make d3 stresstest CLEANUP=0   # keep test conversations for inspection' \
    'Example: make d3 backup postgresql' \
    'Example: make d3 restore postgresql' \
    'Example: make d3 sign agents   # after editing ANY file under agents/<name>/ - agent.okf.md, tasks/*.md, anything' \
    'Example: make d3 run mlops   # triggers one real LoRA training run (WP-126) - scales up zuno-gpu-burst-a' \
    'Example: git tag v0.2.0 && git push origin v0.2.0 && make d3 release TAG=v0.2.0   # named in-cluster release (ADR-0549)' \
    'Example: make d3 scenario-failover-node   # interactive - pauses for confirmation between cordon+kill and uncordon+restore'; \
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
    bulk="$${BULK:-}"; \
    if [[ -z "$$bulk" ]]; then \
      if [[ -t 0 ]]; then \
        read -r -p "Bulk interaction count [10]: " bulk; \
        bulk="$${bulk:-10}"; \
      else \
        bulk=10; \
      fi; \
    fi; \
    cleanup="$${CLEANUP:-}"; \
    if [[ -z "$$cleanup" ]]; then \
      if [[ -t 0 ]]; then \
        read -r -p "Remove test-generated conversations after the run? [Y/n]: " cleanup_answer; \
        case "$$cleanup_answer" in [nN]*) cleanup=0 ;; *) cleanup=1 ;; esac; \
      else \
        cleanup=1; \
      fi; \
    fi; \
    aap_route job zuno-day3-stresstest "{\"target_component\": \"$$component\", \"report_format\": \"$$report_format\", \"bulk_interactions\": $$bulk, \"cleanup_test_data\": $$cleanup}"; rc=$$?; \
    if [[ $$rc -eq 99 ]]; then $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/day3_stresstest.yml -e "target_component=$$component" -e "report_format=$$report_format" -e "bulk_interactions=$$bulk" -e "cleanup_test_data=$$cleanup" $(EXTRA_VARS); else exit $$rc; fi ;; \
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
  sign) \
    case " $(DAY3_SIGN_COMPONENTS) all " in *" $$component "*) ;; *) echo "Unsupported day3 sign component: '$$component' (expected one of: $(DAY3_SIGN_COMPONENTS) or all)" >&2; exit 2;; esac; \
    aap_route job zuno-day3-sign "{\"target_component\": \"$$component\"}"; rc=$$?; \
    if [[ $$rc -eq 99 ]]; then $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/day3_sign.yml -e "target_component=$$component" $(EXTRA_VARS); else exit $$rc; fi ;; \
  run) \
    case " $(DAY3_RUN_COMPONENTS) all " in *" $$component "*) ;; *) echo "Unsupported day3 run component: '$$component' (expected one of: $(DAY3_RUN_COMPONENTS) or all)" >&2; exit 2;; esac; \
    agent="$${AGENT:-comage}"; \
    aap_route job zuno-day3-run "{\"target_component\": \"$$component\", \"agent\": \"$$agent\"}"; rc=$$?; \
    if [[ $$rc -eq 99 ]]; then $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/day3_run.yml -e "target_component=$$component" -e "agent=$$agent" $(EXTRA_VARS); else exit $$rc; fi ;; \
  release) \
    case " $(DAY3_RELEASE_COMPONENTS) all " in *" $$component "*) ;; *) echo "Unsupported day3 release component: '$$component' (expected one of: $(DAY3_RELEASE_COMPONENTS) or all)" >&2; exit 2;; esac; \
    if [[ -z "$${TAG:-}" ]]; then echo "day3 release requires TAG=<release_tag>, e.g. TAG=v0.2.0 (must already be a real, pushed git tag)" >&2; exit 2; fi; \
    tag="$$TAG"; \
    aap_route job zuno-day3-release "{\"target_component\": \"$$component\", \"release_tag\": \"$$tag\"}"; rc=$$?; \
    if [[ $$rc -eq 99 ]]; then $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/day3_release.yml -e "target_component=$$component" -e "release_tag=$$tag" $(EXTRA_VARS); else exit $$rc; fi ;; \
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
esac
endef

day3: $(if $(DAY_VERB),credentials-check)
	$(DAY3_RECIPE)

d3: $(if $(DAY_VERB),credentials-check)
	$(DAY3_RECIPE)

# Verb/component tokens are intentionally no-op Make targets. The day0/d0/
# day1/d1/day2/d2/day3/d3 recipes read MAKECMDGOALS words 2 and 3
# directly, so e.g. `make d0 check postgresql` needs "check" and
# "postgresql" to resolve to *something* as Make goals without erroring
# as unknown targets.
$(sort $(DAY0_VERBS) $(DAY0_COMPONENTS) $(DAY1_VERBS) $(DAY1_RUN_COMPONENTS) $(DAY1_BUILD_COMPONENTS) $(DAY2_VERBS) $(DAY2_RUN_COMPONENTS) $(DAY2_BUILD_COMPONENTS) $(DAY3_VERBS) $(DAY3_COMPONENTS) $(DAY3_TEST_COMPONENTS) $(DAY3_BACKUP_COMPONENTS) $(DAY3_SIGN_COMPONENTS) $(DAY3_CHECK_ONLY_COMPONENTS)):
	@:
