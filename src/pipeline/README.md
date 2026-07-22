# Data pipeline

The numbered notebooks describe the intended workflow:

1. `01_clean_titles.ipynb` cleans the manually collected SteamDB title lists into `data/interim/new_game_list.csv`.
2. `02_resolve_itad_ids.ipynb` resolves titles to ITAD IDs and writes `data/interim/game_list.parquet`.
3. `03_fetch_game_info.ipynb` fetches metadata into the ITAD info cache and `data/interim/game_info.csv`.
4. `04_fetch_price_history.ipynb` fetches price events into the ITAD history cache and `data/interim/game_history.csv`.
5. `05_build_core_tables.ipynb` builds `data/processed/game_info.parquet` and `game_tags.parquet`.
6. `06_enrich_game_info.ipynb` adds cached Early Access and peak-player fields to the processed game table.

`constants.py` is local and ignored by Git because it contains the ITAD API key. Run pipeline notebooks from this directory so their `../../data/` paths and local import resolve correctly.

Install `requirements-dev.txt` from the repository root before running the pipeline or analysis notebooks. `requirements.txt` remains limited to the deployed dashboard.

The current notebooks document the historical pipeline. A future cleanup should convert them into restartable Python modules with explicit validation between stages.
