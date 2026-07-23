# 🎮 Steam Game Sales Analysis & Dashboard

## 💻 Dashboard
[Open in Streamlit!](https://alextran1357-game-data-tracker-srcdashboard-u70h5x.streamlit.app/)

## 📌 Project Overview
This project analyzes **when Steam games first go on sale and how deep those first discounts are**.
I built a dataset of **8,500+ games** and **460k+ historical price events**, cleaned and structured it, and created a dashboard for comparing discount timing across game segments.
The project demonstrates my ability to **collect messy real-world data, engineer features, run exploratory analysis, and communicate insights clearly**.

## 🗂️ Repository Layout

- `data/processed/` — final Parquet tables used by the dashboard and analysis.
- `data/interim/` — generated handoff files between pipeline stages.
- `data/raw/` — local SteamDB inputs and ITAD response caches; ignored by Git.
- `notebooks/` — exploratory analysis and the research report.
- `src/pipeline/` — data collection notebooks and the repeatable analysis-table builder.
- `src/dashboard.py` — stable Streamlit deployment entry point.
- `reports/` — generated data-quality and analytical reports.

See [`data/README.md`](data/README.md) and [`src/pipeline/README.md`](src/pipeline/README.md) for file-level details.

---

## 🚀 Motivation
The project asks:
- How soon after release do games receive their first observed discount?
- How deep is that first discount?
- How does timing differ across tags, release years, review scores, and Early Access status?

I wanted to explore these questions by combining **Steam game lists** with the **IsThereAnyDeal API** for metadata and price history.

---

## 📂 Data Sources
- **SteamDB (Game Titles)**  
  SteamDB does not allow scraping, so I manually collected game titles by highlighting and pasting them into text files across multiple custom review tiers. This resulted in ~8,300 unique titles.  
- **IsThereAnyDeal (ITAD) API**  
  Used to resolve titles into UUIDs, fetch game metadata (release dates, tags, review scores, maturity, etc.), and collect historical **event-based pricing data** (discounts, sale events, regular price).  

---

## 🔄 Process
1. **Data Collection**  
   - Batched API calls with retry + caching to collect ~460k sale events.  
   - Designed schema: `game_info`, `game_tags`, `game_history`.  

2. **Cleaning & Preprocessing**  
   - Resolved missing and inconsistent records.
   - Normalized datatypes.
   - Flagged anomalies such as invalid discounts or missing sale dates.

3. **Feature Engineering**  
   - Per-game metrics: `time_to_first_sale`, `num_sales`, `max_discount`, `avg_discount`.  
   - Created lifecycle summaries: min vs max vs avg discount per game.

4. **Exploratory & Statistical Analysis**
   - Conducted formal tests and regression analysis for the research paper to quantify relationships between pricing and player engagement.
   - Explored distributions of price, review score, release month, and sale percentage.

5. **Interactive Dashboard Development**
   - Built a Streamlit app focused on first-discount timing and depth.
   - Added simple filters and charts while keeping the dashboard dataset small.
---

## ⚡ Challenges & Problem-Solving
This project wasn’t a clean dataset exercise — it forced me to deal with real-world messiness and make design choices along the way:

### 🧹 Data & Collection
- **Messy & incomplete data**  
  Many games had missing release dates or reviews. I created boolean flags (`has_release_date`) so I could filter vs impute consistently.  
- **Data Gathering Limitations**  
  Data gathering was constrained by SteamDB’s search and pagination limits. Because only a limited number of entries were accessible at a time, I collected a subset of games for each Steam rating tier. As a result, the dataset contains far fewer poorly rated games compared to well-rated ones. This imbalance reflects both the natural distribution of ratings on Steam and the practical limitations of manual data collection. Consequently, the data may not fully represent the true proportion of low-rated games in the broader Steam catalog. 
- **Delisted or hidden games**  
  SteamDB includes titles that no longer exist on Steam. These explained some of the missing review/date data and forced me to design around incomplete metadata.  
- **Event-based sales data**  
  ITAD only logs *price changes*, not continuous snapshots. At first, this made analysis confusing (many “0% discount” rows).  
  I solved this by treating the dataset as an **event log** and then engineering per-game summaries like “max discount” and “time to first sale.”  

### ⚙️ Data Integrity & Quality
- **API reliability & efficiency**  
  ITAD has strict rate limits. I implemented batching, retries, and response caching to reliably collect ~460k sale events without hitting limits.  
- **Anomalies**  
  Found impossible discounts (e.g., 120%). Learned to investigate, validate against context, and decide to drop single noisy entries.  
- **Skewed variables**  
  Review counts ranged from 1 to 2.5M, hiding most of the distribution. I used log-scaling to reveal long-tail patterns and interpret them properly.

### 📊 Research & Statistical Analysis
- **Learning new statistical methods**  
  To validate findings, I studied correlation tests and non-parametric comparisons for skewed data. The hard part wasn't just applying them; it was understanding assumptions and interpreting results responsibly and translating stats into meaningful insights for readers.
- **Explaining insights clearly**  
  Turning statistical significance into plain-language pushed me to balance technical accuracy with storytelling.

### 🖥️ Dashboard Design & Development
- **Learning Streamlist from scratch**
  I had never used Streamlit before, so building the dasboard meant learning how components, layout, and state work while figuring out how to connect everything to my data.
- **Designing something that felt right**
  I don't have much of a design background, so a lot of the time went into experimenting with colors and layouts until it looked clean and easy to read. There were many times I had to rewrite big parts of the code until I was happy with it.

---

## 🏆 Accomplishments
- Engineered a dataset of 8,500+ games and 460k+ sales events.  
- Implemented robust API pipelines with batching, retries, and caching.  
- Designed a clean fact/dimension schema (game info, sale history, tags).  
- Built derived features: min/max/avg discount, first-sale timing, seasonal clustering.  
- Validated insights with statistical tests (e.g., chi-squared on maturity vs review tier).  
- Produced a clear EDA → analysis workflow, showcasing my ability to go from messy raw data to structured insights.  
- Developed an interactive Streamlit dashbord to explore these patterns.
- Produced a full research analysis + visual app to demonstrate an end-to-end workflow.
---

## 🔮 Planned Extensions
- Add more games
- Extend lifecycle analysis to compare **indie vs AAA games**  
- Explore correlations between discount timing and long-term success  
- Implement game completion time from `howlongtobeat.com`
---
