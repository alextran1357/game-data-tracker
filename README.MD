# 🎮 Game Sale Timing Analysis

## 📌 Project Overview
This project analyzes **how and when Steam games go on sale**, and whether discounts relate to game success (measured by reviews, popularity, and visibility).  
I built a dataset of **8,500+ games** and **460k+ historical sale events**, cleaned and structured it, and explored discount strategies across genres, release timing, and review tiers.  
The project demonstrates my ability to **collect messy real-world data, engineer features, run exploratory analysis, and communicate insights clearly**.

---

## 🚀 Motivation
Games release very often, and I want to know:
- Is there a month trend for when more successful games release compared to less successful games?
- Do successful games discount differently than less popular ones?  
- Does timing/depth of sales influence player engagement or reviews?  

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

4. **Exploratory & Statistical Analysis
   - Conducted formal tests and regression analysis for the research paper to quantify relationships between pricing and player engagement.
   - Explored distributions of price, review score, release month, and sale percentage.

5. **Interactive Dashboard Development
   - Built a Streamlit app for interactive exploration of sale and engagement patterns.
   - Integrated dynamic filtering, custom Altair visuals, and metric cards for key KPIs.
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