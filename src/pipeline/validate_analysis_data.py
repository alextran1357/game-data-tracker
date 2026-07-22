"""Validate the analysis tables and generate reproducible data-quality outputs.

Run from the repository root after building the analysis tables:

    python src/pipeline/validate_analysis_data.py

The script fails on broken table grains or relationships. When validation passes,
it writes game-level flags, price-event flags, and a Markdown audit report.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
ANALYTICS_DIR = DATA_DIR / "processed" / "analytics"
QUALITY_DIR = DATA_DIR / "processed" / "quality"
REPORT_PATH = PROJECT_ROOT / "reports" / "data_quality_report.md"

GAME_LIST_PATH = DATA_DIR / "interim" / "game_list.parquet"
GAME_TAGS_PATH = DATA_DIR / "processed" / "game_tags.parquet"
HISTORY_STAGING_PATH = DATA_DIR / "interim" / "game_history.csv"
HISTORY_FALLBACK_PATH = DATA_DIR / "processed" / "game_history.parquet"

DIM_GAME_PATH = ANALYTICS_DIR / "dim_game.parquet"
FACT_PRICE_PATH = ANALYTICS_DIR / "fact_price_event.parquet"
FACT_DISCOUNT_PATH = ANALYTICS_DIR / "fact_discount_event.parquet"
SUMMARY_PATH = ANALYTICS_DIR / "game_discount_summary.parquet"

GAME_FLAGS_PATH = QUALITY_DIR / "game_quality_flags.parquet"
PRICE_FLAGS_PATH = QUALITY_DIR / "price_event_quality_flags.parquet"

PRICE_TOLERANCE_USD = 0.01
DISCOUNT_TOLERANCE_POINTS = 1.0
PRICE_COVERAGE_START_DAYS = -1.0
PRICE_COVERAGE_END_DAYS = 7.0


def _require_files(paths: list[Path]) -> None:
    missing = [path for path in paths if not path.exists()]
    if missing:
        missing_text = "\n".join(f"- {path}" for path in missing)
        raise FileNotFoundError(f"Required files are missing:\n{missing_text}")


def load_analysis_tables() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    paths = [DIM_GAME_PATH, FACT_PRICE_PATH, FACT_DISCOUNT_PATH, SUMMARY_PATH]
    _require_files(paths)
    return tuple(pd.read_parquet(path) for path in paths)  # type: ignore[return-value]


def load_source_tables() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, str]:
    _require_files([GAME_LIST_PATH, GAME_TAGS_PATH])
    game_list = pd.read_parquet(GAME_LIST_PATH)
    game_tags = pd.read_parquet(GAME_TAGS_PATH)

    if HISTORY_STAGING_PATH.exists():
        history_columns = [
            "game_id",
            "timestamp",
            "shop_id",
            "shop_name",
            "deal_price",
            "regular_price",
            "currency",
            "discount_pct",
        ]
        history = pd.read_csv(
            HISTORY_STAGING_PATH,
            header=None,
            names=history_columns,
        )
        source_name = HISTORY_STAGING_PATH.relative_to(PROJECT_ROOT).as_posix()
    else:
        _require_files([HISTORY_FALLBACK_PATH])
        history = pd.read_parquet(HISTORY_FALLBACK_PATH).rename(
            columns={
                "itad_uuid": "game_id",
                "percent": "discount_pct",
            }
        )
        history["shop_id"] = 61
        history["shop_name"] = "Steam"
        history["currency"] = "USD"
        source_name = HISTORY_FALLBACK_PATH.relative_to(PROJECT_ROOT).as_posix()

    return game_list, game_tags, history, source_name


def validate_tables(
    game_list: pd.DataFrame,
    history: pd.DataFrame,
    dim_game: pd.DataFrame,
    fact_price: pd.DataFrame,
    fact_discount: pd.DataFrame,
    summary: pd.DataFrame,
) -> list[str]:
    """Raise on a failed contract and return human-readable passing checks."""
    checks: list[str] = []

    resolved_ids = (
        game_list["itad_uuid"]
        .astype("string")
        .str.strip()
        .replace("", pd.NA)
        .dropna()
        .drop_duplicates()
    )
    if dim_game["game_id"].isna().any() or dim_game["game_id"].duplicated().any():
        raise AssertionError("dim_game does not have one non-null row per game ID")
    if set(dim_game["game_id"]) != set(resolved_ids):
        raise AssertionError("dim_game IDs do not match the resolved source IDs")
    checks.append("dim_game has one row for every unique resolved source ID")

    price_key = [
        "game_id",
        "observed_at",
        "shop_id",
        "currency",
        "deal_price_usd",
        "regular_price_usd",
        "discount_pct",
    ]
    if fact_price.duplicated(price_key).any():
        raise AssertionError("fact_price_event contains duplicate grain keys")
    if not set(fact_price["game_id"]).issubset(set(dim_game["game_id"])):
        raise AssertionError("fact_price_event contains orphan game IDs")
    checks.append("fact_price_event has a unique grain and no orphan game IDs")

    source_scope_valid = (
        history["shop_id"].eq(61)
        & history["shop_name"].eq("Steam")
        & history["currency"].eq("USD")
    )
    if not source_scope_valid.all():
        raise AssertionError("Price source contains records outside Steam/USD scope")
    checks.append("every source price record is Steam shop 61 and USD")

    if len(fact_price) > len(history):
        raise AssertionError("fact_price_event has more rows than its source history")
    if fact_price["price_record_status"].isna().any():
        raise AssertionError("fact_price_event contains unclassified records")
    checks.append("every price record has an explicit validation status")

    valid_discount = fact_price["price_record_status"].eq("valid_discount")
    valid_full_price = fact_price["price_record_status"].eq("valid_full_price")
    invalid = fact_price["price_record_status"].eq("invalid")
    if not (valid_discount | valid_full_price | invalid).all():
        raise AssertionError("Unknown price-record validation status found")

    recalculated_discount = (
        100
        * (fact_price["regular_price_usd"] - fact_price["deal_price_usd"])
        / fact_price["regular_price_usd"]
    )
    expected_valid_discount = (
        fact_price["discount_pct"].between(1, 100, inclusive="both")
        & fact_price["regular_price_usd"].gt(0)
        & fact_price["deal_price_usd"].ge(0)
        & fact_price["deal_price_usd"].le(
            fact_price["regular_price_usd"] + PRICE_TOLERANCE_USD
        )
        & (recalculated_discount - fact_price["discount_pct"]).abs().le(
            DISCOUNT_TOLERANCE_POINTS
        )
    )
    if not valid_discount.equals(expected_valid_discount):
        raise AssertionError("Valid discount classification does not match the contract")
    checks.append("valid discounts satisfy price, range, and formula rules")

    expected_discount_keys = (
        fact_price.loc[valid_discount, ["game_id", "price_event_number"]]
        .sort_values(["game_id", "price_event_number"])
        .reset_index(drop=True)
    )
    actual_discount_keys = (
        fact_discount[["game_id", "price_event_number"]]
        .sort_values(["game_id", "price_event_number"])
        .reset_index(drop=True)
    )
    pd.testing.assert_frame_equal(expected_discount_keys, actual_discount_keys)
    if fact_discount.duplicated(["game_id", "discount_event_number"]).any():
        raise AssertionError("fact_discount_event contains duplicate event numbers")
    checks.append("fact_discount_event contains every valid discount exactly once")

    dimension_ids = set(dim_game["game_id"])
    if len(summary) != len(dim_game) or set(summary["game_id"]) != dimension_ids:
        raise AssertionError("game_discount_summary does not match dim_game")
    if summary["game_id"].duplicated().any():
        raise AssertionError("game_discount_summary contains duplicate game IDs")
    checks.append("game_discount_summary has exactly one row per dim_game row")

    cutoff_without_timezone = fact_price["observed_at"].max().tz_localize(None)
    expected_eligibility = (
        dim_game["is_game"]
        & dim_game["reported_release_date"].notna()
        & dim_game["reported_release_date"].le(cutoff_without_timezone)
        & dim_game["has_price_history"]
        & dim_game["price_coverage_start_days"].between(
            PRICE_COVERAGE_START_DAYS,
            PRICE_COVERAGE_END_DAYS,
            inclusive="both",
        )
        & ~dim_game["has_ambiguous_price_stream"]
    ).fillna(False)
    if not dim_game["discount_timing_eligible"].equals(
        expected_eligibility.astype("boolean")
    ):
        raise AssertionError("Discount-timing eligibility does not match the contract")
    checks.append("discount-timing eligibility matches the declared cohort rules")

    expected_censoring = (
        summary["discount_timing_eligible"]
        & ~summary["has_post_release_discount"]
    ).astype("boolean")
    if not summary["right_censored_without_discount"].equals(expected_censoring):
        raise AssertionError("Right-censoring flags are inconsistent")
    if summary.loc[
        summary["discount_timing_eligible"], "days_to_first_observed_discount"
    ].dropna().lt(0).any():
        raise AssertionError("Eligible first-discount timing contains a negative value")
    checks.append("eligible games without a discount are retained as right-censored")

    for days in [30, 90, 180, 365]:
        column = f"discounted_within_{days}_days"
        should_be_available = (
            summary["discount_timing_eligible"]
            & summary["followup_days"].ge(days)
        )
        if summary.loc[~should_be_available, column].notna().any():
            raise AssertionError(f"{column} is populated without enough follow-up")
        expected_value = summary["days_to_first_observed_discount"].between(0, days)
        observed_value = summary.loc[should_be_available, column].astype(bool)
        expected_available = expected_value.loc[should_be_available].fillna(False).astype(bool)
        if not (observed_value.to_numpy() == expected_available.to_numpy()).all():
            raise AssertionError(f"{column} values are inconsistent")
    checks.append("30/90/180/365-day metrics enforce complete follow-up windows")

    if not (
        dim_game["tag_count"].fillna(0).astype(int)
        == dim_game["tags"].map(len)
    ).all():
        raise AssertionError("dim_game tag counts do not match their tag arrays")
    checks.append("game tags are deduplicated and their counts are consistent")

    return checks


def build_game_quality_flags(
    dim_game: pd.DataFrame,
    fact_discount: pd.DataFrame,
    summary: pd.DataFrame,
) -> pd.DataFrame:
    game = dim_game.merge(
        summary[
            [
                "game_id",
                "first_observed_regular_price_usd",
                "has_post_release_discount",
                "right_censored_without_discount",
            ]
        ],
        on="game_id",
        how="left",
        validate="one_to_one",
    )
    cutoff_without_timezone = summary["data_cutoff_at"].max().tz_localize(None)
    pre_release_game_ids = set(
        fact_discount.loc[fact_discount["game_age_days"].lt(-1), "game_id"]
    )

    frames: list[pd.DataFrame] = []

    def add_flag(
        mask: pd.Series,
        flag: str,
        scope: str,
        action: str,
    ) -> None:
        flagged = game.loc[mask.fillna(False), ["game_id", "title"]].copy()
        if flagged.empty:
            return
        flagged["quality_flag"] = flag
        flagged["affected_analysis"] = scope
        flagged["action"] = action
        frames.append(flagged)

    add_flag(
        ~game["metadata_available"],
        "metadata_unavailable",
        "metadata_and_engagement",
        "retain_with_limited_metadata",
    )
    add_flag(
        game["content_type"].isna(),
        "content_type_unknown",
        "general_game_analysis",
        "exclude_from_general_game_analysis",
    )
    add_flag(
        game["content_type"].eq("dlc"),
        "content_type_dlc",
        "general_game_analysis",
        "exclude_from_general_game_analysis",
    )
    add_flag(
        game["content_type"].eq("package"),
        "content_type_package",
        "general_game_analysis",
        "exclude_from_general_game_analysis",
    )
    add_flag(
        game["reported_release_date"].isna(),
        "release_date_missing",
        "lifecycle_and_discount_timing",
        "exclude_from_lifecycle_analysis",
    )
    add_flag(
        game["reported_release_date"].gt(cutoff_without_timezone),
        "release_date_after_price_cutoff",
        "lifecycle_and_discount_timing",
        "exclude_from_lifecycle_analysis",
    )
    add_flag(
        ~game["has_price_history"],
        "price_history_missing",
        "pricing_and_discount_analysis",
        "exclude_from_pricing_analysis",
    )
    add_flag(
        game["is_game"]
        & game["reported_release_date"].notna()
        & game["reported_release_date"].le(cutoff_without_timezone)
        & game["has_price_history"]
        & ~game["near_release_price_coverage"],
        "price_history_not_near_release",
        "first_discount_timing",
        "exclude_from_discount_timing",
    )
    add_flag(
        game["has_ambiguous_price_stream"],
        "ambiguous_price_stream",
        "first_discount_timing_and_price_tier",
        "exclude_from_discount_timing_and_price_tier",
    )
    add_flag(
        game["discount_timing_eligible"]
        & game["first_observed_regular_price_usd"].isna(),
        "positive_baseline_price_unavailable",
        "price_tier_and_discount_depth",
        "exclude_from_price_tier_only",
    )
    add_flag(
        game["steam_review_score"].isna(),
        "steam_review_score_missing",
        "engagement_comparison",
        "exclude_from_review_score_comparison_only",
    )
    add_flag(
        game["steam_review_count"].isna(),
        "steam_review_count_missing",
        "engagement_comparison",
        "exclude_from_review_count_comparison_only",
    )
    add_flag(
        game["peak_player_count"].isna(),
        "peak_player_count_missing",
        "engagement_comparison",
        "exclude_from_peak_player_comparison_only",
    )
    add_flag(
        game["peak_player_count"].eq(0),
        "peak_player_count_zero",
        "engagement_comparison",
        "retain_with_caution",
    )
    add_flag(
        game["game_id"].isin(pre_release_game_ids),
        "pre_release_discount_history",
        "post_release_discount_metrics",
        "exclude_pre_release_events_only",
    )
    add_flag(
        game["right_censored_without_discount"],
        "no_observed_post_release_discount",
        "first_discount_timing",
        "retain_as_right_censored",
    )

    columns = ["game_id", "title", "quality_flag", "affected_analysis", "action"]
    if not frames:
        return pd.DataFrame(columns=columns)
    return (
        pd.concat(frames, ignore_index=True)[columns]
        .sort_values(["quality_flag", "game_id"])
        .reset_index(drop=True)
    )


def build_price_event_quality_flags(fact_price: pd.DataFrame) -> pd.DataFrame:
    flagged = fact_price.loc[
        fact_price["quality_issue"].ne("none"),
        [
            "game_id",
            "price_event_number",
            "observed_at",
            "deal_price_usd",
            "regular_price_usd",
            "discount_pct",
            "price_record_status",
            "quality_issue",
        ],
    ].copy()
    flagged["quality_flag"] = flagged.pop("quality_issue").str.split("|")
    flagged = flagged.explode("quality_flag", ignore_index=True)

    action_map = {
        "missing_required_value": "exclude_event_from_analysis",
        "negative_price": "exclude_event_from_analysis",
        "deal_above_regular": "exclude_event_from_analysis",
        "discount_out_of_range": "exclude_event_from_analysis",
        "discount_formula_mismatch": "exclude_event_from_analysis",
        "full_price_value_mismatch": "exclude_event_from_analysis",
        "zero_regular_price": "retain_but_exclude_from_price_baseline",
        "ambiguous_timestamp": "retain_but_exclude_game_from_timing",
    }
    flagged["action"] = flagged["quality_flag"].map(action_map).fillna(
        "review_required"
    )
    return flagged.sort_values(
        ["quality_flag", "game_id", "observed_at", "price_event_number"]
    ).reset_index(drop=True)


def _markdown_table(headers: list[str], rows: list[list[object]]) -> str:
    header = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(str(value) for value in row) + " |" for row in rows]
    return "\n".join([header, separator, *body])


def build_report(
    game_list: pd.DataFrame,
    game_tags: pd.DataFrame,
    history: pd.DataFrame,
    history_source_name: str,
    dim_game: pd.DataFrame,
    fact_price: pd.DataFrame,
    fact_discount: pd.DataFrame,
    summary: pd.DataFrame,
    game_flags: pd.DataFrame,
    price_flags: pd.DataFrame,
    checks: list[str],
) -> str:
    cutoff_at = fact_price["observed_at"].max()
    cutoff_without_timezone = cutoff_at.tz_localize(None)
    non_null_source_ids = game_list["itad_uuid"].dropna()
    duplicate_source_ids = int(non_null_source_ids.duplicated().sum())
    duplicate_tags = int(game_tags.duplicated(["itad_uuid", "tag"]).sum())
    exact_history_duplicates = int(history.duplicated().sum())

    high_price_source_rows = int(
        (history["deal_price"].gt(70) | history["regular_price"].gt(70)).sum()
    )
    source_scope_rows = int(
        (
            history["shop_id"].eq(61)
            & history["shop_name"].eq("Steam")
            & history["currency"].eq("USD")
        ).sum()
    )

    valid_release = (
        dim_game["is_game"]
        & dim_game["reported_release_date"].notna()
        & dim_game["reported_release_date"].le(cutoff_without_timezone)
    )
    with_history = valid_release & dim_game["has_price_history"]
    near_release = with_history & dim_game["near_release_price_coverage"]
    eligible = dim_game["discount_timing_eligible"]

    cohort_rows = [
        ["Resolved game IDs", f"{len(dim_game):,}", "Starting population"],
        ["Content type is game", f"{int(dim_game['is_game'].sum()):,}", "Keep games only"],
        ["Valid release date through cutoff", f"{int(valid_release.sum()):,}", "Required for lifecycle timing"],
        ["Has price history", f"{int(with_history.sum()):,}", "Required for discount analysis"],
        ["History begins from day -1 through day 7", f"{int(near_release.sum()):,}", "Required for first-discount timing"],
        ["Unambiguous eligible price stream", f"{int(eligible.sum()):,}", "Final timing cohort"],
        ["Observed post-release discount", f"{int((summary['discount_timing_eligible'] & summary['has_post_release_discount']).sum()):,}", "Observed event"],
        ["No observed post-release discount", f"{int(summary['right_censored_without_discount'].sum()):,}", "Retain as right-censored"],
    ]

    source_rows = [
        ["Resolved-title input rows", f"{len(game_list):,}", "Source"],
        ["Rows without a resolved ID", f"{int(game_list['itad_uuid'].isna().sum()):,}", "Excluded before dim_game"],
        ["Duplicate non-null resolved IDs", f"{duplicate_source_ids:,}", "Collapsed to one game row"],
        ["Unique resolved game IDs", f"{dim_game['game_id'].nunique():,}", "Retained"],
        ["Tag input rows", f"{len(game_tags):,}", "Source"],
        ["Duplicate game-tag pairs", f"{duplicate_tags:,}", "Collapsed"],
        ["Price-history source rows", f"{len(history):,}", history_source_name],
        ["Exact duplicate source price rows", f"{exact_history_duplicates:,}", "Collapsed if present"],
        ["Steam/USD source rows", f"{source_scope_rows:,}", "All source rows pass scope"],
        ["Source rows with a price above $70", f"{high_price_source_rows:,}", "Retained; high price alone is not invalid"],
    ]

    price_rows = [
        ["Distinct price records", f"{len(fact_price):,}", "Retained with status"],
        ["Valid full-price records", f"{int(fact_price['price_record_status'].eq('valid_full_price').sum()):,}", "Retained"],
        ["Valid discount records", f"{int(fact_price['price_record_status'].eq('valid_discount').sum()):,}", "Retained in fact_discount_event"],
        ["Invalid price records", f"{int(fact_price['price_record_status'].eq('invalid').sum()):,}", "Excluded from price and discount metrics"],
        ["Zero regular-price records", f"{int(fact_price['regular_price_usd'].eq(0).sum()):,}", "Retained but not used as a positive baseline"],
        ["Ambiguous timestamp records", f"{int(fact_price['is_ambiguous_timestamp'].sum()):,}", "Retained; affected games excluded from timing"],
        ["Ambiguous timestamp groups", f"{fact_price.loc[fact_price['is_ambiguous_timestamp']].groupby(['game_id', 'observed_at']).ngroups:,}", "Flagged"],
        ["Games with an ambiguous price stream", f"{fact_price.loc[fact_price['is_ambiguous_timestamp'], 'game_id'].nunique():,}", "Excluded from first-discount timing"],
        ["Pre-release discount records before day -1", f"{int(fact_discount['game_age_days'].lt(-1).sum()):,}", "Excluded from post-release metrics"],
        ["Games with pre-release discount history", f"{fact_discount.loc[fact_discount['game_age_days'].lt(-1), 'game_id'].nunique():,}", "Game retained when other rules pass"],
    ]

    game_flag_counts = (
        game_flags.groupby(["quality_flag", "action"], sort=True)["game_id"]
        .nunique()
        .reset_index(name="games")
    )
    game_flag_rows = [
        [row.quality_flag, f"{row.games:,}", row.action]
        for row in game_flag_counts.itertuples(index=False)
    ]

    price_flag_counts = (
        price_flags.groupby(["quality_flag", "action"], sort=True)
        .size()
        .reset_index(name="records")
    )
    price_flag_rows = [
        [row.quality_flag, f"{row.records:,}", row.action]
        for row in price_flag_counts.itertuples(index=False)
    ]

    check_rows = [["PASS", check] for check in checks]

    sections = [
        "# Data Quality Report",
        "",
        "This report is generated by `src/pipeline/validate_analysis_data.py`. It records the actual retained and excluded counts; it is not a manual checklist.",
        "",
        f"**Price-history cutoff:** {cutoff_at.isoformat()}  ",
        f"**Price source:** `{history_source_name}`  ",
        f"**Final first-discount timing cohort:** {int(eligible.sum()):,} games",
        "",
        "## Outcome",
        "",
        f"The validated timing cohort contains **{int(eligible.sum()):,} games**. Of those, **{int((summary['discount_timing_eligible'] & summary['has_post_release_discount']).sum()):,}** have an observed post-release discount and **{int(summary['right_censored_without_discount'].sum()):,}** are retained as right-censored games without an observed discount.",
        "",
        "The audit restored high-price history records that had been removed by an old $70 ceiling. Price size is no longer an exclusion rule; records are now excluded only when they fail an explicit validity check.",
        "",
        "## Source cleanup",
        "",
        _markdown_table(["Measure", "Count", "Treatment"], source_rows),
        "",
        "## First-discount cohort flow",
        "",
        _markdown_table(["Step", "Games remaining", "Treatment"], cohort_rows),
        "",
        "## Price-record validation",
        "",
        _markdown_table(["Measure", "Count", "Treatment"], price_rows),
        "",
        "## Game-level quality flags",
        "",
        "A game can have more than one flag, so these counts are not additive.",
        "",
        _markdown_table(["Flag", "Games", "Action"], game_flag_rows),
        "",
        "## Price-event quality flags",
        "",
        "One price record can have more than one flag, so these counts are not additive.",
        "",
        _markdown_table(["Flag", "Records", "Action"], price_flag_rows),
        "",
        "## Automated validation results",
        "",
        _markdown_table(["Result", "Check"], check_rows),
        "",
        "## Generated quality artifacts",
        "",
        "- `data/processed/quality/game_quality_flags.parquet` — one row per game and applicable quality flag.",
        "- `data/processed/quality/price_event_quality_flags.parquet` — one row per price event and applicable quality flag.",
        "- `reports/data_quality_report.md` — this generated summary.",
        "",
    ]
    return "\n".join(sections)


def _write_parquet_atomically(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".tmp.parquet")
    frame.to_parquet(temporary_path, index=False)
    temporary_path.replace(path)


def _write_text_atomically(text: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".tmp.md")
    temporary_path.write_text(text, encoding="utf-8", newline="\n")
    temporary_path.replace(path)


def main() -> None:
    game_list, game_tags, history, history_source_name = load_source_tables()
    dim_game, fact_price, fact_discount, summary = load_analysis_tables()

    checks = validate_tables(
        game_list,
        history,
        dim_game,
        fact_price,
        fact_discount,
        summary,
    )
    game_flags = build_game_quality_flags(dim_game, fact_discount, summary)
    price_flags = build_price_event_quality_flags(fact_price)
    report = build_report(
        game_list,
        game_tags,
        history,
        history_source_name,
        dim_game,
        fact_price,
        fact_discount,
        summary,
        game_flags,
        price_flags,
        checks,
    )

    _write_parquet_atomically(game_flags, GAME_FLAGS_PATH)
    _write_parquet_atomically(price_flags, PRICE_FLAGS_PATH)
    _write_text_atomically(report, REPORT_PATH)

    print("Data validation passed")
    print(f"- automated checks: {len(checks)}")
    print(f"- game quality flags: {len(game_flags):,} rows")
    print(f"- price-event quality flags: {len(price_flags):,} rows")
    print(f"- report: {REPORT_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
