.PHONY: bootstrap lint typecheck test-unit test-integration ui-test check

bootstrap:
	uv sync --all-packages

lint:
	uv run ruff format --check .
	uv run ruff check .

typecheck:
	uv run mypy domain tests

test-unit:
	uv run pytest -m "not integration and not e2e and not infrastructure and not performance" --disable-socket -q

test-integration:
	uv run pytest -m integration --enable-socket -q

ui-test:
	uv run pytest -m ui --enable-socket -q

check: lint typecheck test-unit

