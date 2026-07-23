from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st


DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "processed" / "analytics"

st.set_page_config(page_title="Steam Discount Timing", page_icon="🎮", layout="wide")
st.title("🎮 Steam Discount Timing")
st.write(
    "Explore when Steam games first go on sale and how deep their first discount is. "
    "Results describe this dataset; they do not show that discounting causes success."
)


@st.cache_data
def load_data():
    games = pd.read_parquet(DATA_DIR / "dim_game.parquet")
    summary = pd.read_parquet(DATA_DIR / "game_discount_summary.parquet")
    summary = summary.drop(columns=["reported_release_date", "discount_timing_eligible"])
    return games.merge(summary, on="game_id", validate="one_to_one")


data = load_data()
data = data.loc[data["is_game"]].copy()
data["release_year"] = data["reported_release_date"].dt.year

st.sidebar.header("Filters")
all_tags = sorted(data["tags"].explode().dropna().unique())
selected_tags = st.sidebar.multiselect("Tags", all_tags)

years = data["release_year"].dropna().astype(int)
year_range = st.sidebar.slider(
    "Release year",
    int(years.min()),
    int(years.max()),
    (int(years.min()), int(years.max())),
)
score_range = st.sidebar.slider("Steam review score", 0, 100, (0, 100))
early_access = st.sidebar.radio("Early access", ["All", "Yes", "No"], horizontal=True)
eligible_only = st.sidebar.checkbox("Use reliable timing cohort only", value=True)

filtered = data.loc[
    data["release_year"].between(*year_range)
    & data["steam_review_score"].between(*score_range)
].copy()
if selected_tags:
    wanted = set(selected_tags)
    filtered = filtered.loc[
        filtered["tags"].apply(lambda tags: bool(wanted.intersection(tags)))
    ]
if early_access != "All":
    filtered = filtered.loc[filtered["early_access"].eq(early_access == "Yes")]
if eligible_only:
    filtered = filtered.loc[filtered["discount_timing_eligible"]]

if filtered.empty:
    st.warning("No games match these filters.")
    st.stop()

eligible = filtered.loc[filtered["discount_timing_eligible"]]
observed = eligible.loc[eligible["days_to_first_discount"].notna()].copy()

metric_1, metric_2, metric_3, metric_4 = st.columns(4)
metric_1.metric("Games in view", f"{len(filtered):,}")
metric_2.metric("Reliable timing cohort", f"{len(eligible):,}")
metric_3.metric(
    "Median days to first discount",
    f"{observed['days_to_first_discount'].median():.0f}" if len(observed) else "—",
)
metric_4.metric(
    "Median first discount",
    f"{observed['first_discount_pct'].median():.0f}%" if len(observed) else "—",
)

window_rows = []
for days in (30, 90, 180, 365):
    values = eligible[f"discounted_within_{days}_days"].dropna()
    window_rows.append(
        {
            "Window": f"{days} days",
            "Games observed": len(values),
            "Discounted (%)": 100 * values.mean() if len(values) else 0,
        }
    )
window_data = pd.DataFrame(window_rows)

timing_labels = ["0–30", "31–90", "91–180", "181–365", "366+"]
observed["Timing"] = pd.cut(
    observed["days_to_first_discount"],
    [-1, 30, 90, 180, 365, float("inf")],
    labels=timing_labels,
)
timing_data = (
    observed.groupby("Timing", observed=False)
    .agg(Games=("game_id", "size"), **{"Median discount (%)": ("first_discount_pct", "median")})
    .reset_index()
)

left, right = st.columns(2)
with left:
    st.altair_chart(
        alt.Chart(window_data)
        .mark_bar()
        .encode(
            x=alt.X("Window:N", sort=[f"{days} days" for days in (30, 90, 180, 365)]),
            y=alt.Y("Discounted (%):Q", scale=alt.Scale(domain=[0, 100])),
            tooltip=["Window", "Discounted (%):Q", "Games observed:Q"],
        )
        .properties(title="Games discounted within each window", height=320),
        use_container_width=True,
    )
    st.caption("Each bar uses only games followed for the entire time window.")

with right:
    st.altair_chart(
        alt.Chart(timing_data)
        .mark_bar()
        .encode(
            x=alt.X("Timing:N", sort=timing_labels, title="Days to first discount"),
            y=alt.Y("Games:Q"),
            tooltip=["Timing", "Games", "Median discount (%):Q"],
        )
        .properties(title="When first discounts occurred", height=320),
        use_container_width=True,
    )

tag_data = observed[["game_id", "tags", "days_to_first_discount"]].explode("tags")
tag_data = (
    tag_data.groupby("tags")
    .agg(Games=("game_id", "size"), **{"Median days": ("days_to_first_discount", "median")})
    .query("Games >= 15")
    .sort_values("Games", ascending=False)
    .head(15)
    .reset_index()
)
if not tag_data.empty:
    st.altair_chart(
        alt.Chart(tag_data)
        .mark_bar()
        .encode(
            x=alt.X("Median days:Q", title="Median days to first discount"),
            y=alt.Y("tags:N", sort="-x", title="Tag"),
            tooltip=["tags", "Games", "Median days:Q"],
        )
        .properties(title="First-discount timing among common tags", height=420),
        use_container_width=True,
    )

with st.expander("View games"):
    st.dataframe(
        filtered[
            [
                "title",
                "release_year",
                "steam_review_score",
                "release_price_usd",
                "days_to_first_discount",
                "first_discount_pct",
                "peak_player_count",
            ]
        ].sort_values("days_to_first_discount"),
        hide_index=True,
        width="stretch",
    )
