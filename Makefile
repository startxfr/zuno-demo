SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

ANSIBLE_PLAYBOOK ?= ansible-playbook
INVENTORY ?= ansible/inventories/demo/hosts.yml
EXTRA_VARS ?=

PREP_COMPONENTS := openshift-ai datascience nvidia-gpu argocd vault external-secrets keycloak postgresql observability smtp
CONFIG_SCOPES := vault external-secrets argocd datascience keycloak postgresql sql-schema models llm api mlops rag mcp
DISPATCH_TARGET := $(word 2,$(MAKECMDGOALS))

.PHONY: help precheck prepare configure install check credentials-check $(PREP_COMPONENTS) $(CONFIG_SCOPES)

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
	  '  make precheck                 Check all prerequisites' \
	  '  make precheck <component>     Check one prerequisite component' \
	  '  make prepare                  Install/prepare all prerequisites' \
	  '  make prepare <component>      Install/prepare one prerequisite component' \
	  '  make configure                Configure all platform scopes' \
	  '  make configure <scope>        Configure one platform scope' \
	  '  make install                  Install the agent platform and business definitions' \
	  '  make check                    Validate demo components and agents' \
	  '' \
	  'Prerequisite components: $(PREP_COMPONENTS)' \
	  'Configuration scopes:    $(CONFIG_SCOPES)'

credentials-check:
	@if [[ -z "$${K8S_AUTH_HOST:-}" || -z "$${K8S_AUTH_API_KEY:-}" ]]; then \
	  echo "K8S_AUTH_HOST and K8S_AUTH_API_KEY must be exported first - see 'make help'." >&2; \
	  exit 2; \
	fi

precheck: credentials-check
	@component="$${TARGET_COMPONENT:-$(DISPATCH_TARGET)}"; \
	if [[ -z "$$component" ]]; then component=all; fi; \
	case " $(PREP_COMPONENTS) all " in *" $$component "*) ;; *) echo "Unsupported precheck component: $$component" >&2; exit 2;; esac; \
	$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/precheck.yml -e "target_component=$$component" $(EXTRA_VARS)

prepare: credentials-check
	@component="$${TARGET_COMPONENT:-$(DISPATCH_TARGET)}"; \
	if [[ -z "$$component" ]]; then component=all; fi; \
	case " $(PREP_COMPONENTS) all " in *" $$component "*) ;; *) echo "Unsupported prepare component: $$component" >&2; exit 2;; esac; \
	$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/prepare.yml -e "target_component=$$component" $(EXTRA_VARS)

configure: credentials-check
	@scope="$${TARGET_SCOPE:-$(DISPATCH_TARGET)}"; \
	if [[ -z "$$scope" ]]; then scope=all; fi; \
	case " $(CONFIG_SCOPES) all " in *" $$scope "*) ;; *) echo "Unsupported configure scope: $$scope" >&2; exit 2;; esac; \
	$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/configure.yml -e "target_scope=$$scope" $(EXTRA_VARS)

install: credentials-check
	$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/install.yml $(EXTRA_VARS)

check: credentials-check
	$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) ansible/playbooks/check.yml $(EXTRA_VARS)

# Component/scope tokens are intentionally no-op Make targets. The first target
# reads the second goal and dispatches it to Ansible. This preserves commands
# such as `make precheck keycloak` without requiring COMPONENT=keycloak.
$(sort $(PREP_COMPONENTS) $(CONFIG_SCOPES)):
	@:
