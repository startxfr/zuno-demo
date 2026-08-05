SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

ANSIBLE_PLAYBOOK ?= ansible-playbook
INVENTORY ?= ansible/inventories/demo/hosts.yml
EXTRA_VARS ?=

# ADR-0056: Day 0 (cluster prerequisites) / Day 1 (build + run the
# platform) sequencing, replacing the former precheck/prepare/configure/
# install/check interface outright.
DAY0_COMPONENTS := admin-context argocd namespaces vault external-secrets keycloak postgresql smtp nfd nvidia-gpu observability openshift-ai
DAY0_VERBS := check install configure all

# Day 1 has two different valid component sets depending on the verb:
# "build" only knows how to build the 3 named image groups (mcp, rag,
# agent - see ansible/roles/{mcp,rag,agent}_build); "check"/"configure"/
# "run" operate on the 7 deployable components (models/sql-schema/mlops
# go beyond your original "llm, rag, mcp, agents" list deliberately - see
# ansible/playbooks/day1_check.yml's header comment for why dropping them
# would be a functional regression, not just a naming choice).
# "configure" and "run" are aliases of each other.
DAY1_RUN_COMPONENTS := llm models sql-schema rag mcp agents mlops
DAY1_BUILD_COMPONENTS := mcp rag agent
DAY1_VERBS := check build configure run all

DAY_VERB := $(word 2,$(MAKECMDGOALS))
DAY_COMPONENT := $(word 3,$(MAKECMDGOALS))

.PHONY: help credentials-check day0 d0 day1 d1 $(DAY0_VERBS) $(DAY0_COMPONENTS) $(DAY1_VERBS) $(DAY1_RUN_COMPONENTS) $(DAY1_BUILD_COMPONENTS)

help:
	@printf '%s\n' \
	  'Zuno Demo operator interface' \
	  '' \
	  '  Required once, before any target below:' \
	  '    export K8S_AUTH_HOST=https://api.mycluster.com:6443' \
	  '    export K8S_AUTH_API_KEY=<cluster-admin token>' \
	  '  This is the only manual input for the entire install - everything else' \
	  '  (Keycloak, Vault, PostgreSQL, OpenShift AI, MLOps...) is automated.' \
	  '' \
	  '  make day0|d0 check [component]      Check one/all Day 0 prerequisites' \
	  '  make day0|d0 install [component]    Install one/all Day 0 prerequisites' \
	  '  make day0|d0 configure [component]  Configure one/all Day 0 prerequisites' \
	  '  make day0|d0 all [component]        check + install + configure, in order' \
	  '' \
	  '  make day1|d1 check [component]      Check one/all Day 1 components (agents runs the ADR-0053 acceptance gate)' \
	  '  make day1|d1 build [component]      Build one/all Day 1 component images' \
	  '  make day1|d1 configure [component]  Configure/deploy one/all Day 1 components (alias: run)' \
	  '  make day1|d1 run [component]        Same as configure' \
	  '  make day1|d1 all [component]        check + build + configure, whichever apply to the component' \
	  '' \
	  'Day 0 components: $(DAY0_COMPONENTS)' \
	  'Day 1 components (check/configure/run): $(DAY1_RUN_COMPONENTS)' \
	  'Day 1 components (build):               $(DAY1_BUILD_COMPONENTS)'

credentials-check:
	@if [[ -z "$${K8S_AUTH_HOST:-}" || -z "$${K8S_AUTH_API_KEY:-}" ]]; then \
	  echo "K8S_AUTH_HOST and K8S_AUTH_API_KEY must be exported first - see 'make help'." >&2; \
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
  configure) run_one configure ;; \
  all) run_one check && run_one install && run_one configure ;; \
esac
endef

day0: credentials-check
	$(DAY0_RECIPE)

d0: credentials-check
	$(DAY0_RECIPE)

# day1/d1 share this exact recipe. "all" is handled specially: build
# components (mcp, rag, agent) and run components (mcp, models, sql-schema,
# rag, mcp, agents, mlops) are different, overlapping-but-not-identical
# sets (most visibly: "agent" builds, "agents" runs - singular vs plural,
# a real name, not a typo), so `make d1 all <component>` runs whichever of
# check/build/configure actually apply to that specific component instead
# of assuming one shared list.
define DAY1_RECIPE
@verb="$(DAY_VERB)"; \
component="$${TARGET_COMPONENT:-$(DAY_COMPONENT)}"; \
if [[ -z "$$component" ]]; then component=all; fi; \
case " $(DAY1_VERBS) " in *" $$verb "*) ;; *) echo "Unsupported day1 verb: '$$verb' (expected one of: $(DAY1_VERBS))" >&2; exit 2;; esac; \
run_check() { $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/day1_check.yml -e "target_component=$$component" $(EXTRA_VARS); }; \
run_build() { $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/day1_build.yml -e "target_component=$$component" $(EXTRA_VARS); }; \
run_configure() { $(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/day1_configure.yml -e "target_component=$$component" $(EXTRA_VARS); }; \
case "$$verb" in \
  check) \
    case " $(DAY1_RUN_COMPONENTS) all " in *" $$component "*) ;; *) echo "Unsupported day1 check component: '$$component' (expected one of: $(DAY1_RUN_COMPONENTS) or all)" >&2; exit 2;; esac; \
    run_check ;; \
  build) \
    case " $(DAY1_BUILD_COMPONENTS) all " in *" $$component "*) ;; *) echo "Unsupported day1 build component: '$$component' (expected one of: $(DAY1_BUILD_COMPONENTS) or all)" >&2; exit 2;; esac; \
    run_build ;; \
  configure|run) \
    case " $(DAY1_RUN_COMPONENTS) all " in *" $$component "*) ;; *) echo "Unsupported day1 $$verb component: '$$component' (expected one of: $(DAY1_RUN_COMPONENTS) or all)" >&2; exit 2;; esac; \
    run_configure ;; \
  all) \
    is_run=0; is_build=0; \
    case " $(DAY1_RUN_COMPONENTS) all " in *" $$component "*) is_run=1;; esac; \
    case " $(DAY1_BUILD_COMPONENTS) all " in *" $$component "*) is_build=1;; esac; \
    if [[ $$is_run -eq 0 && $$is_build -eq 0 ]]; then \
      echo "Unsupported day1 component: '$$component' (expected one of: $(DAY1_RUN_COMPONENTS) $(DAY1_BUILD_COMPONENTS) or all)" >&2; exit 2; \
    fi; \
    if [[ $$is_run -eq 1 ]]; then run_check || exit $$?; fi; \
    if [[ $$is_build -eq 1 ]]; then run_build || exit $$?; fi; \
    if [[ $$is_run -eq 1 ]]; then run_configure || exit $$?; fi ;; \
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
