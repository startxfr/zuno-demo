SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

ANSIBLE_PLAYBOOK ?= ansible-playbook
INVENTORY ?= ansible/inventories/demo/hosts.yml
EXTRA_VARS ?=

# ADR-0056: Day 0 (cluster prerequisites) / Day 1 (build + run the
# platform) sequencing, replacing the former precheck/prepare/configure/
# install/check interface outright.
DAY0_COMPONENTS := admin-context argocd namespaces openshift-rbac-groups vault cert-manager external-secrets keycloak openshift-oauth console-favorites-provisioning redis postgresql mariadb service-mesh tempo mesh-monitoring kiali smtp nfd nvidia-gpu observability connectivity-link lws custom-metrics-autoscaler jobset kueue openshift-ai
DAY0_VERBS := check install uninstall all

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
DAY1_RUN_COMPONENTS := namespaces llm models sql-schema rag rag-ingestion mcp agents mlops
DAY1_BUILD_COMPONENTS := mcp rag rag-ingestion agent ai-gateway
DAY1_VERBS := check install build uninstall all

DAY_VERB := $(word 2,$(MAKECMDGOALS))
DAY_COMPONENT := $(word 3,$(MAKECMDGOALS))

.PHONY: help credentials-check day0 d0 day1 d1 $(DAY0_VERBS) $(DAY0_COMPONENTS) $(DAY1_VERBS) $(DAY1_RUN_COMPONENTS) $(DAY1_BUILD_COMPONENTS)

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
	  '  make day0|d0 all [component]        check + install, in order' \
	  '' \
	  '  make day1|d1 check [component]      Check one/all Day 1 components'"'"' install state (agents runs the ADR-0053 acceptance gate)' \
	  '  make day1|d1 build [component]      Build one/all Day 1 component images' \
	  '  make day1|d1 install [component]    Install/deploy one/all Day 1 components' \
	  '  make day1|d1 uninstall [component]  Uninstall one/all Day 1 components (reverse order)' \
	  '  make day1|d1 all [component]        check + build + install, whichever apply to the component' \
	  '' \
	  'Day 0 components: $(DAY0_COMPONENTS)' \
	  'Day 1 components (check/install): $(DAY1_RUN_COMPONENTS)' \
	  'Day 1 components (build):         $(DAY1_BUILD_COMPONENTS)'

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
if [[ -z "$$component" ]]; then component=all; fi; \
case " $(DAY0_VERBS) " in *" $$verb "*) ;; *) echo "Unsupported day0 verb: '$$verb' (expected one of: $(DAY0_VERBS))" >&2; exit 2;; esac; \
case " $(DAY0_COMPONENTS) all " in *" $$component "*) ;; *) echo "Unsupported day0 component: '$$component' (expected one of: $(DAY0_COMPONENTS) or all)" >&2; exit 2;; esac; \
run_one() { $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) "ansible/playbooks/day0_$$1.yml" -e "target_component=$$component" $(EXTRA_VARS); }; \
case "$$verb" in \
  check) run_one check ;; \
  install) run_one install ;; \
  uninstall) run_one uninstall ;; \
  all) run_one check && run_one install ;; \
esac
endef

day0: credentials-check
	$(DAY0_RECIPE)

d0: credentials-check
	$(DAY0_RECIPE)

# day1/d1 share this exact recipe. "all" is handled specially: build
# components (mcp, rag, agent, ai-gateway) and run components (mcp, models, sql-schema,
# rag, mcp, agents, mlops) are different, overlapping-but-not-identical
# sets (most visibly: "agent" builds, "agents" runs - singular vs plural,
# a real name, not a typo), so `make d1 all <component>` runs whichever of
# check/build/install actually apply to that specific component instead
# of assuming one shared list.
define DAY1_RECIPE
@verb="$(DAY_VERB)"; \
component="$${TARGET_COMPONENT:-$(DAY_COMPONENT)}"; \
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
esac
endef

day1: credentials-check
	$(DAY1_RECIPE)

d1: credentials-check
	$(DAY1_RECIPE)

# Verb/component tokens are intentionally no-op Make targets. The day0/d0/
# day1/d1 recipes read MAKECMDGOALS words 2 and 3 directly, so e.g.
# `make d0 check postgresql` needs "check" and "postgresql" to resolve to
# *something* as Make goals without erroring as unknown targets.
$(sort $(DAY0_VERBS) $(DAY0_COMPONENTS) $(DAY1_VERBS) $(DAY1_RUN_COMPONENTS) $(DAY1_BUILD_COMPONENTS)):
	@:
