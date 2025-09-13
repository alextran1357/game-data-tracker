# 🎮 Game Sale Timing Analysis

## 📌 Project Overview
This project explores **how and when games go on sale**, and whether discounts relate to success (reviews, popularity, etc.).  
The goal is to build a dataset of Steam games, merge it with historical pricing data, and analyze discount strategies across genres, release ages, and popularity tiers.

---

## 🚀 Motivation
Games release very often, and I want to know:
- Is there a month trend for when more successful games release compared to less successful games?
- Do successful games discount differently than less popular ones?  
- Does timing/depth of sales influence player engagement or reviews?  

I wanted to explore these questions by combining **Steam game lists** with the **IsThereAnyDeal API** for metadata and price history.

---

## 📂 Data Sources
- **SteamDB** → Grab titles from different tier of reviews
    - Excellent: 85–100
    - Good: 70–84
    - Mixed: 50–69
    - Poor: 30–49
    - Terrible: 1–29
- **IsThereAnyDeal (ITAD) API** → game UUIDs, release dates, stats, reviews, and price history  

---

## 🔄 Process & Checklist
- [x] Collect game titles from SteamDB (Handgrab 8000+ titles to avoid scraping their website)  
- [x] Resolve titles → ITAD UUIDs (batch API calls with retry handling)  
- [x] Collect game metadata (release date, tags, Steam review scores, stats)  
- [x] Store data as CSV/Parquet for reproducibility  
- [ ] Collect historical pricing data (sale events, discounts, regular price)  
- [ ] Merge price history with game metadata  
- [ ] Clean & preprocess (handle missing values, type conversions)  
- [ ] Exploratory Data Analysis (EDA) → discount patterns, lifecycle, seasonal trends  
- [ ] Compare **top vs. bottom performers**  
- [ ] Build visualizations / dashboard (PowerBI or Streamlit)  
- [ ] Model correlations (e.g., reviews before vs after sales)  
- [ ] Write final insights  

---

## 📊 Current Status
- ✅ Titles collected (~8,500 games from 2006–2025 Top 250 lists).  
- ✅ Metadata enriched (release dates, reviews, tags, ITAD stats).  
- ⏳ Working on historical sale data collection.  

---

## ⚡ Challenges & Learnings
- Handling **missing values** (release dates, Steam reviews).  
- Games listed in SteamDB but not visible on Steam → delisted titles.  
- Efficient **batching and retry logic** for ITAD API calls.  
- Designing the dataset in a **fact/dimension schema** for analysis (game info vs price history vs tags).  

---

## 🔮 Planned Extensions
- Incorporate **player count data** from Steam API or SteamSpy.  
- Explore **seasonality** (are discounts clustered around Summer/Winter sales?).  
- Add **genre/tag breakdowns** (e.g., are indie games discounted earlier?).  
- Deploy results as an **interactive dashboard**.  

---

## 🛠️ How to Run
1. Clone this repo  
2. Install requirements:  
   ```bash
   pip install -r requirements.txt
3. Add your ITAD API key in `constants.py`
4. Run scripts in `src/` to rebuild the dataset