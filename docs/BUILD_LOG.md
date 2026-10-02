# Social network application: build log

Roadmap: build the **data science part** first (Stages 1-4), then the **application part** (Stages 5-10).

| Stage | What | Status |
|---|---|---|
| 1 | Synthetic dataset (about 1,000 users, 2-5% errors) and pandas exploration | **done** |
| 2 | Data cleaning (remove duplicates, fix missing values, select columns) | **done** |
| 3 | Graph analysis with NetworkX (users, connections, most connected, density) | **done** |
| 4 | Community detection (Louvain) and visualisation | **done** |
| 5 | SQLite database | **done** |
| 6 | Flask backend and API (`/api/users`, `/api/network`, `/api/communities`, `/api/posts`) | **done** |
| 7 | Frontend pages (login, dashboard, network, communities, users) | **done** |
| 8 | Connect frontend to backend (`fetch("/api/network")`) | **done** |
| 9 | Graph intelligence: predict a new user's community, recommend people, save the user (`stage9_recommender.py`) | **done** |
| 10 | Information flow: spread simulation (`stage10_spread.py`), Spread tab, report and presentation guide | **done** |

## Stage 1: run it
```
pip install -r requirements.txt
python stage1_create_dataset.py     # writes data/raw/*.csv and data/answer_key/anomalies.csv
python stage1_explore_data.py       # profiles the data, writes outputs/stage1_data_profile.txt
```
Read `DATA_DICTIONARY.md` for the meaning of every column.

## Stage 2: clean it
```
python stage2_clean_data.py         # raw CSV -> data/clean/*.csv, outputs/stage2_cleaning_log.txt, outputs/stage2_before_after.png
```
In VS Code: open the folder, open the file, press Run (or use Run and Debug -> "Stage 2 - clean data"). Every `# %%` line is a runnable cell.

| Table | Raw rows | Clean rows | What changed |
|---|---|---|---|
| users | 1010 | 1000 | 10 duplicates removed; ages fixed (median of interest group); cities normalised, 6 set to Unknown; dates unified; email dropped |
| connections | 4008 | 3897 | duplicates, self-links, unknown users, both-ways repeats removed; 36 bad dates estimated and flagged `date_estimated` |
| posts | 3482 | 3370 | duplicates, unknown users, empty text, impossible timestamps removed; 17 negative likes set to median |

## Stage 3: analyse the graph
```
pip install -r requirements.txt
python stage3_graph_analysis.py     # data/graph/node_metrics.csv, outputs/stage3_graph_report.txt + 2 figures
```

## Stage 4: find communities
```
python stage4_communities.py        # data/graph/communities.csv, community_summary.csv, outputs/stage4_*.png
```
Louvain finds 6 communities (modularity 0.62) using friendships only; they match the declared interests with purity 0.96.

## Stage 5: database
```
python stage5_database.py           # builds data/social.db and runs 11 example SQL queries
```
Tables: communities, users, connections, posts, post_hashtags, plus the view `friendships` (every edge in both directions).

## Stage 6: API
```
pip install flask
python stage6_api.py                # starts the server; open http://127.0.0.1:5000  (stop with Ctrl+C)
python stage6_test_api.py           # 31 automatic tests, no server needed
```

## Stages 7 and 8: the web site
```
python stage6_api.py                # one server = API + web site;  open http://127.0.0.1:5000
```
Sign in with `demo` / `graph123` (demo gate only, not real security). Pages: Dashboard, Network (D3 force layout on a canvas, zoom, drag, hover, click for profile), Communities, Users.
Files: `frontend/index.html`, `style.css`, `app.js`, `vendor/d3.min.js` (D3 v7, ISC licence, bundled so it works offline).
The page must be opened through the server (http://127.0.0.1:5000), not by double-clicking index.html, because it calls `/api/...` on the same address.

## Stage 9: new users (Join tab)
```
python stage9_recommender.py        # tests the prediction model (leave-one-out accuracy) and prints a demo
python stage6_api.py                # web site: Join tab -> predict community, suggest people, create user in social.db
```
Files needed together in one folder: `stage6_api.py`, `stage7_frontend.py` (writes the frontend/ folder), `stage9_recommender.py`, and `data/social.db` (made by `stage5_database.py`).
New users are saved only in `data/social.db`. Running `stage5_database.py` again rebuilds the database from the CSV files and removes them.

## Stage 10: information flow
```
python stage10_spread.py            # marketing + fake-news experiments, 9 checks, outputs/stage10_spread.png and report
python stage6_api.py                # Spread tab (experiments) and Network tab (Simulate a post: animated spread)
```
Model: independent cascade. The written report and presentation guide are in `REPORT.md`. Files needed together: stage6_api.py, stage7_frontend.py, stage9_recommender.py, stage10_spread.py, data/social.db.
