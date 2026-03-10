.PHONY: help install test lint clean

help: ## Show available targets
	@grep -E '^[a-zA-Z_/%-]+:.*## ' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  %-20s %s\n", $$1, $$2}'

install: ## Install package with dev dependencies
	uv pip install -e ".[dev]"

test: ## Run tests
	uv run --extra dev pytest tests/ -v

lint: ## Check Python syntax
	find src -name '*.py' -exec uv run python -m py_compile {} +

clean: ## Remove build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	rm -rf *.egg-info .pytest_cache .venv
