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
   - Batched API calls with retry + caching to collect ~460k sale events  
   - Designed schema: `game_info`, `game_tags`, `game_history`  

2. **Cleaning & Preprocessing**  
   - Handled missing values (dates, reviews)  
   - Normalized datatypes (e.g., `uint8` for % values, datetime for release)  
   - Flagged anomalies (e.g., impossible 120% discount)  

3. **Exploratory Data Analysis (EDA)**  
   - Univariate: distribution of reviews, discounts, release dates  
   - Bivariate: maturity vs review tier, discount lifecycle per game  
   - Multivariate: seasonal discount clustering, tag distribution in Excellent-tier games  

4. **Feature Engineering**  
   - Per-game metrics: `time_to_first_sale`, `num_sales`, `max_discount`, `avg_discount`  
   - Created lifecycle summaries: min vs max vs avg discount per game 

---

## ⚡ Challenges & Problem-Solving
This project wasn’t a clean dataset exercise — it forced me to deal with real-world messiness and make design choices along the way:

- **Messy & incomplete data**  
  Many games had missing release dates or reviews. I created boolean flags (`has_release_date`) so I could filter vs impute consistently.  
- **Delisted or hidden games**  
  SteamDB includes titles that no longer exist on Steam. These explained some of the missing review/date data and forced me to design around incomplete metadata.  
- **Event-based sales data**  
  ITAD only logs *price changes*, not continuous snapshots. At first, this made analysis confusing (many “0% discount” rows).  
  I solved this by treating the dataset as an **event log** and then engineering per-game summaries like “max discount” and “time to first sale.”  
- **API reliability & efficiency**  
  ITAD has strict rate limits. I implemented batching, retries, and response caching to reliably collect ~460k sale events without hitting limits.  
- **Anomalies**  
  Found impossible discounts (e.g., 120%). Learned to investigate, validate against context, and decide to drop single noisy entries.  
- **Skewed variables**  
  Review counts ranged from 1 to 2.5M, hiding most of the distribution. I used log-scaling to reveal long-tail patterns and interpret them properly.  
- **EDA fatigue**  
  Some findings felt “obvious.” I learned to separate **scratchpad EDA** (for myself) from **polished analysis** (for others). This helped me focus on what’s portfolio-worthy.  

---

## 🏆 Accomplishments
- Engineered a dataset of **8,500+ games and 460k+ sales events**.  
- Implemented **robust API pipelines** with batching, retries, and caching.  
- Designed a clean **fact/dimension schema** (game info, sale history, tags).  
- Built **derived features**: min/max/avg discount, first-sale timing, seasonal clustering.  
- Validated insights with **statistical tests** (e.g., chi-squared on maturity vs review tier).  
- Produced a clear EDA → analysis workflow, showcasing my ability to go from messy raw data to structured insights.  

---

## 🔮 Planned Extensions
- Build an **interactive dashboard** (Streamlit) for exploring sales by tag/genre  
- Extend lifecycle analysis to compare **indie vs AAA games**  
- Explore correlations between discount timing and long-term success  

---

## 🛠️ How to Run
1. Clone this repo  
2. Install requirements:  
   ```bash
   pip install -r requirements.txt
3. Add your ITAD API key in `constants.py`
4. Run scripts in `src/` to rebuild the dataset