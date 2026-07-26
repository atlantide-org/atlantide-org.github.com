.PHONY: deps docs docs-serve

deps:  ## Install the docs toolchain
	uv sync --extra docs

docs: deps  ## Build the documentation site -> site/
	uv run mkdocs build --strict

docs-serve: deps  ## Serve the docs with live reload on http://127.0.0.1:8000/
	uv run mkdocs serve
