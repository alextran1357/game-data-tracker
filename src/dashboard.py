import streamlit as st
import pandas as pd
import altair as alt
import plotly.express as px
from streamlit_dynamic_filters import DynamicFilters
from streamlit_extras.metric_cards import style_metric_cards

st.set_page_config(
  page_title="Steam Data Dashboard",
  page_icon="🎮",
  layout="wide",
)
st.title("🎮 Steam Data Dashboard")
st.write("Explore how price, ratings, and release month affect peak player counts.")

@st.cache_data
def load_data():
  game_info = pd.read_parquet("../data/game_info.parquet")
  game_history = pd.read_parquet("../data/game_history.parquet")
  game_tags = pd.read_parquet("../data/game_tags.parquet")
  game_tags_15 = pd.read_parquet("../data/game_tags_15.parquet")
  return game_info, game_history, game_tags, game_tags_15
game_info, game_history, game_tags, game_tags_15 = load_data()
filtered_df = game_info.copy()
game_history_copy = game_history.sort_values("regular_price").drop_duplicates("itad_uuid")
filtered_df = filtered_df.merge(game_history_copy, on="itad_uuid", how='left')
CHART_HEIGHT = 320
# ------------ Select Chart ------------
# chart_choice = st.sidebar.selectbox(
#   "Charts Selection",
#   ["Overall Summary", "User Exploration"],
#   index=0
# )
# st.title(chart_choice)

# if chart_choice == "User Exploration" and len(filtered_df):
if len(filtered_df):
  # ------------ Sidebar Config Display ------------
  sidebar_title = st.sidebar.header("Filters")
  tag_filter = DynamicFilters(game_tags_15, filters=['tag'])
  with st.sidebar:
    tag_filter.display_filters()
  release_month_dict = {"01 - January":1, "02 - February":2, "03 - March":3, "04 - April":4, "05 - May":5, "06 - June":6, "07 - July":7, "08 - August":8, "09 - September":9, "10 - October":10, "11 - November":11, "12 - December":12}
  release_month = st.sidebar.multiselect( 
    "Release Month",
    ["01 - January", "02 - February", "03 - March", "04 - April", "05 - May", "06 - June" , "07 - July", "08 - August", "09 - September", "10 - October", "11 - November", "12 - December"]
  )
  # release_year = st.sidebar.multiselect(
  #   "Release Year",
  #   [x for x in range(int(min(game_info['release_year'])), int(max(game_info['release_year'])+1))]
  # )
  score_range = st.sidebar.slider("Steam Score Range", 0, 100, (0, 100))
  early_access = st.sidebar.radio(
      "Early Access",
      ["All", "Yes", "No"],
      index=0,
      horizontal=True
  )
  mature = st.sidebar.radio(
      "Mature",
      ["All", "Yes", "No"],
      index=0,
      horizontal=True
  )
  achievements = st.sidebar.radio(
      "Achievements",
      ["All", "Yes", "No"],
      index=0,
      horizontal=True
  )

  # ------------ Apply Filters ------------
  if tag_filter:
    filter_id = tag_filter.filter_df()
    filter_id = filter_id['itad_uuid'].dropna().unique()
    filtered_df = filtered_df[game_info['itad_uuid'].isin(filter_id)]
  if release_month:
    check_release_month = [release_month_dict[x] for x in release_month]
    filtered_df = filtered_df[filtered_df['release_month'].isin(check_release_month)]
  # if release_year:
  #   filtered_df = filtered_df[filtered_df['release_year'].isin(release_year)]
  if score_range:
    filtered_df = filtered_df[filtered_df['steam_score'].between(score_range[0], score_range[1])]
  if early_access != "All":
    if early_access == "Yes":
      filtered_df = filtered_df[filtered_df['early_access'] == True]
    else:
      filtered_df = filtered_df[filtered_df['early_access'] == False]
  if mature != "All":
    if mature == "Yes":
      filtered_df = filtered_df[filtered_df['mature'] == True]
    else:
      filtered_df = filtered_df[filtered_df['mature'] == False]
  if achievements != "All":
    if achievements == "Yes":
      filtered_df = filtered_df[filtered_df['achievements'] == True]
    else:
      filtered_df = filtered_df[filtered_df['achievements'] == False]
  
  hover = alt.selection_point(on="mouseover")
  col1, col2, col3 = st.columns(3, gap="small")
  with col1:
    st.metric("Median Steam Score", f"{filtered_df['steam_score'].median():.0f}")
  with col2:
    st.metric("Median Price", f"${filtered_df['regular_price'].median():.2f}")
  with col3:
    average_percent_off = sum(filtered_df[filtered_df["percent"] > 0]['percent'] / len(filtered_df[filtered_df["percent"] > 0]))
    st.metric("Average Sale Percent", f"{average_percent_off:.0f}%")
  col1, col2 = st.columns(2)
  with col1:
    release_trends_over_time_chart = alt.Chart(filtered_df[filtered_df['release_date'].notnull() &
                                                          (filtered_df['release_date'].dt.year > 2000)]).mark_bar().encode(
      x=alt.X("release_year:O", title="Release Year", axis=alt.Axis(labelAngle=-45)),
      y=alt.Y("count()", title="Count"),
      color=alt.Color(
        "early_access", 
        title="Early Access",
        legend=alt.Legend(
          labelExpr="datum.label == 'true' ? 'Yes' : 'No'"  # rename labels
        )
      ),
    ).properties(height=CHART_HEIGHT, width="container", title="Game Releases per Year")
    st.altair_chart(release_trends_over_time_chart)
  with col2:
    score_vs_price = alt.Chart(filtered_df).mark_bar().encode(
      x=alt.X("regular_price:Q", title="Price", bin=alt.Bin(step=2.5)),
      y=alt.Y("count():Q", title="Count")
    ).properties(height=CHART_HEIGHT, width="container", title="Price")
    st.altair_chart(score_vs_price)
  col1, col2 = st.columns(2)
  with col1:
    score_over_time = alt.Chart(filtered_df[filtered_df['release_date'].notnull()]).mark_line().encode(
      x=alt.X("release_year:O", title="Release Year", axis=alt.Axis(labelAngle=-45)),
      y=alt.Y("mean(steam_score):Q", title="Median Steam Score", scale=alt.Scale(domain=[0,100]))
    ).properties(height=CHART_HEIGHT, width="container", title="Median Score over Time")
    st.altair_chart(score_over_time)
  with col2:
    tag_summary = (
      game_tags.merge(filtered_df, on="itad_uuid").groupby("tag")["peak_player_count"]
      .agg(["median", "count"])
      .query("count >= 15")
      .reset_index()
      .sort_values("median", ascending=False)
      .head(10)
    )
    st.altair_chart(
      alt.Chart(tag_summary).mark_bar().encode(
        x=alt.X("median", title="Median Peak Players"),
        y=alt.Y("tag:N", title="Tags").sort("-x")
      ).properties(height=CHART_HEIGHT, width="container", title="Top 10 Tags"),
      use_container_width=True
    )
  style_metric_cards(
    background_color="#1e1e1e",
    border_left_color="#4dabf7",
    border_color="#333",
    box_shadow=False
  )
  col1, col2, col3 = st.columns(3, gap="small")  
  with col1:
    median_peak = int(filtered_df["peak_player_count"].median())
    st.metric("Median Peak Players", f"{median_peak:,}")
  with col2:
    total_players = int(filtered_df["peak_player_count"].sum())
    st.metric("Total Peak Players", f"{total_players:,}")
  with col3:
    st.metric("Number of Games", len(filtered_df))
  with st.expander("🔍 View Filtered Games"):
    st.dataframe(
      filtered_df[["rank", "title", "steam_score", "regular_price", "peak_player_count"]]
    )

  # if chart_choice == "Overall Summary" and len(filtered_df):
  #   st.sidebar.empty()
    
  #   #------------ Release Month/Year ------------
  #   st.header("Release Month and Year")
  #   release_month_chart = alt.Chart(game_info[game_info['release_date'].notnull()]).mark_bar().encode(
  #     x=alt.X("release_month:O", axis=alt.Axis(labelAngle=0), title="Release Month"),
  #     y=alt.Y("count()")
  #   ).properties(height=300, width="container")
  #   release_year_chart = alt.Chart(game_info[game_info['release_date'].notnull()]).mark_bar().encode(
  #     x=alt.X("release_year:O", axis=alt.Axis(labelAngle=0), title="Release Year"),
  #     y=alt.Y("count()")
  #   ).properties(height=300, width="container")
  #   st.altair_chart(release_year_chart | release_month_chart, use_container_width=True)
    
  #   month_summary = (
  #     game_info[["release_month", "peak_player_count"]]
  #     .groupby('release_month')['peak_player_count']
  #     .agg(["count", "mean", "median"])
  #   ).reset_index()
  #   st.altair_chart(
  #     alt.Chart(month_summary).mark_bar().encode(
  #       x=alt.X("release_month:O", axis=alt.Axis(labelAngle=0), title="Release Month"),
  #       y=alt.Y("median")
  #     ).properties(height=300, width="container"),
  #     use_container_width=True
  #   )
  #   #------------ Price ------------
  #   st.header("Price and Score")
  #   price_count = alt.Chart(game_history_copy).mark_bar().encode(
  #     x=alt.X("regular_price:Q", title="Regular Price", bin=alt.Bin(step=5), scale=alt.Scale(domain=[0,70])),
  #     y=alt.Y("count()"),
  #   ).properties(height=300, width="container")
  #   percent_discount_count = alt.Chart(game_history[game_history["percent"] > 0]).mark_bar().encode(
  #     x=alt.X("percent:O", axis=alt.Axis(labelAngle=0), title="Percent", bin=alt.Bin(step=5)),
  #     y=alt.Y("count()")
  #   ).properties(height=300, width="container")
    
  #   st.altair_chart(price_count | percent_discount_count)
    
  #   #------------ Score ------------
  #   st.header("Score Distribution")
  #   score_count = alt.Chart(game_info).mark_bar().encode(
  #     x=alt.X("steam_score:Q", title="Steam Score", bin=alt.Bin(step=5), scale=alt.Scale(domain=[0,max(filtered_df['steam_score'])])),
  #     y=alt.Y("count()"),
  #   ).properties(height=300, width="container")
  #   st.altair_chart(score_count, use_container_width=True)
    
  #   #------------ Sale Percentages ------------
  #   st.header("Sales Data")
  #   sale_percent = alt.Chart(game_history[game_history["percent"] > 0]).mark_bar().encode(
  #     x=alt.X("percent", title="Sale Percent", bin=alt.Bin(step=5)),
  #     y=alt.Y("count()")
  #   )
  #   st.altair_chart(sale_percent, use_container_width=True)
  #   # ------------ Top Tags ------------
  #   st.header("Top Tags")
  #   tag_peak = game_tags.merge(game_info, on="itad_uuid")
  #   tag_summary = (
  #     tag_peak.groupby("tag")["peak_player_count"]
  #     .agg(["median", "count"])
  #     .query("count >= 15")
  #     .reset_index()
  #     .sort_values("median", ascending=False)
  #     .head(18)
  #   )
  #   st.altair_chart(
  #     alt.Chart(tag_summary).mark_bar().encode(
  #       x=alt.X("median", title="Median Peak Players"),
  #       y=alt.Y("tag:N", title="Tags").sort("-x")
  #     )
  #     .properties(height=450, width="container"),
  #     use_container_width=True
  #   )