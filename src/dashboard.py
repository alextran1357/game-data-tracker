from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st


DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "processed" / "analytics"
WINDOWS = (30, 90, 180, 365)
TIMING_LABELS = ["0–30", "31–90", "91–180", "181–365", "366+"]

st.set_page_config(page_title="Steam Discount Decisions", page_icon="🎮", layout="wide")
st.title("🎮 Steam Discount Decisions")
st.write(
    "Benchmark a first-discount plan against comparable Steam games. "
    "The dashboard describes observed behavior; it does not predict sales or prove causation."
)


@st.cache_data
def load_data():
    games = pd.read_parquet(DATA_DIR / "dim_game.parquet")
    summary = pd.read_parquet(DATA_DIR / "game_discount_summary.parquet")
    summary = summary.drop(columns=["reported_release_date", "discount_timing_eligible"])
    return games.merge(summary, on="game_id", validate="one_to_one")


data = load_data()
data = data.loc[data["is_game"] & data["discount_timing_eligible"]].copy()
data["release_year"] = data["reported_release_date"].dt.year.astype(int)
data["price_band"] = pd.cut(
    data["release_price_usd"],
    [0, 10, 20, 30, 60, float("inf")],
    right=False,
    labels=["Under $10", "$10–19.99", "$20–29.99", "$30–59.99", "$60+"],
)

all_tags = sorted(data["tags"].explode().dropna().unique())
year_min, year_max = data["release_year"].min(), data["release_year"].max()
filter_defaults = {
    "tags": [],
    "years": (year_min, year_max),
    "price": "Any",
    "score": (0, 100),
    "early_access": "All",
}
for key, value in filter_defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


def reset_comparison_filters():
    st.session_state.update(filter_defaults)


st.sidebar.header("Comparable games")
selected_tags = st.sidebar.multiselect("Tags", all_tags, key="tags")
year_range = st.sidebar.slider(
    "Release year", year_min, year_max, key="years"
)
price_band = st.sidebar.selectbox(
    "Launch price",
    ["Any"] + data["price_band"].cat.categories.tolist(),
    key="price",
)
score_range = st.sidebar.slider("Steam review score", 0, 100, key="score")
early_access = st.sidebar.radio(
    "Early access",
    ["All", "Yes", "No"],
    horizontal=True,
    key="early_access",
)
st.sidebar.button("Reset comparison filters", on_click=reset_comparison_filters)

filtered = data.loc[
    data["release_year"].between(*year_range)
    & data["steam_review_score"].between(*score_range)
].copy()
if selected_tags:
    wanted = set(selected_tags)
    filtered = filtered.loc[
        filtered["tags"].apply(lambda tags: bool(wanted.intersection(tags)))
    ]
if price_band != "Any":
    filtered = filtered.loc[filtered["price_band"].eq(price_band)]
if early_access != "All":
    filtered = filtered.loc[filtered["early_access"].eq(early_access == "Yes")]

if filtered.empty:
    st.warning("No reliable comparison games match these filters.")
    st.stop()

st.subheader("Test a first-discount plan")
control_1, control_2 = st.columns(2)
with control_1:
    target_days = st.select_slider(
        "Run the first discount within", WINDOWS, value=90, format_func=lambda x: f"{x} days"
    )
with control_2:
    target_depth = st.slider("Discount by at least", 5, 75, 20, step=5, format="%d%%")

target_sample = filtered.loc[filtered["followup_days"].ge(target_days)].copy()
discounted_by_target = target_sample["days_to_first_discount"].between(0, target_days)
matched_plan = discounted_by_target & target_sample["first_discount_pct"].ge(target_depth)

share_discounted = 100 * discounted_by_target.mean()
share_matched = 100 * matched_plan.mean()
observed = filtered.loc[filtered["days_to_first_discount"].notna()].copy()

metric_1, metric_2, metric_3, metric_4 = st.columns(4)
metric_1.metric("Comparable games", f"{len(filtered):,}")
metric_2.metric("Fully observed for target", f"{len(target_sample):,}")
metric_3.metric(f"Discounted within {target_days} days", f"{share_discounted:.0f}%")
metric_4.metric(f"By day {target_days} at ≥{target_depth}% off", f"{share_matched:.0f}%")

st.caption(
    f"Based on {len(target_sample):,} comparable games with near-release price coverage "
    f"and at least {target_days} days of follow-up."
)
st.info(
    f"{share_matched:.0f}% had their first observed discount within {target_days} days "
    f"at {target_depth}% off or deeper. This is a prevalence benchmark, not a success rate."
)
if len(target_sample) < 50:
    st.warning("This comparison has fewer than 50 games; treat the percentage cautiously.")

window_rows = []
for days in WINDOWS:
    values = filtered[f"discounted_within_{days}_days"].dropna()
    window_rows.append(
        {
            "Window": f"{days} days",
            "Games observed": len(values),
            "Discounted (%)": 100 * values.mean() if len(values) else 0,
        }
    )
window_data = pd.DataFrame(window_rows)

observed["Timing"] = pd.cut(
    observed["days_to_first_discount"],
    [-1, 30, 90, 180, 365, float("inf")],
    labels=TIMING_LABELS,
)
timing_data = (
    observed.groupby("Timing", observed=False)
    .agg(
        Games=("game_id", "size"),
        **{"Median first discount (%)": ("first_discount_pct", "median")},
    )
    .reset_index()
)

left, right = st.columns(2)
with left:
    st.altair_chart(
        alt.Chart(window_data)
        .mark_bar()
        .encode(
            x=alt.X(
                "Window:N",
                sort=[f"{days} days" for days in WINDOWS],
                axis=alt.Axis(labelAngle=0),
            ),
            y=alt.Y("Discounted (%):Q", scale=alt.Scale(domain=[0, 100])),
            tooltip=["Window", "Discounted (%):Q", "Games observed:Q"],
        )
        .properties(title="Share receiving a first discount", height=320),
        use_container_width=True,
    )
    st.caption("Each bar includes only games observed for the full window.")

with right:
    st.altair_chart(
        alt.Chart(timing_data)
        .mark_bar()
        .encode(
            x=alt.X(
                "Timing:N",
                sort=TIMING_LABELS,
                title="Days to first discount",
                axis=alt.Axis(labelAngle=0),
            ),
            y=alt.Y("Median first discount (%):Q"),
            tooltip=["Timing", "Games", "Median first discount (%):Q"],
        )
        .properties(title="Typical depth by timing", height=320),
        use_container_width=True,
    )

with st.expander("View comparable games"):
    st.dataframe(
        filtered[
            [
                "title",
                "release_year",
                "release_price_usd",
                "steam_review_score",
                "days_to_first_discount",
                "first_discount_pct",
            ]
        ].sort_values("days_to_first_discount"),
        hide_index=True,
        width="stretch",
    )

with st.expander("How to interpret this dashboard"):
    st.write(
        "Only games whose price history begins between one day before and seven days after "
        "release are used. Games without enough follow-up are excluded from each time-window "
        "percentage. ITAD records price changes rather than daily snapshots, and these comparisons "
        "do not estimate the effect of discounting on revenue, reviews, or player counts."
    )
