.PHONY: bootstrap lint typecheck test-unit test-integration ui-test check

bootstrap:
	uv sync --all-packages

lint:
	uv run ruff format --check .
	uv run ruff check .

typecheck:
	uv run mypy domain packages services tests

test-unit:
	uv run pytest -m "not integration and not e2e and not infrastructure and not performance" --disable-socket --allow-unix-socket -q

test-integration:
	uv run pytest -m integration -q

ui-test:
	uv run pytest -m ui -q

check: lint typecheck test-unit
