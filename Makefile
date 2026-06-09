# Daily Stock Analysis — task runner.
# Run `make` or `make help` to list all commands.
SHELL := bash
PYTHON ?= python
WEB := apps/dsa-web
S ?=
R ?= cn

.DEFAULT_GOAL := help
.PHONY: help install serve dev web analyze review schedule test gate web-test web-build lint clean

help: ## List available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install backend (pip) + web (npm) dependencies
	pip install -r requirements.txt
	cd $(WEB) && npm ci

serve: ## Run the web app (FastAPI serves the built frontend) at http://localhost:8000
	$(PYTHON) main.py --serve-only

dev: ## Run backend (:8000) + web dev server (:5173) together (Ctrl+C stops both)
	@trap 'kill 0' EXIT; \
	$(PYTHON) main.py --serve-only & \
	(cd $(WEB) && npm run dev) & \
	wait

web: ## Run only the web dev server (Vite, :5173, proxies /api -> :8000)
	cd $(WEB) && npm run dev

analyze: ## Analyze stocks (make analyze S=tw2330,tw0050,AAPL); empty S uses STOCK_LIST
	@if [ -n "$(S)" ]; then $(PYTHON) main.py --stocks "$(S)"; else $(PYTHON) main.py; fi

review: ## Market review (make review R=tw  | cn/hk/us/tw/both)
	MARKET_REVIEW_REGION="$(R)" $(PYTHON) main.py --market-review

schedule: ## Run the built-in scheduler (daily tasks)
	$(PYTHON) main.py --schedule

test: ## Backend offline tests: pytest -m 'not network'
	$(PYTHON) -m pytest -m "not network"

gate: ## Backend CI gate (./scripts/ci_gate.sh: syntax + critical flake8)
	./scripts/ci_gate.sh

lint: ## Backend critical lint (flake8 E9/F63/F7/F82)
	flake8 . --select=E9,F63,F7,F82 --show-source --statistics

web-test: ## Web checks: eslint + tsc typecheck + vitest
	cd $(WEB) && npm run lint && npx tsc -b --noEmit && npm run test

web-build: ## Build the web frontend (outputs to static/)
	cd $(WEB) && npm run build

clean: ## Remove Python caches and the web build output
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf $(WEB)/dist
