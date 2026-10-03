# Multivendor automation lab: IOS XE / IOS XR / NX-OS on containerlab
SHELL        := /bin/bash
.SHELLFLAGS  := -eu -o pipefail -c
CHANGE       ?= sot/changes/loopback100.yml
VENV         ?= .venv
PYTHON_VER   ?= 3.12
PY           := $(VENV)/bin/python
PLAYBOOK     := $(VENV)/bin/ansible-playbook

# Image tags / NX-OS sizing come from lab.env (shell exports override it)
-include lab.env
TOPO         ?= topology/lab.clab.yml
LAB_VARS := C8KV_IMAGE N9KV_IMAGE N9KV_MEMORY N9KV_SMP XRD_IMAGE XRV9K_IMAGE GNMI_SKIP
export $(LAB_VARS)
CLAB_ENV := $(foreach v,$(LAB_VARS),$(if $($(v)),$(v)=$($(v))))
# clab_admins members run containerlab directly; otherwise pass vars via `sudo env`
# (works with classic sudo and Ubuntu 26.04's sudo-rs, which has no -E)
CLAB ?= $(if $(filter clab_admins,$(shell id -nG)),containerlab,sudo env $(CLAB_ENV) containerlab)
LAB_IPS := 172.30.30.11 172.30.30.12 172.30.30.13

WAIT_TIMEOUT ?= 1800

export ANSIBLE_CONFIG := $(CURDIR)/ansible.cfg
export PATH := $(CURDIR)/$(VENV)/bin:$(PATH)

.DEFAULT_GOAL := help
.PHONY: help deps env lint render deploy wait bootstrap configure dry-run validate change validate-change \
	    audit netconf restconf gnmi apis inspect graph ssh-xe ssh-xr ssh-nx destroy ci clean

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*## "}{printf "  \033[36m%-16s\033[0m %s\n",$$1,$$2}'

deps: ## Create Python 3.12 venv + install Python deps and Ansible collections
	uv venv --python $(PYTHON_VER) $(VENV)
	uv pip install --python $(PY) -r requirements.txt
	$(VENV)/bin/ansible-galaxy collection install -r ansible/requirements.yml -p ansible/collections

lint: ## Static checks (no lab needed)
	$(VENV)/bin/yamllint -c .yamllint topology sot ansible validation nr .gitlab-ci.yml
	shellcheck -S warning scripts/*.sh api/gnmi_check.sh
	$(PY) -m py_compile nr/*.py api/*.py validation/*.py
	$(PY) scripts/render_templates.py >/dev/null && echo "templates render OK"

render: ## Print rendered day-1 configs (CHANGE=... to include a change set)
	$(PY) scripts/render_templates.py $(if $(filter command line,$(origin CHANGE)),--change $(CHANGE))

env: ## Show image/sizing variables passed to containerlab
	@$(foreach v,$(LAB_VARS),echo "$(v)=$($(v))";)

deploy: ## Deploy the topology
	$(CLAB) deploy -t $(TOPO) --reconfigure
	@for ip in $(LAB_IPS); do ssh-keygen -R $$ip >/dev/null 2>&1 || true; done

wait: ## Poll until every node answers over SSH
	$(PY) nr/wait_ready.py --timeout $(WAIT_TIMEOUT)

bootstrap: ## Day-0: enable NETCONF/RESTCONF/gNMI
	$(PLAYBOOK) ansible/playbooks/bootstrap.yml

configure: ## Day-1: push intent from sot/fabric.yml
	$(PLAYBOOK) ansible/playbooks/configure.yml --diff

dry-run: ## Show what configure would change
	$(PLAYBOOK) ansible/playbooks/configure.yml --check --diff

validate: ## pyATS validation of baseline intent
	$(PY) validation/validate.py --label baseline

change: ## Apply change set $(CHANGE)
	$(PLAYBOOK) ansible/playbooks/configure.yml --diff -e @$(CHANGE)

validate-change: ## pyATS validation including change set
	$(PY) validation/validate.py --label change --change $(CHANGE)

audit: ## Nornir: backup configs + compliance audit
	$(PY) nr/backup_and_audit.py

netconf: ## NETCONF smoke test (all platforms)
	$(PY) api/netconf_get.py

restconf: ## RESTCONF smoke test (XE + NX-OS)
	$(PY) api/restconf_get.py

gnmi: ## gNMI smoke test (all platforms)
	bash api/gnmi_check.sh

apis: netconf restconf gnmi ## All model-driven API checks

inspect: ## Show running nodes and mgmt IPs
	$(CLAB) inspect -t $(TOPO)

graph: ## Web topology graph on :50080
	$(CLAB) graph -t $(TOPO)

ssh-xe: ; ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null admin@172.30.30.11
ssh-xr: ; ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null clab@172.30.30.12
ssh-nx: ; ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null admin@172.30.30.13

destroy: ## Destroy the lab and remove its directory
	$(CLAB) destroy -t $(TOPO) --cleanup

ci: ## Full scripted pipeline (deploy -> ... -> destroy)
	TOPO=$(TOPO) ./scripts/ci.sh

clean: ## Remove generated artifacts
	rm -rf reports backups

print-topo: ## Print the topology in use
	@echo $(TOPO)
