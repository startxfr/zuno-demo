SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

ANSIBLE_PLAYBOOK ?= ansible-playbook
INVENTORY ?= ansible/inventories/demo/hosts.yml
EXTRA_VARS ?=

# ADR-0056: Day 0 (cluster prerequisites) / Day 1 (build + run the
# platform) sequencing, replacing the former precheck/prepare/configure/
# install/check interface outright.
DAY0_COMPONENTS := admin-context argocd namespaces openshift-rbac-groups vault cert-manager external-secrets keycloak openshift-oauth redis postgresql mariadb service-mesh tempo mesh-monitoring kiali grafana smtp machines nfd nvidia-gpu observability connectivity-link lws custom-metrics-autoscaler jobset kueue openshift-ai
DAY0_VERBS := check install uninstall reconcile all reinstall

# Day 1 has two different valid component sets depending on the verb:
# "build" only knows how to build the 5 named image groups (mcp, rag,
# rag-ingestion, agent, ai-gateway - see
# ansible/roles/{mcp,rag,rag_ingestion,agent,ai_gateway}_build);
# "check"/"install" operate on the 9 deployable components
# (models/sql-schema/mlops go beyond your original "llm, rag, mcp,
# agents" list deliberately - see ansible/playbooks/day1_check.yml's
# header comment for why dropping them would be a functional regression,
# not just a naming choice). "namespaces" is also here despite being a
# Day 0 component everywhere else in this Makefile - only its
# quota/network-policy overlay is Day 1, see
# ansible/roles/namespaces/README.md.
DAY1_RUN_COMPONENTS := namespaces llm models sql-schema rag rag-ingestion mcp aiagent-operator agents mlops
DAY1_BUILD_COMPONENTS := mcp rag rag-ingestion agent ai-gateway mlops aiagent-operator
DAY1_VERBS := check install build uninstall all reinstall

# ADR-0057/ADR-0058: Day 2 (agent test / stresstest operations), the third
# stage after Day 0 (cluster prerequisites) and Day 1 (build + run the
# platform). "test" only ever proves availability (agent frontends'
# /healthz, shared platform services' /healthz+/readyz); "stresstest" runs
# every existing test layer per agent (contract/scenarios/security/gate/
# stress_test) plus an optional bulk-interaction load pass. Component
# granularity matches Day 1's "agents" (every agent bundle, collectively)
# plus a new "platform" component for the shared services - which agents/
# services actually exist is resolved dynamically from
# agents/*/agent.okf.md at Ansible run time, never a list here.
DAY2_COMPONENTS := agents platform
DAY2_VERBS := test stresstest

DAY_VERB := $(word 2,$(MAKECMDGOALS))
DAY_COMPONENT := $(word 3,$(MAKECMDGOALS))

.PHONY: help credentials-check day0 d0 day1 d1 day2 d2 new-mcp-server $(DAY0_VERBS) $(DAY0_COMPONENTS) $(DAY1_VERBS) $(DAY1_RUN_COMPONENTS) $(DAY1_BUILD_COMPONENTS) $(DAY2_VERBS) $(DAY2_COMPONENTS)

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
	  '  make day1|d1 check [component]      Check one/all Day 1 components'"'"' install state (agents runs the ADR-0053 acceptance gate)' \
	  '  make day1|d1 build [component]      Build one/all Day 1 component images' \
	  '  make day1|d1 install [component]    Install/deploy one/all Day 1 components (no component: builds first)' \
	  '  make day1|d1 uninstall [component]  Uninstall one/all Day 1 components (reverse order)' \
	  '  make day1|d1 all [component]        check + build + install, whichever apply to the component' \
	  '  make day1|d1 reinstall [component]  Uninstall then install one/all Day 1 components' \
	  '' \
	  '  make day2|d2 test [component]        Check availability only (ADR-0057)' \
	  '  make day2|d2 stresstest [component]  Run every existing test layer per agent, plus a bulk-interaction load pass (ADR-0058)' \
	  '' \
	  '  make new-mcp-server NAME=<name> [DESCRIPTION="..."]   Scaffold a new MCP server (ADR-0119)' \
	  '' \
	  'Day 0 components: $(DAY0_COMPONENTS)' \
	  'Day 1 components (check/install): $(DAY1_RUN_COMPONENTS)' \
	  'Day 1 components (build):         $(DAY1_BUILD_COMPONENTS)' \
	  'Day 2 components: $(DAY2_COMPONENTS)' \
	  'Day 2 report format: text (default) | json | csv - set via REPORT_FORMAT=<fmt> or EXTRA_VARS="-e report_format=<fmt>"'

# ADR-0119: scaffold a new MCP server from the confluence-shaped template
# instead of hand-copying an existing server directory-by-directory.
new-mcp-server:
	@if [[ -z "$(NAME)" ]]; then \
	  echo "Usage: make new-mcp-server NAME=<name> [DESCRIPTION=\"...\"]" >&2; \
	  exit 2; \
	fi
	python3 platform/scaffolding/new_mcp_server.py "$(NAME)" $(if $(DESCRIPTION),--description "$(DESCRIPTION)")

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

# day1/d1 share this exact recipe. "all" is handled specially: build
# components (mcp, rag, agent, ai-gateway) and run components (mcp, models, sql-schema,
# rag, mcp, agents, mlops) are different, overlapping-but-not-identical
# sets (most visibly: "agent" builds, "agents" runs - singular vs plural,
# a real name, not a typo), so `make d1 all <component>` runs whichever of
# check/build/install actually apply to that specific component instead
# of assuming one shared list. `install` with no component (component
# defaults to "all") also runs build first, same as `all` does - a named
# single-component install (`make d1 install rag`) does not, build/install
# stay separate verbs there (`make d1 install rag` alone can deploy a
# Deployment whose image was never built, a permanent ImagePullBackOff -
# "install everything" must never do that).
define DAY1_RECIPE
@verb="$(DAY_VERB)"; \
component="$${TARGET_COMPONENT:-$(DAY_COMPONENT)}"; \
if [[ -z "$$verb" ]]; then \
  printf '%s\n' \
    'Zuno Demo - Day 1 (build + run the platform)' \
    '' \
    'Usage: make day1|d1 <verb> [component]' \
    '' \
    '  check       Check one/all Day 1 components'"'"' install state (agents runs the ADR-0053 acceptance gate)' \
    '  build       Build one/all Day 1 component images' \
    '  install     Install/deploy one/all Day 1 components (no component: builds first)' \
    '  uninstall   Uninstall one/all Day 1 components (reverse order)' \
    '  all         check + build + install, whichever apply to the component' \
    '  reinstall   Uninstall then install one/all Day 1 components' \
    '' \
    'Components (check/install/uninstall/all; optional, default: all):' \
    '  $(DAY1_RUN_COMPONENTS)' \
    '' \
    'Components (build; optional, default: all):' \
    '  $(DAY1_BUILD_COMPONENTS)' \
    '' \
    'Example: make d1 install rag'; \
  exit 0; \
fi; \
if [[ -z "$$component" ]]; then component=all; fi; \
case " $(DAY1_VERBS) " in *" $$verb "*) ;; *) echo "Unsupported day1 verb: '$$verb' (expected one of: $(DAY1_VERBS))" >&2; exit 2;; esac; \
run_check() { $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/day1_check.yml -e "target_component=$$component" $(EXTRA_VARS); }; \
run_build() { $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/day1_build.yml -e "target_component=$$component" $(EXTRA_VARS); }; \
run_install() { $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/day1_install.yml -e "target_component=$$component" $(EXTRA_VARS); }; \
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

# day2/d2 share this exact recipe. Only two components (agents, platform)
# and two verbs (test, stresstest) - no build/run split like Day 1, since
# neither verb ever changes cluster state, only observes/exercises it.
# report_format defaults to "text" (ADR-0057 decision 4: raw table always
# printed; json/csv are additional artifacts, selected via REPORT_FORMAT=
# or EXTRA_VARS="-e report_format=..."). "stresstest" additionally reads
# BULK (ADR-0058 decision 3): unset in an interactive shell prompts for a
# bulk-interaction count with a default of 10; unset in a non-interactive
# shell (stdin not a TTY, e.g. CI) silently defaults to 10 without
# prompting, so this recipe never blocks a non-interactive caller. BULK=0
# runs the functional layers only, no bulk-interaction load pass.
define DAY2_RECIPE
@verb="$(DAY_VERB)"; \
component="$${TARGET_COMPONENT:-$(DAY_COMPONENT)}"; \
if [[ -z "$$verb" ]]; then \
  printf '%s\n' \
    'Zuno Demo - Day 2 (agent test / stresstest operations)' \
    '' \
    'Usage: make day2|d2 <verb> [component]' \
    '' \
    '  test         Check availability only (agent frontends'"'"' /healthz, shared platform services'"'"' /healthz+/readyz)' \
    '  stresstest   Run every existing test layer per agent, plus an optional bulk-interaction load pass (ADR-0058)' \
    '' \
    'Components (optional, default: all):' \
    '  $(DAY2_COMPONENTS)' \
    '' \
    'Report format: text (default) | json | csv - REPORT_FORMAT=<fmt> or EXTRA_VARS="-e report_format=<fmt>"' \
    'Bulk interaction count (stresstest only): BULK=<n> (skips the interactive prompt; BULK=0 disables it)' \
    '' \
    'Example: make d2 test agents' \
    'Example: make d2 stresstest BULK=25'; \
  exit 0; \
fi; \
if [[ -z "$$component" ]]; then component=all; fi; \
case " $(DAY2_VERBS) " in *" $$verb "*) ;; *) echo "Unsupported day2 verb: '$$verb' (expected one of: $(DAY2_VERBS))" >&2; exit 2;; esac; \
case " $(DAY2_COMPONENTS) all " in *" $$component "*) ;; *) echo "Unsupported day2 component: '$$component' (expected one of: $(DAY2_COMPONENTS) or all)" >&2; exit 2;; esac; \
report_format="$${REPORT_FORMAT:-text}"; \
case "$$verb" in \
  test) $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/day2_test.yml -e "target_component=$$component" -e "report_format=$$report_format" $(EXTRA_VARS) ;; \
  stresstest) \
    bulk="$${BULK:-}"; \
    if [[ -z "$$bulk" ]]; then \
      if [[ -t 0 ]]; then \
        read -r -p "Bulk interaction count [10]: " bulk; \
        bulk="$${bulk:-10}"; \
      else \
        bulk=10; \
      fi; \
    fi; \
    $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/day2_stresstest.yml -e "target_component=$$component" -e "report_format=$$report_format" -e "bulk_interactions=$$bulk" $(EXTRA_VARS) ;; \
esac
endef

day2: $(if $(DAY_VERB),credentials-check)
	$(DAY2_RECIPE)

d2: $(if $(DAY_VERB),credentials-check)
	$(DAY2_RECIPE)

# Verb/component tokens are intentionally no-op Make targets. The day0/d0/
# day1/d1/day2/d2 recipes read MAKECMDGOALS words 2 and 3 directly, so e.g.
# `make d0 check postgresql` needs "check" and "postgresql" to resolve to
# *something* as Make goals without erroring as unknown targets.
$(sort $(DAY0_VERBS) $(DAY0_COMPONENTS) $(DAY1_VERBS) $(DAY1_RUN_COMPONENTS) $(DAY1_BUILD_COMPONENTS) $(DAY2_VERBS) $(DAY2_COMPONENTS)):
	@:
