
# Root directory for Makefile (where .env file should be)
ROOT_DIR := $(dir $(realpath $(lastword $(MAKEFILE_LIST))))
VENV_BIN := ${ROOT_DIR}/.venv/bin


.PHONY: install
install: ## Install the virtual environment and install the pre-commit hooks
	@echo "🚀 Checking environment"
	@command -v uv >/dev/null 2>&1 || { echo >&2 "uv is not installed. Please install it: https://github.com/astral-sh/uv"; exit 1; }
	@echo "🚀 Creating virtual environment using uv"
	@uv sync
	@uv run pre-commit install

.PHONY: check
check: ## Run code quality tools.
	@echo "🚀 Checking lock file consistency with 'pyproject.toml'"
	@uv lock --locked
	@echo "🚀 Linting code: Running pre-commit"
	@uv run pre-commit run -a

.PHONY: adk-web
adk: ## Run adk web
	@echo "🚀 Running adk web"
	@uv run adk web --reload_agents

.PHONY: adk-agentengine-web
adk-agentengine-web: ## Run adk web with remote agentengine
	@if [ -f "${ROOT_DIR}.agentengine.env" ]; then \
		echo "🚀 Running adk web"; \
		uv run adk web --session_service_uri "agentengine://$(cat .agentengine.env | cut -f2 -d'=')"; \
	else \
		echo "No Agentengine deployed"
	fi

.PHONY: undeploy
undeploy: ## Remove from agent and auth from Agentspace and delete AgentEngine instance
	@if [ -f "${ROOT_DIR}.agentspace_agent.env" ]; then \
		echo "🚀 Deleting Agentspace agent and auth"; \
		${VENV_BIN}/agentspace_manage agent delete && \
		${VENV_BIN}/agentspace_manage auth delete && \
		rm "${ROOT_DIR}.agentspace_agent.env"; \
	else \
		echo "No AgentSpace agent to delete."; \
	fi
	@if [ -f "${ROOT_DIR}.agentengine.env" ]; then \
		echo "🚀 Deleting AgentEngine instance"; \
		${VENV_BIN}/agentengine_manage delete --with-sessions && \
		rm "${ROOT_DIR}.agentengine.env"; \
	else \
		echo "No Agent to delete."; \
	fi

.PHONY: deploy
deploy: build undeploy ## Build and deploy to AgentEngine, create auth and agent
	@echo "🚀 Deploying wheel file"
	@${VENV_BIN}/agentengine_manage deploy --env AGENTSPACE_AUTH_ID --extra-packages dist/adk_jsm_agent-*.whl
	@echo "🚀 Testing remotely AgentEngine"
	@${VENV_BIN}/agentengine_manage remote-test
	@echo "🚀 Creating auth for Agentspace"
	@${VENV_BIN}/agentspace_manage auth create
	@echo "🚀 Creating agent for Agentspace"
	@${VENV_BIN}/agentspace_manage agent create

.PHONY: build
build: clean-build ## Build wheel file
	@echo "🚀 Creating wheel file"
	@uvx --from build pyproject-build --installer uv

.PHONY: clean-build
clean-build: ## Clean build artifacts
	@echo "🚀 Removing build artifacts"
	@uv run python -c "import shutil; import os; shutil.rmtree('dist') if os.path.exists('dist') else None"

.PHONY: test
test: ## Test the code with pytest
	@echo "🚀 Testing code: Running pytest"
	@uv run python -m pytest --cov --cov-config=pyproject.toml --cov-report=xml

.PHONY: help
help:
	@uv run python -c "import re; \
	[[print(f'\033[36m{m[0]:<20}\033[0m {m[1]}') for m in re.findall(r'^([a-zA-Z_-]+):.*?## (.*)$$', open(makefile).read(), re.M)] for makefile in ('$(MAKEFILE_LIST)').strip().split()]"

.DEFAULT_GOAL := help
