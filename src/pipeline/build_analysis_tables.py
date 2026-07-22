"""Build the analysis-ready tables used by the discount-strategy project.

Run from the repository root with:

    python src/pipeline/build_analysis_tables.py

The builder reads the existing resolved game mapping and processed source tables.
It does not modify those inputs or the files used by the current dashboard.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = DATA_DIR / "processed" / "analytics"

GAME_LIST_PATH = DATA_DIR / "interim" / "game_list.parquet"
GAME_INFO_PATH = DATA_DIR / "processed" / "game_info.parquet"
GAME_HISTORY_PATH = DATA_DIR / "processed" / "game_history.parquet"
GAME_TAGS_PATH = DATA_DIR / "processed" / "game_tags.parquet"

OUTPUT_PATHS = {
    "dim_game": OUTPUT_DIR / "dim_game.parquet",
    "fact_price_event": OUTPUT_DIR / "fact_price_event.parquet",
    "fact_discount_event": OUTPUT_DIR / "fact_discount_event.parquet",
    "game_discount_summary": OUTPUT_DIR / "game_discount_summary.parquet",
}

PRICE_TOLERANCE_USD = 0.01
DISCOUNT_TOLERANCE_POINTS = 1.0
PRICE_COVERAGE_START_DAYS = -1.0
PRICE_COVERAGE_END_DAYS = 7.0
BASELINE_PRICE_END_DAYS = 30.0
DISCOUNT_EPISODE_GAP_DAYS = 14.0


def load_sources() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load the source tables and fail clearly if an input is unavailable."""
    paths = [GAME_LIST_PATH, GAME_INFO_PATH, GAME_HISTORY_PATH, GAME_TAGS_PATH]
    missing = [path for path in paths if not path.exists()]
    if missing:
        missing_text = "\n".join(f"- {path}" for path in missing)
        raise FileNotFoundError(f"Required input files are missing:\n{missing_text}")

    return (
        pd.read_parquet(GAME_LIST_PATH),
        pd.read_parquet(GAME_INFO_PATH),
        pd.read_parquet(GAME_HISTORY_PATH),
        pd.read_parquet(GAME_TAGS_PATH),
    )


def _clean_identifier(series: pd.Series) -> pd.Series:
    cleaned = series.astype("string").str.strip()
    return cleaned.mask(cleaned.eq(""))


def build_dim_game(
    game_list: pd.DataFrame,
    game_info: pd.DataFrame,
    game_tags: pd.DataFrame,
) -> pd.DataFrame:
    """Return one row for every resolved game ID in the project."""
    title_map = game_list[["itad_uuid", "title"]].copy()
    title_map["game_id"] = _clean_identifier(title_map.pop("itad_uuid"))
    title_map["source_title"] = title_map.pop("title").astype("string").str.strip()
    title_map = title_map.dropna(subset=["game_id"])
    title_map = title_map.drop_duplicates(subset=["game_id"], keep="first")

    metadata = game_info.copy()
    metadata["game_id"] = _clean_identifier(metadata.pop("itad_uuid"))
    metadata = metadata.rename(
        columns={
            "title": "metadata_title",
            "type": "content_type",
            "release_date": "reported_release_date",
            "steam_score": "steam_review_score",
            "early_access": "early_access_current",
        }
    )

    metadata_columns = [
        "game_id",
        "metadata_title",
        "content_type",
        "achievements",
        "mature",
        "reported_release_date",
        "steam_review_score",
        "steam_review_count",
        "early_access_current",
        "peak_player_count",
    ]
    metadata = metadata[metadata_columns]
    if metadata["game_id"].duplicated().any():
        raise ValueError("game_info.parquet contains duplicate non-null game IDs")

    dim_game = title_map.merge(metadata, on="game_id", how="left", validate="one_to_one")
    dim_game["title"] = (
        dim_game["metadata_title"].astype("string").fillna(dim_game["source_title"])
    )
    dim_game["metadata_available"] = dim_game["metadata_title"].notna()
    dim_game = dim_game.drop(columns=["metadata_title", "source_title"])

    tags = game_tags[["itad_uuid", "tag"]].copy()
    tags["game_id"] = _clean_identifier(tags.pop("itad_uuid"))
    tags["tag"] = tags["tag"].astype("string").str.strip()
    tags = tags.dropna(subset=["game_id", "tag"])
    tags = tags.loc[tags["tag"].ne("")]
    tags = tags.drop_duplicates(subset=["game_id", "tag"])
    tag_groups = (
        tags.sort_values(["game_id", "tag"])
        .groupby("game_id", sort=False)["tag"]
        .agg(list)
        .rename("tags")
    )
    dim_game = dim_game.merge(tag_groups, on="game_id", how="left", validate="one_to_one")
    dim_game["tags"] = dim_game["tags"].apply(
        lambda value: value if isinstance(value, list) else []
    )
    dim_game["tag_count"] = dim_game["tags"].str.len().astype("Int16")

    dim_game["content_type"] = dim_game["content_type"].astype("string")
    dim_game["reported_release_date"] = pd.to_datetime(
        dim_game["reported_release_date"], errors="coerce"
    )
    dim_game["release_year"] = dim_game["reported_release_date"].dt.year.astype("Int16")
    dim_game["release_month"] = dim_game["reported_release_date"].dt.month.astype("Int8")
    dim_game["has_release_date"] = dim_game["reported_release_date"].notna()
    dim_game["is_game"] = dim_game["content_type"].eq("game").fillna(False)

    for column in ["achievements", "mature", "early_access_current"]:
        dim_game[column] = dim_game[column].astype("boolean")
    dim_game["metadata_available"] = dim_game["metadata_available"].astype("boolean")
    dim_game["has_release_date"] = dim_game["has_release_date"].astype("boolean")
    dim_game["is_game"] = dim_game["is_game"].astype("boolean")
    dim_game["steam_review_score"] = dim_game["steam_review_score"].astype("Int16")
    dim_game["steam_review_count"] = dim_game["steam_review_count"].astype("Int64")
    dim_game["peak_player_count"] = dim_game["peak_player_count"].astype("Int64")

    dim_game["review_score_band"] = pd.cut(
        dim_game["steam_review_score"],
        bins=[-1, 29, 49, 69, 84, 100],
        labels=["0-29", "30-49", "50-69", "70-84", "85-100"],
    ).astype("string")

    ordered_columns = [
        "game_id",
        "title",
        "content_type",
        "is_game",
        "metadata_available",
        "reported_release_date",
        "has_release_date",
        "release_year",
        "release_month",
        "achievements",
        "mature",
        "early_access_current",
        "steam_review_score",
        "review_score_band",
        "steam_review_count",
        "peak_player_count",
        "tag_count",
        "tags",
    ]
    return dim_game[ordered_columns].sort_values("game_id").reset_index(drop=True)


def _combine_quality_issues(issue_masks: list[tuple[str, pd.Series]]) -> pd.Series:
    issues = np.full(len(issue_masks[0][1]), "", dtype=object)
    for label, mask in issue_masks:
        mask_values = mask.fillna(False).to_numpy(dtype=bool)
        issues[mask_values] = np.where(
            issues[mask_values] == "",
            label,
            issues[mask_values] + "|" + label,
        )
    issues[issues == ""] = "none"
    return pd.Series(issues, index=issue_masks[0][1].index, dtype="string")


def build_fact_price_event(
    game_history: pd.DataFrame,
    dim_game: pd.DataFrame,
) -> pd.DataFrame:
    """Return one row per distinct observed Steam price record."""
    price = game_history.copy()
    price["game_id"] = _clean_identifier(price.pop("itad_uuid"))
    price["observed_at"] = pd.to_datetime(price.pop("timestamp"), errors="coerce", utc=True)
    price["deal_price_usd"] = pd.to_numeric(price.pop("deal_price"), errors="coerce").round(2)
    price["regular_price_usd"] = pd.to_numeric(
        price.pop("regular_price"), errors="coerce"
    ).round(2)
    price["discount_pct"] = pd.to_numeric(price.pop("percent"), errors="coerce").astype(
        "Int16"
    )

    price = price.drop_duplicates(
        subset=[
            "game_id",
            "observed_at",
            "deal_price_usd",
            "regular_price_usd",
            "discount_pct",
        ],
        keep="first",
    )
    price = price.sort_values(
        [
            "game_id",
            "observed_at",
            "regular_price_usd",
            "deal_price_usd",
            "discount_pct",
        ]
    ).reset_index(drop=True)

    if price["game_id"].isna().any():
        raise ValueError("game_history.parquet contains rows without a game ID")
    orphan_ids = set(price["game_id"]) - set(dim_game["game_id"])
    if orphan_ids:
        raise ValueError(f"Price history contains {len(orphan_ids)} IDs missing from dim_game")

    price["price_event_number"] = (
        price.groupby("game_id", sort=False).cumcount().add(1).astype("Int32")
    )
    price["shop_id"] = pd.Series(61, index=price.index, dtype="Int16")
    price["shop_name"] = pd.Series("Steam", index=price.index, dtype="string")
    price["currency"] = pd.Series("USD", index=price.index, dtype="string")

    positive_regular = price["regular_price_usd"].gt(0)
    price["computed_discount_pct"] = np.where(
        positive_regular,
        100
        * (price["regular_price_usd"] - price["deal_price_usd"])
        / price["regular_price_usd"],
        np.nan,
    )
    price["computed_discount_pct"] = price["computed_discount_pct"].round(2).astype(
        "Float32"
    )
    price["discount_formula_difference"] = (
        price["computed_discount_pct"] - price["discount_pct"].astype("Float32")
    ).abs().astype("Float32")

    nonnegative_prices = price["deal_price_usd"].ge(0) & price["regular_price_usd"].ge(0)
    deal_not_above_regular = price["deal_price_usd"].le(
        price["regular_price_usd"] + PRICE_TOLERANCE_USD
    )
    valid_discount = (
        price["discount_pct"].between(1, 100, inclusive="both")
        & positive_regular
        & nonnegative_prices
        & deal_not_above_regular
        & price["discount_formula_difference"].le(DISCOUNT_TOLERANCE_POINTS)
    )
    valid_full_price = (
        price["discount_pct"].eq(0)
        & nonnegative_prices
        & (price["deal_price_usd"] - price["regular_price_usd"])
        .abs()
        .le(PRICE_TOLERANCE_USD)
    )

    price["price_record_status"] = pd.Series(
        np.select(
            [valid_discount.to_numpy(), valid_full_price.to_numpy()],
            ["valid_discount", "valid_full_price"],
            default="invalid",
        ),
        index=price.index,
        dtype="string",
    )
    price["is_valid_price_record"] = (valid_discount | valid_full_price).astype("boolean")
    price["is_discount"] = valid_discount.astype("boolean")
    price["is_ambiguous_timestamp"] = price.duplicated(
        subset=["game_id", "observed_at"], keep=False
    ).astype("boolean")

    price["quality_issue"] = _combine_quality_issues(
        [
            ("missing_required_value", price[["game_id", "observed_at", "deal_price_usd", "regular_price_usd", "discount_pct"]].isna().any(axis=1)),
            ("negative_price", ~nonnegative_prices),
            ("deal_above_regular", ~deal_not_above_regular),
            ("discount_out_of_range", ~price["discount_pct"].between(0, 100, inclusive="both")),
            ("zero_regular_price", price["regular_price_usd"].eq(0)),
            (
                "discount_formula_mismatch",
                price["discount_pct"].gt(0)
                & price["discount_formula_difference"].gt(DISCOUNT_TOLERANCE_POINTS),
            ),
            (
                "full_price_value_mismatch",
                price["discount_pct"].eq(0)
                & (price["deal_price_usd"] - price["regular_price_usd"])
                .abs()
                .gt(PRICE_TOLERANCE_USD),
            ),
            ("ambiguous_timestamp", price["is_ambiguous_timestamp"]),
        ]
    )

    release_dates = dim_game.set_index("game_id")["reported_release_date"]
    price["reported_release_date"] = price["game_id"].map(release_dates)
    observed_without_timezone = price["observed_at"].dt.tz_localize(None)
    price["game_age_days"] = (
        (observed_without_timezone - price["reported_release_date"]).dt.total_seconds()
        / 86_400
    ).astype("Float32")

    ordered_columns = [
        "game_id",
        "price_event_number",
        "observed_at",
        "shop_id",
        "shop_name",
        "currency",
        "deal_price_usd",
        "regular_price_usd",
        "discount_pct",
        "computed_discount_pct",
        "discount_formula_difference",
        "price_record_status",
        "is_valid_price_record",
        "is_discount",
        "is_ambiguous_timestamp",
        "quality_issue",
        "reported_release_date",
        "game_age_days",
    ]
    return price[ordered_columns]


def add_game_eligibility_flags(
    dim_game: pd.DataFrame,
    fact_price_event: pd.DataFrame,
) -> pd.DataFrame:
    """Add source-coverage and analysis-eligibility flags to the game dimension."""
    dim_game = dim_game.copy()
    price_ids = set(fact_price_event["game_id"])
    discount_ids = set(fact_price_event.loc[fact_price_event["is_discount"], "game_id"])
    ambiguous_ids = set(
        fact_price_event.loc[fact_price_event["is_ambiguous_timestamp"], "game_id"]
    )

    first_observed = fact_price_event.groupby("game_id", sort=False)["observed_at"].min()
    dim_game["first_price_observed_at"] = dim_game["game_id"].map(first_observed)
    first_observed_without_timezone = dim_game["first_price_observed_at"].dt.tz_localize(None)
    dim_game["price_coverage_start_days"] = (
        (
            first_observed_without_timezone
            - dim_game["reported_release_date"]
        ).dt.total_seconds()
        / 86_400
    ).astype("Float32")

    dim_game["has_price_history"] = dim_game["game_id"].isin(price_ids)
    dim_game["has_observed_discount"] = dim_game["game_id"].isin(discount_ids)
    dim_game["has_ambiguous_price_stream"] = dim_game["game_id"].isin(ambiguous_ids)
    dim_game["near_release_price_coverage"] = dim_game[
        "price_coverage_start_days"
    ].between(PRICE_COVERAGE_START_DAYS, PRICE_COVERAGE_END_DAYS, inclusive="both")

    cutoff_without_timezone = fact_price_event["observed_at"].max().tz_localize(None)
    release_before_cutoff = dim_game["reported_release_date"].le(cutoff_without_timezone)
    dim_game["discount_timing_eligible"] = (
        dim_game["is_game"]
        & dim_game["has_release_date"]
        & release_before_cutoff
        & dim_game["has_price_history"]
        & dim_game["near_release_price_coverage"]
        & ~dim_game["has_ambiguous_price_stream"]
    )

    boolean_columns = [
        "has_price_history",
        "has_observed_discount",
        "has_ambiguous_price_stream",
        "near_release_price_coverage",
        "discount_timing_eligible",
    ]
    for column in boolean_columns:
        dim_game[column] = dim_game[column].fillna(False).astype("boolean")
    return dim_game


def build_fact_discount_event(fact_price_event: pd.DataFrame) -> pd.DataFrame:
    """Return one row per valid discounted price observation with episode fields."""
    timeline = fact_price_event.loc[fact_price_event["is_valid_price_record"]].copy()
    timeline = timeline.sort_values(["game_id", "observed_at", "price_event_number"])

    grouped_timeline = timeline.groupby("game_id", sort=False)
    timeline["previous_valid_status"] = grouped_timeline["price_record_status"].shift()
    timeline["previous_valid_observed_at"] = grouped_timeline["observed_at"].shift()
    gap_from_previous_valid = (
        timeline["observed_at"] - timeline["previous_valid_observed_at"]
    ).dt.total_seconds() / 86_400

    new_episode = timeline["is_discount"] & (
        timeline["previous_valid_status"].ne("valid_discount")
        | timeline["previous_valid_status"].isna()
        | gap_from_previous_valid.gt(DISCOUNT_EPISODE_GAP_DAYS)
    )
    timeline["is_episode_start"] = new_episode.astype("boolean")
    timeline["discount_episode_number"] = (
        new_episode.groupby(timeline["game_id"], sort=False).cumsum().astype("Int32")
    )

    discount = timeline.loc[timeline["is_discount"]].copy()
    discount["discount_event_number"] = (
        discount.groupby("game_id", sort=False).cumcount().add(1).astype("Int32")
    )
    discount["days_since_previous_discount_record"] = (
        discount.groupby("game_id", sort=False)["observed_at"]
        .diff()
        .dt.total_seconds()
        .div(86_400)
        .astype("Float32")
    )
    discount["is_release_day_discount"] = discount["game_age_days"].between(
        -1, 0, inclusive="both"
    ).fillna(False).astype("boolean")

    ordered_columns = [
        "game_id",
        "discount_event_number",
        "price_event_number",
        "discount_episode_number",
        "is_episode_start",
        "observed_at",
        "deal_price_usd",
        "regular_price_usd",
        "discount_pct",
        "computed_discount_pct",
        "reported_release_date",
        "game_age_days",
        "days_since_previous_discount_record",
        "is_release_day_discount",
        "is_ambiguous_timestamp",
    ]
    return discount[ordered_columns].reset_index(drop=True)


def _nullable_window_flag(
    summary: pd.DataFrame,
    days: int,
) -> pd.Series:
    result = pd.Series(pd.NA, index=summary.index, dtype="boolean")
    enough_followup = (
        summary["discount_timing_eligible"]
        & summary["followup_days"].ge(days)
    )
    observed_within_window = summary["days_to_first_observed_discount"].between(
        0, days, inclusive="both"
    )
    result.loc[enough_followup] = observed_within_window.loc[enough_followup].fillna(False)
    return result


def build_game_discount_summary(
    dim_game: pd.DataFrame,
    fact_price_event: pd.DataFrame,
    fact_discount_event: pd.DataFrame,
) -> pd.DataFrame:
    """Return a standalone one-row-per-game analytical summary."""
    summary_columns = [
        "game_id",
        "title",
        "content_type",
        "is_game",
        "reported_release_date",
        "release_year",
        "release_month",
        "steam_review_score",
        "review_score_band",
        "steam_review_count",
        "peak_player_count",
        "tag_count",
        "tags",
        "has_price_history",
        "has_ambiguous_price_stream",
        "near_release_price_coverage",
        "discount_timing_eligible",
        "first_price_observed_at",
        "price_coverage_start_days",
    ]
    summary = dim_game[summary_columns].copy()

    price_group = fact_price_event.groupby("game_id", sort=False)
    price_aggregates = price_group.agg(
        last_price_observed_at=("observed_at", "max"),
        price_record_count=("price_event_number", "size"),
        valid_price_record_count=("is_valid_price_record", "sum"),
        ambiguous_price_record_count=("is_ambiguous_timestamp", "sum"),
    )
    price_aggregates["invalid_price_record_count"] = (
        price_aggregates["price_record_count"]
        - price_aggregates["valid_price_record_count"]
    )
    summary = summary.merge(price_aggregates, on="game_id", how="left", validate="one_to_one")

    valid_positive_price = fact_price_event.loc[
        fact_price_event["is_valid_price_record"]
        & fact_price_event["regular_price_usd"].gt(0)
    ].copy()
    baseline = (
        valid_positive_price.loc[
            valid_positive_price["game_age_days"].between(
                PRICE_COVERAGE_START_DAYS,
                BASELINE_PRICE_END_DAYS,
                inclusive="both",
            )
        ]
        .sort_values(["game_id", "observed_at", "price_event_number"])
        .drop_duplicates("game_id", keep="first")
        [["game_id", "regular_price_usd", "observed_at"]]
        .rename(
            columns={
                "regular_price_usd": "first_observed_regular_price_usd",
                "observed_at": "baseline_price_observed_at",
            }
        )
    )
    latest_regular = (
        valid_positive_price.sort_values(["game_id", "observed_at", "price_event_number"])
        .drop_duplicates("game_id", keep="last")
        [["game_id", "regular_price_usd"]]
        .rename(columns={"regular_price_usd": "latest_observed_regular_price_usd"})
    )
    summary = summary.merge(baseline, on="game_id", how="left", validate="one_to_one")
    summary = summary.merge(latest_regular, on="game_id", how="left", validate="one_to_one")
    summary["price_tier"] = pd.cut(
        summary["first_observed_regular_price_usd"],
        bins=[0, 5, 10, 20, 30, np.inf],
        right=False,
        labels=["Under $5", "$5-9.99", "$10-19.99", "$20-29.99", "$30+"],
    ).astype("string")

    discount_aggregates = fact_discount_event.groupby("game_id", sort=False).agg(
        valid_discount_record_count=("discount_event_number", "size"),
        discount_episode_count=("discount_episode_number", "nunique"),
        first_valid_discount_at=("observed_at", "min"),
    )
    summary = summary.merge(discount_aggregates, on="game_id", how="left", validate="one_to_one")

    post_release_discount = fact_discount_event.loc[
        fact_discount_event["game_age_days"].ge(PRICE_COVERAGE_START_DAYS)
    ].copy()
    post_release_aggregates = post_release_discount.groupby("game_id", sort=False).agg(
        post_release_discount_record_count=("discount_event_number", "size"),
        post_release_discount_episode_count=("discount_episode_number", "nunique"),
        median_post_release_discount_pct=("discount_pct", "median"),
        max_post_release_discount_pct=("discount_pct", "max"),
    )
    first_post_release_discount = (
        post_release_discount.sort_values(
            ["game_id", "observed_at", "discount_event_number"]
        )
        .drop_duplicates("game_id", keep="first")
        [["game_id", "observed_at", "discount_pct"]]
        .rename(
            columns={
                "observed_at": "first_post_release_discount_at",
                "discount_pct": "first_post_release_discount_pct",
            }
        )
    )
    summary = summary.merge(
        post_release_aggregates, on="game_id", how="left", validate="one_to_one"
    )
    summary = summary.merge(
        first_post_release_discount, on="game_id", how="left", validate="one_to_one"
    )

    cutoff_at = fact_price_event["observed_at"].max()
    cutoff_without_timezone = cutoff_at.tz_localize(None)
    first_discount_without_timezone = summary["first_post_release_discount_at"].dt.tz_localize(
        None
    )
    raw_days_to_discount = (
        first_discount_without_timezone - summary["reported_release_date"]
    ).dt.total_seconds() / 86_400
    summary["days_to_first_observed_discount"] = raw_days_to_discount.where(
        summary["discount_timing_eligible"]
    ).clip(lower=0).astype("Float32")
    summary["followup_days"] = (
        (cutoff_without_timezone - summary["reported_release_date"]).dt.total_seconds()
        / 86_400
    ).clip(lower=0).astype("Float32")
    summary["has_post_release_discount"] = summary[
        "first_post_release_discount_at"
    ].notna().astype("boolean")
    summary["right_censored_without_discount"] = (
        summary["discount_timing_eligible"]
        & ~summary["has_post_release_discount"]
    ).astype("boolean")
    summary["data_cutoff_at"] = cutoff_at

    for days in [30, 90, 180, 365]:
        summary[f"discounted_within_{days}_days"] = _nullable_window_flag(summary, days)

    count_columns = [
        "price_record_count",
        "valid_price_record_count",
        "invalid_price_record_count",
        "ambiguous_price_record_count",
        "valid_discount_record_count",
        "discount_episode_count",
        "post_release_discount_record_count",
        "post_release_discount_episode_count",
    ]
    for column in count_columns:
        summary[column] = summary[column].fillna(0).astype("Int32")
    summary["first_post_release_discount_pct"] = summary[
        "first_post_release_discount_pct"
    ].astype("Int16")
    summary["max_post_release_discount_pct"] = summary[
        "max_post_release_discount_pct"
    ].astype("Int16")
    summary["median_post_release_discount_pct"] = summary[
        "median_post_release_discount_pct"
    ].astype("Float32")

    return summary.sort_values("game_id").reset_index(drop=True)


def validate_tables(
    dim_game: pd.DataFrame,
    fact_price_event: pd.DataFrame,
    fact_discount_event: pd.DataFrame,
    game_discount_summary: pd.DataFrame,
) -> None:
    """Enforce the declared grains and table relationships before writing files."""
    if dim_game["game_id"].isna().any() or dim_game["game_id"].duplicated().any():
        raise AssertionError("dim_game must contain one non-null row per game_id")

    price_key = [
        "game_id",
        "observed_at",
        "deal_price_usd",
        "regular_price_usd",
        "discount_pct",
    ]
    if fact_price_event.duplicated(price_key).any():
        raise AssertionError("fact_price_event contains duplicate grain keys")

    dimension_ids = set(dim_game["game_id"])
    if not set(fact_price_event["game_id"]).issubset(dimension_ids):
        raise AssertionError("fact_price_event contains orphan game IDs")
    if not set(fact_discount_event["game_id"]).issubset(dimension_ids):
        raise AssertionError("fact_discount_event contains orphan game IDs")

    if not fact_discount_event["discount_pct"].between(1, 100).all():
        raise AssertionError("fact_discount_event contains a non-discount record")
    if fact_discount_event.duplicated(["game_id", "discount_event_number"]).any():
        raise AssertionError("fact_discount_event contains duplicate event numbers")

    if len(game_discount_summary) != len(dim_game):
        raise AssertionError("game_discount_summary must contain one row per dim_game row")
    if game_discount_summary["game_id"].duplicated().any():
        raise AssertionError("game_discount_summary contains duplicate game IDs")
    if set(game_discount_summary["game_id"]) != dimension_ids:
        raise AssertionError("game_discount_summary game IDs do not match dim_game")


def _write_parquet_atomically(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".tmp.parquet")
    frame.to_parquet(temporary_path, index=False)
    temporary_path.replace(path)


def main() -> None:
    game_list, game_info, game_history, game_tags = load_sources()

    dim_game = build_dim_game(game_list, game_info, game_tags)
    fact_price_event = build_fact_price_event(game_history, dim_game)
    dim_game = add_game_eligibility_flags(dim_game, fact_price_event)
    fact_discount_event = build_fact_discount_event(fact_price_event)
    game_discount_summary = build_game_discount_summary(
        dim_game, fact_price_event, fact_discount_event
    )

    validate_tables(
        dim_game,
        fact_price_event,
        fact_discount_event,
        game_discount_summary,
    )

    tables = {
        "dim_game": dim_game,
        "fact_price_event": fact_price_event,
        "fact_discount_event": fact_discount_event,
        "game_discount_summary": game_discount_summary,
    }
    for name, frame in tables.items():
        _write_parquet_atomically(frame, OUTPUT_PATHS[name])

    print("Analysis tables built successfully")
    for name, frame in tables.items():
        print(f"- {name}: {len(frame):,} rows -> {OUTPUT_PATHS[name].relative_to(PROJECT_ROOT)}")
    print(
        "- discount timing eligible games: "
        f"{int(dim_game['discount_timing_eligible'].sum()):,}"
    )
    print(
        "- eligible games without an observed post-release discount: "
        f"{int(game_discount_summary['right_censored_without_discount'].sum()):,}"
    )


if __name__ == "__main__":
    main()
