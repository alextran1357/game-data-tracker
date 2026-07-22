# Data pipeline

The numbered notebooks describe the intended workflow:

1. `01_clean_titles.ipynb` cleans the manually collected SteamDB title lists into `data/interim/new_game_list.csv`.
2. `02_resolve_itad_ids.ipynb` resolves titles to ITAD IDs and writes `data/interim/game_list.parquet`.
3. `03_fetch_game_info.ipynb` fetches metadata into the ITAD info cache and `data/interim/game_info.csv`.
4. `04_fetch_price_history.ipynb` fetches price events into the ITAD history cache and `data/interim/game_history.csv`.
5. `05_build_core_tables.ipynb` builds `data/processed/game_info.parquet` and `game_tags.parquet`.
6. `06_enrich_game_info.ipynb` adds cached Early Access and peak-player fields to the processed game table.
7. `build_analysis_tables.py` converts the resolved mapping and processed source tables into four validated analysis-ready tables under `data/processed/analytics/`.
8. `validate_analysis_data.py` enforces the table contracts and writes generated quality flags and `reports/data_quality_report.md`.

Run the analysis-table builder from the repository root:

```powershell
python src/pipeline/build_analysis_tables.py
python src/pipeline/validate_analysis_data.py
```

The builder creates:

- `dim_game.parquet` — one row per resolved game ID.
- `fact_price_event.parquet` — one row per distinct observed price record.
- `fact_discount_event.parquet` — one row per valid discounted observation.
- `game_discount_summary.parquet` — one row per game with analysis-ready discount metrics.

When `data/interim/game_history.csv` is available, the builder uses that complete Steam/USD staging history. This restores valid high-price observations that the older processed history removed with an arbitrary $70 ceiling. The tracked processed history remains a fallback when the staging file is unavailable.

The validation step checks table grains, source scope, discount calculations, cohort eligibility, censoring, and follow-up windows. It produces:

- `data/processed/quality/game_quality_flags.parquet`
- `data/processed/quality/price_event_quality_flags.parquet`
- `reports/data_quality_report.md`

`constants.py` is local and ignored by Git because it contains the ITAD API key. Run pipeline notebooks from this directory so their `../../data/` paths and local import resolve correctly.

Install `requirements-dev.txt` from the repository root before running the pipeline or analysis notebooks. `requirements.txt` remains limited to the deployed dashboard.

The notebooks document the historical collection pipeline. The two Python scripts are the repeatable transformation and validation entry points for the redesigned analysis.
