"""Build the compact tables used for discount analysis."""

from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
ANALYTICS = DATA / "processed" / "analytics"

FILES = {
    "games": DATA / "interim" / "game_list.parquet",
    "info": DATA / "processed" / "game_info.parquet",
    "tags": DATA / "processed" / "game_tags.parquet",
    "history": DATA / "processed" / "game_history.parquet",
}


def read_sources():
    missing = [str(path) for path in FILES.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing source files: {missing}")
    return {name: pd.read_parquet(path) for name, path in FILES.items()}


def build_games(source):
    games = source["games"][["itad_uuid", "title"]].rename(
        columns={"itad_uuid": "game_id", "title": "list_title"}
    )
    games = games.dropna(subset=["game_id"]).drop_duplicates("game_id")

    info = source["info"][
        [
            "itad_uuid",
            "title",
            "type",
            "release_date",
            "steam_score",
            "steam_review_count",
            "early_access",
            "peak_player_count",
        ]
    ].rename(
        columns={
            "itad_uuid": "game_id",
            "title": "info_title",
            "type": "content_type",
            "release_date": "reported_release_date",
            "steam_score": "steam_review_score",
        }
    )
    if info["game_id"].duplicated().any():
        raise ValueError("game_info.parquet contains duplicate game IDs")

    games = games.merge(info, on="game_id", how="left", validate="one_to_one")
    games["title"] = games["info_title"].fillna(games["list_title"])
    games = games.drop(columns=["info_title", "list_title"])

    tags = source["tags"][["itad_uuid", "tag"]].rename(
        columns={"itad_uuid": "game_id"}
    )
    tags = tags.dropna().drop_duplicates().sort_values(["game_id", "tag"])
    tags = tags.groupby("game_id")["tag"].agg(list).rename("tags")
    games = games.merge(tags, on="game_id", how="left")
    games["tags"] = games["tags"].apply(
        lambda value: value if isinstance(value, list) else []
    )

    games["reported_release_date"] = pd.to_datetime(
        games["reported_release_date"], errors="coerce"
    )
    games["is_game"] = games["content_type"].eq("game")
    return games.sort_values("game_id").reset_index(drop=True)


def build_prices(history, games):
    prices = history.rename(
        columns={
            "itad_uuid": "game_id",
            "timestamp": "observed_at",
            "deal_price": "deal_price_usd",
            "regular_price": "regular_price_usd",
            "percent": "discount_pct",
        }
    ).copy()
    prices["observed_at"] = pd.to_datetime(prices["observed_at"], utc=True)
    prices["deal_price_usd"] = prices["deal_price_usd"].round(2)
    prices["regular_price_usd"] = prices["regular_price_usd"].round(2)

    key = [
        "game_id",
        "observed_at",
        "deal_price_usd",
        "regular_price_usd",
        "discount_pct",
    ]
    prices = prices.drop_duplicates(key).sort_values(key).reset_index(drop=True)
    prices["price_record_number"] = prices.groupby("game_id").cumcount() + 1

    regular = prices["regular_price_usd"]
    expected = 100 * (regular - prices["deal_price_usd"]) / regular.where(regular > 0)
    prices["calculated_discount_pct"] = expected.round(2)
    sensible_prices = (
        prices["deal_price_usd"].ge(0)
        & regular.ge(0)
        & prices["deal_price_usd"].le(regular + 0.01)
    )
    valid_discount = (
        prices["discount_pct"].between(1, 100)
        & regular.gt(0)
        & sensible_prices
        & (expected - prices["discount_pct"]).abs().le(1)
    )
    valid_full_price = (
        prices["discount_pct"].eq(0)
        & sensible_prices
        & (prices["deal_price_usd"] - regular).abs().le(0.01)
    )
    prices["record_status"] = np.select(
        [valid_discount, valid_full_price],
        ["valid_discount", "valid_full_price"],
        default="invalid",
    )
    prices["is_discount"] = valid_discount
    prices["ambiguous_timestamp"] = prices.duplicated(
        ["game_id", "observed_at"], keep=False
    )

    release_dates = games.set_index("game_id")["reported_release_date"]
    prices["reported_release_date"] = prices["game_id"].map(release_dates)
    prices["days_from_release"] = (
        prices["observed_at"].dt.tz_localize(None)
        - prices["reported_release_date"]
    ).dt.total_seconds() / 86_400
    return prices


def add_coverage(games, prices):
    games = games.copy()
    first_seen = prices.groupby("game_id")["observed_at"].min()
    games["first_price_observed_at"] = games["game_id"].map(first_seen)
    games["price_coverage_start_days"] = (
        games["first_price_observed_at"].dt.tz_localize(None)
        - games["reported_release_date"]
    ).dt.total_seconds() / 86_400
    games["has_price_history"] = games["first_price_observed_at"].notna()
    ambiguous_games = prices.loc[prices["ambiguous_timestamp"], "game_id"]
    games["has_ambiguous_price_history"] = games["game_id"].isin(ambiguous_games)

    cutoff = prices["observed_at"].max().tz_localize(None)
    games["discount_timing_eligible"] = (
        games["is_game"]
        & games["reported_release_date"].notna()
        & games["reported_release_date"].le(cutoff)
        & games["has_price_history"]
        & games["price_coverage_start_days"].between(-1, 7)
        & ~games["has_ambiguous_price_history"]
    )
    return games


def build_discounts(prices):
    timeline = prices.loc[prices["record_status"] != "invalid"].copy()
    timeline = timeline.sort_values(
        ["game_id", "observed_at", "price_record_number"]
    )
    groups = timeline.groupby("game_id")
    previous_status = groups["record_status"].shift()
    gap_days = (
        timeline["observed_at"] - groups["observed_at"].shift()
    ).dt.total_seconds() / 86_400
    episode_start = timeline["is_discount"] & (
        previous_status.ne("valid_discount")
        | previous_status.isna()
        | gap_days.gt(14)
    )
    timeline["discount_episode_number"] = episode_start.groupby(
        timeline["game_id"]
    ).cumsum()

    discounts = timeline.loc[timeline["is_discount"]].copy()
    discounts["discount_record_number"] = (
        discounts.groupby("game_id").cumcount() + 1
    )
    discounts["is_episode_start"] = episode_start.loc[discounts.index]
    columns = [
        "game_id",
        "discount_record_number",
        "discount_episode_number",
        "is_episode_start",
        "observed_at",
        "deal_price_usd",
        "regular_price_usd",
        "discount_pct",
        "reported_release_date",
        "days_from_release",
    ]
    return discounts[columns].reset_index(drop=True)


def build_summary(games, prices, discounts):
    summary = games[["game_id", "discount_timing_eligible"]].copy()
    counts = prices.groupby("game_id").agg(
        price_record_count=("price_record_number", "size"),
        invalid_price_record_count=("record_status", lambda x: x.eq("invalid").sum()),
    )
    summary = summary.merge(counts, on="game_id", how="left")

    baseline = prices.loc[
        prices["record_status"].ne("invalid")
        & prices["regular_price_usd"].gt(0)
        & prices["days_from_release"].between(-1, 30)
    ]
    baseline = (
        baseline.sort_values(["game_id", "observed_at"])
        .drop_duplicates("game_id")
        .set_index("game_id")["regular_price_usd"]
        .rename("release_price_usd")
    )
    summary = summary.merge(baseline, on="game_id", how="left")

    post_release = discounts.loc[discounts["days_from_release"].ge(-1)]
    discount_stats = post_release.groupby("game_id").agg(
        first_discount_at=("observed_at", "min"),
        first_discount_pct=("discount_pct", "first"),
        median_discount_pct=("discount_pct", "median"),
        max_discount_pct=("discount_pct", "max"),
        discount_episode_count=("discount_episode_number", "nunique"),
    )
    summary = summary.merge(discount_stats, on="game_id", how="left")

    release_dates = games.set_index("game_id")["reported_release_date"]
    summary["reported_release_date"] = summary["game_id"].map(release_dates)
    summary["days_to_first_discount"] = (
        summary["first_discount_at"].dt.tz_localize(None)
        - summary["reported_release_date"]
    ).dt.total_seconds() / 86_400
    summary.loc[
        ~summary["discount_timing_eligible"], "days_to_first_discount"
    ] = np.nan
    summary["days_to_first_discount"] = summary["days_to_first_discount"].clip(
        lower=0
    )

    cutoff = prices["observed_at"].max()
    summary["followup_days"] = (
        cutoff.tz_localize(None) - summary["reported_release_date"]
    ).dt.total_seconds() / 86_400
    summary["has_observed_discount"] = summary["first_discount_at"].notna()
    summary["right_censored"] = (
        summary["discount_timing_eligible"] & ~summary["has_observed_discount"]
    )
    for days in (30, 90, 180, 365):
        available = summary["discount_timing_eligible"] & summary[
            "followup_days"
        ].ge(days)
        column = f"discounted_within_{days}_days"
        summary[column] = pd.Series(pd.NA, index=summary.index, dtype="boolean")
        summary.loc[available, column] = summary.loc[
            available, "days_to_first_discount"
        ].between(0, days)

    for column in (
        "price_record_count",
        "invalid_price_record_count",
        "discount_episode_count",
    ):
        summary[column] = summary[column].fillna(0).astype(int)
    return summary


def validate(games, prices, discounts, summary):
    price_key = [
        "game_id",
        "observed_at",
        "deal_price_usd",
        "regular_price_usd",
        "discount_pct",
    ]
    assert games["game_id"].is_unique and games["game_id"].notna().all()
    assert not prices.duplicated(price_key).any()
    assert set(prices["game_id"]).issubset(set(games["game_id"]))
    assert len(discounts) == prices["record_status"].eq("valid_discount").sum()
    assert discounts["discount_pct"].between(1, 100).all()
    assert len(summary) == len(games) and summary["game_id"].is_unique
    assert not summary["days_to_first_discount"].dropna().lt(0).any()
    assert summary["right_censored"].equals(
        summary["discount_timing_eligible"] & ~summary["has_observed_discount"]
    )
    for days in (30, 90, 180, 365):
        available = summary["discount_timing_eligible"] & summary[
            "followup_days"
        ].ge(days)
        assert summary.loc[
            ~available, f"discounted_within_{days}_days"
        ].isna().all()


def write_results(source, games, prices, discounts, summary):
    tables = {
        "dim_game": games,
        "game_discount_summary": summary,
    }
    ANALYTICS.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        path = ANALYTICS / f"{name}.parquet"
        temp = path.with_suffix(".tmp.parquet")
        table.to_parquet(temp, index=False)
        temp.replace(path)

    report = f"""# Data Quality Report

Generated by `src/pipeline/build_analysis_tables.py`.

| Check | Result |
| --- | ---: |
| Resolved games | {len(games):,} |
| Source price records | {len(source['history']):,} |
| Distinct price records | {len(prices):,} |
| Valid discount records | {len(discounts):,} |
| Invalid price records excluded from metrics | {prices['record_status'].eq('invalid').sum():,} |
| Games eligible for discount-timing analysis | {games['discount_timing_eligible'].sum():,} |
| Eligible games without an observed discount | {summary['right_censored'].sum():,} |
| Price-history cutoff | {prices['observed_at'].max().isoformat()} |

All table-grain, relationship, discount, censoring, and follow-up checks passed.
"""
    report_path = ROOT / "reports" / "data_quality_report.md"
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    return tables


def main():
    source = read_sources()
    games = build_games(source)
    prices = build_prices(source["history"], games)
    games = add_coverage(games, prices)
    discounts = build_discounts(prices)
    summary = build_summary(games, prices, discounts)
    validate(games, prices, discounts, summary)
    tables = write_results(source, games, prices, discounts, summary)

    print("Build passed")
    for name, table in tables.items():
        print(f"- {name}: {len(table):,} rows")


if __name__ == "__main__":
    main()
