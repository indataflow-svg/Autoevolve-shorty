PYTHON ?= python3
# Prefer the project venv for script targets: the repo requires Python 3.12+.
VPY := $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo $(PYTHON); fi)
ARCHIVE ?=

.PHONY: setup setup-core setup-engines init doctor dev test lint check smoke email-worker-install backup restore verify-backup video-plan video-queue video-submit video-worker-status

setup: setup-core setup-engines init doctor

setup-core:
	@$(PYTHON) -c 'import sys; assert sys.version_info >= (3, 12), "Company Core requires Python 3.12+; run make setup PYTHON=python3.12"'
	$(PYTHON) -m venv .venv
	.venv/bin/python -m pip install --upgrade pip
	.venv/bin/python -m pip install -e ".[dev]"

setup-engines:
	PYTHON=$(PYTHON) ./scripts/install_engines.sh

init:
	./scripts/init_env.sh

doctor:
	.venv/bin/python scripts/doctor.py

dev:
	.venv/bin/python -m uvicorn app.api:app --reload --host 0.0.0.0 --port 8787

test:
	.venv/bin/python -m pytest

lint:
	.venv/bin/python -m ruff check app core services agents tools tests

check: lint test doctor

smoke:
	$(VPY) scripts/smoke_actions.py

video-plan:
	$(VPY) scripts/video.py plan --script $(SCRIPT)

video-queue:
	$(VPY) scripts/video.py queue $(PLAN)

video-submit:
	$(VPY) scripts/video.py submit $(JOB)

video-worker-status:
	$(VPY) scripts/video.py worker-status

backup:
	./scripts/backup.sh

restore:
	./scripts/restore.sh --verify --archive $(ARCHIVE)

verify-backup:
	$(VPY) scripts/verify_backup.py --archive $(ARCHIVE)

email-worker-install:
	npm --prefix company-sales-email-ingress ci
