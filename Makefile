.PHONY: setup build build-invoice check

setup:
	uv sync

build:
	uv run python -m houjin_analytics

build-invoice:
	uv run python -m houjin_analytics.invoice

check:
	uv run ruff check .
	uv run mypy
	uv run pytest -q
