.PHONY: install test run clean

install:
	uv sync --all-extras

test:
	uv run pytest tests/ -v

run:
	uv run python -m charter_parser.main voyage-charter-example.pdf

run-debug:
	uv run python -m charter_parser.main voyage-charter-example.pdf --log-level DEBUG

clean:
	rm -rf output/clauses.json __pycache__ .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
