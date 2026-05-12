# Repository Guidelines

## Project Structure & Module Organization

This repository contains a Python project for calculating and publishing a KOSPI Fear & Greed Index. Core code lives under `module/`:

- `module/main.py` is the main CLI for scraping data, computing the index, and updating outputs.
- `module/data/` contains scrapers and processing logic.
- `module/config/settings.py` stores paths, URLs, headers, and index parameters.
- `module/utils/` contains database and helper utilities.
- `module/db/` stores local SQLite databases and related reports.
- `module/json/` contains generated JSON outputs.
- `assets/js/` contains browser-consumable JavaScript data files.

Run commands from `module/` unless a command explicitly states otherwise, because several paths are relative to `./db` and `./json`.

## Build, Test, and Development Commands

No package manager metadata is currently checked in. Create an isolated environment and install inferred dependencies before running scripts:

```bash
python -m venv .venv
source .venv/bin/activate
pip install pandas numpy requests beautifulsoup4 pykrx PyGithub scipy scikit-learn matplotlib seaborn
cd module
python main.py --skip-scrape
python main.py --force-update
python run_optimization.py
python test_optimization.py
```

- `python main.py --skip-scrape` recalculates from existing database data.
- `python main.py --force-update` refreshes all supported data sources.
- `python run_optimization.py` starts the interactive parameter optimization workflow.
- `python test_optimization.py` runs the current smoke/integration test script.

## Coding Style & Naming Conventions

Use standard Python style: 4-space indentation, `snake_case` for functions and variables, `CapWords` for classes, and constants in `UPPER_SNAKE_CASE`. Keep Korean domain comments where they clarify financial logic, but write new public-facing documentation in clear English or Korean consistently. Prefer small functions around scraping, processing, and database boundaries.

## Testing Guidelines

The repository currently uses script-based tests rather than `pytest`. Add new tests as executable Python scripts or migrate related checks to `pytest` when adding broader coverage. Name test files `test_*.py`. Tests should avoid live network calls when possible and should document any required database fixture in `module/db/`.

## Commit & Pull Request Guidelines

Git history includes short messages such as `Add KOSPI fear greed module` and repeated `committing files`; prefer more descriptive, imperative intent lines going forward. Pull requests should include: a summary of behavior changes, commands run, affected data files (`module/json/`, `assets/js/`), and screenshots or sample output when visual/index results change.

## Security & Configuration Tips

Do not commit credentials. `GITHUB_TOKEN` is read from the environment in `module/config/settings.py`. Treat SQLite databases and generated JSON as data artifacts; explain intentional updates in the PR description.
