SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

ANSIBLE_PLAYBOOK ?= ansible-playbook
INVENTORY ?= ansible/inventories/demo/hosts.yml
EXTRA_VARS ?=

# ADR-0056: Day 0 (cluster prerequisites) / Day 1 (build + run the
# platform) sequencing, replacing the former precheck/prepare/configure/
# install/check interface outright. Day 1 is added in a later commit.
DAY0_COMPONENTS := admin-context argocd namespaces vault keycloak postgresql smtp external-secrets nfd nvidia-gpu observability openshift-ai
DAY0_VERBS := check install configure all

DAY_VERB := $(word 2,$(MAKECMDGOALS))
DAY_COMPONENT := $(word 3,$(MAKECMDGOALS))

.PHONY: help credentials-check day0 d0 $(DAY0_VERBS) $(DAY0_COMPONENTS)

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
	  'Day 0 components: $(DAY0_COMPONENTS)'

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

# Verb/component tokens are intentionally no-op Make targets. The day0/d0
# recipe reads MAKECMDGOALS words 2 and 3 directly, so e.g.
# `make d0 check postgresql` needs "check" and "postgresql" to resolve to
# *something* as Make goals without erroring as unknown targets.
$(sort $(DAY0_VERBS) $(DAY0_COMPONENTS)):
	@:
