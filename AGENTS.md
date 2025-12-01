# Repository Guidelines

## Project Structure & Module Organization
- `datas/` handles ingestion, SQLite setup (`database/ashare_data.db`), and market data fetchers; start with `create_database.py` and `fetch_all_market.py`.
- `hunters/` contains reusable analyzers; `hunt_machine.py` orchestrates threaded scans and plugs in strategy modules such as `strategy_breakout_pullback.py`.
- `workflow/` provides ready-to-run jobs (e.g., `hunt_breakout_pullback.py`) that stitch together ingestion and analytics, storing artifacts under `output/`.
- `cli/stock_info.py` exposes the lightweight CLI entry point used by `setup.py`, while `tools/` centralizes logging, timing, and export utilities.
- `tests/` holds pytest suites; treat them as integration checks that exercise the live database.

## Build, Test, and Development Commands
- `python -m venv .venv && source .venv/bin/activate` creates an isolated environment; always work activated.
- `pip install -r requirements.txt` brings in data vendors (Akshare, Tushare) and support libs; follow with `pip install -e .` to register `stock-info`.
- `python workflow/daily_market.py` refreshes baseline market data; `python workflow/hunt_breakout_pullback.py` runs the flagship screening flow and saves CSV results.
- `python cli/stock_info.py --help` previews CLI usage; favor module execution (`python -m workflow.hunt_breakout_pullback`) when packaging matters.
- `pytest -k hunt_machine -s` runs the current test suite with console logging so you can watch threaded workers.

## Coding Style & Naming Conventions
- Stick to PEP 8: four-space indents, snake_case for modules/functions, CamelCase for classes such as `HuntMachine`.
- Keep type hints and docstrings consistent with existing code; prefer explicit return typing for analyzers and data access layers.
- Use `tools.log.get_fetch_logger()` or `get_analyze_logger()` instead of creating raw loggers so output flows to `logs/`.
- Persist intermediate artifacts under `output/` and avoid committing large CSV snapshots; redact credentials from checked-in files.

## Testing Guidelines
- Pytest is the expected runner; structure new tests under `tests/` mirroring the target module name (`test_<module>.py`).
- Seed the SQLite cache first (`python datas/fetch_all_market.py`) so integration tests can query realistic bars.
- When mocking data, follow the existing pattern in `tests/test_hunt_machine.py` that patches `query_all_stock_code_list` to bound runtime.
- Aim to verify both selection results and log behavior; capture emitted warnings when introducing new failure modes.

## Commit & Pull Request Guidelines
- Follow the repo’s concise, present-tense commit style (`latest trade day`, `volume ma`); one focused change per commit.
- Describe what changed and why in the PR description, link related issues, and paste sample command output or CSV snippets proving the behavior.
- Confirm virtualenv activation, data refresh, and `pytest` completion before requesting review; surface any remaining data prerequisites up front.

## Data & Configuration Notes
- Secrets live in `.env`; avoid hard-coding Tushare tokens beyond `config.py` scaffolding and document any new keys you require.
- Ensure database migrations stay backward compatible—extend the schema via `create_database.py` helpers and note rebuild steps in the PR.
- Log files in `logs/` grow quickly; rotate or trim during experiments and keep repository history clean of generated logs.
