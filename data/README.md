# Data directory

The data is separated by lifecycle stage so dashboard-ready tables are not mixed with source files and experiments.

## `processed/`

Final, tracked Parquet tables consumed by `src/dashboard.py` and the analysis notebooks:

- `game_info.parquet` — one row per analyzed game.
- `game_history.parquet` — cleaned Steam price-change events.
- `game_tags.parquet` — game-to-tag bridge table.
- `game_tags_15.parquet` — tag-filter table used by the dashboard.
- `days_first_discount.parquet` — first observed discount timing by game.

## `interim/`

Outputs passed between pipeline stages:

- `game_list.parquet` — resolved title-to-ITAD-ID mapping; tracked.
- `game_info.csv` — fetched metadata staging table; generated and ignored.
- `game_history.csv` — fetched price-event staging table; generated and ignored.

Generated CSV files are ignored because they can be large and are not dashboard inputs.

## `raw/`

Local source material and API caches. This directory is ignored by Git.

- `steamdb_rating_tiers/` — manually collected title lists.
- `itad/game_info/` — cached ITAD metadata responses.
- `itad/price_history/` — cached ITAD price-history responses.

## `archive/`

Superseded or duplicate artifacts retained for safety. Nothing in this directory is used by the active dashboard or pipeline.
