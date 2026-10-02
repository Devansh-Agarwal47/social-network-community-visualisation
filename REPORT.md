# Interactive Social Media Community and Information-Flow Visualisation

**Type:** Graph Visualization course project  |  **Author:** Devansh Agarwal

---

## 1. Problem and objectives

Social platforms are graphs: people are **vertices**, friendships are **edges**. The questions a platform asks are graph questions:
*Who are the influencers? Which communities exist? Who should a new user follow? How far does a post travel?*

This project builds a complete, working application that answers those questions, from raw data to an interactive web site:

1. create a realistic dataset with deliberate errors, and **clean** it,
2. **analyse** the graph (degree, density, components, centrality),
3. **detect communities** and visualise them,
4. store everything in a **database** and serve it through an **API**,
5. show it in an **interactive website** (dashboard, network, communities, users),
6. **predict the community** of a new user, recommend people, and save the user,
7. **simulate information spread** (viral marketing and fake-news control).

## 2. Architecture

```
Stage 1  synthetic CSV data (with 2-5% errors)         stage1_create_dataset.py, stage1_explore_data.py
Stage 2  cleaning: duplicates, missing values, columns  stage2_clean_data.py          -> data/clean/*.csv
Stage 3  graph analysis (NetworkX)                      stage3_graph_analysis.py      -> node metrics, charts
Stage 4  communities (Louvain) + network picture        stage4_communities.py         -> communities.csv
Stage 5  SQLite database                                stage5_database.py            -> data/social.db
Stage 6  Flask API                                      stage6_api.py                 -> /api/... JSON
Stage 7+8 website (HTML, CSS, JavaScript, D3) + fetch() stage7_frontend.py            -> frontend/
Stage 9  new user: community prediction, people to follow, save   stage9_recommender.py
Stage 10 information spread simulation                  stage10_spread.py
```
Data flows one way: **CSV -> pandas -> NetworkX -> database -> API -> browser.** Each stage reads the output of the previous one, so every stage can be run and checked on its own.

Tools: Python 3, pandas, NumPy, NetworkX, Matplotlib, SQLite (`sqlite3`), Flask, D3.js v7. Nothing is "trained" on a GPU: the community detection, the recommender and the spread model are classical algorithms that run in seconds.

## 3. Data (Stage 1)

Real social-media data is private, so the data is **synthetic** but built to behave like a real network: six interest groups, dense friendships inside a group, sparse between groups, three "influencer" hubs per group, and ten users with no friends.

| Table | Rows (raw) | Important columns |
|---|---|---|
| users | 1,010 (1,000 people + 10 duplicates) | user_id, username, age, city, interest, account_type, joined_date |
| connections | 4,008 | user_id_1, user_id_2, connected_on, interaction_count (one row = one edge) |
| posts | 3,482 | post_id, user_id, posted_at, text, hashtags, likes, shares, comments |

**Planted errors** (so cleaning can be demonstrated): 45 of 1,010 user rows (4.5%), 147 of 4,008 connection rows (3.7%), 129 of 3,482 post rows (3.7%). They include duplicates, missing values, impossible ages, inconsistent city spellings and date formats, self-friendships, unknown user ids, friendships written both ways, and impossible dates. A hidden *answer key* records every planted error. It is used **only to check** the cleaning, never to do it.

Stage 1 exploration (pandas) finds all **17 error types**, and every count equals the answer key.

## 4. Cleaning (Stage 2)

| Table | Raw -> clean rows | What was done |
|---|---|---|
| users | 1,010 -> 1,000 | 10 duplicates dropped; 4 impossible ages set to missing, then all 12 missing ages filled with the median age of the user's interest group; 8 city spellings normalised; 6 missing cities set to "Unknown"; 5 dates converted; email column dropped (personal data, not needed) |
| connections | 4,008 -> 3,897 | 43 duplicates, 20 self-connections, 24 unknown users and 24 friendships written both ways removed (pairs sorted so A-B = B-A); 36 missing or impossible dates estimated and flagged `date_estimated` |
| posts | 3,482 -> 3,370 | 34 duplicates, 17 unknown users, 34 empty texts, 27 impossible timestamps removed; 17 negative like-counts replaced by the median (8) |

Result: all 15 problem counts go from non-zero to **0** (figure `outputs/stage2_before_after.png`). The row counts match the answer key exactly (1,000 / 3,897 / 3,370).

*Design choices worth defending:* a friendship with a bad date is real, so its date is estimated and flagged instead of deleting the edge; a missing city becomes "Unknown" because a wrong guess is worse than an honest blank; an ISO date such as 2021-03-05 must not be read day-first, so ISO and non-ISO dates are parsed separately.

## 5. Graph analysis (Stage 3)

The clean tables become a **simple, undirected graph** (NetworkX): 1,000 vertices, 3,897 edges.

| Measure | Value | Meaning |
|---|---|---|
| Density | 0.0078 | 0.78% of all possible friendships exist |
| Average degree | 7.79 (median 6, max 110) | typical user has about 8 friends; a few hubs have 60-110 |
| Isolated vertices (degree 0) | 10 | users with no friends |
| Pendent vertices (degree 1) | 16 | users with exactly one friend |
| Connected components | 11 | one giant component (990 users, 99%) + 10 isolated users |
| Diameter / average path (giant component) | 6 / 3.26 hops | any two connected users are about 3 steps apart ("small world") |
| Global clustering | 0.042 | low: hubs and communities, but few tight friend triangles |
| Edges in complement graph | 495,603 | n(n-1)/2 - 3,897 = 499,500 - 3,897 |

**Centrality** answers "who matters": *degree* (most friends: `ira_shah53`, 110), *PageRank* (friends of important people), *betweenness* (bridges between groups: `nisha_roy34` is the strongest bridge although she has fewer friends than the top hubs). **Homophily:** 82.3% of friendships join users with the same interest, against 17.9% expected at random. Checks: handshake lemma (sum of degrees = 2 x edges), components add up to n, degrees computed two ways agree (8 checks).

## 6. Community detection (Stage 4)

**Louvain** groups users to maximise **modularity** (share of edges inside groups minus the share expected by chance). It sees only the friendships, never the interest column.

* 6 communities + 10 isolated users; **modularity 0.624** (shuffling the same group sizes at random gives -0.003).
* Communities: C1 Tech 237, C2 Sports 196, C3 Music 168, C4 Food 154, C5 Travel 138, C6 Fashion 97.
* **Purity 0.964, NMI 0.903** against the declared interests: the detected groups match the real ones, although the algorithm never saw them.
* Tightest community: C1 (87% of friendship ends stay inside); loosest: C6 Fashion (69%).
* Figures: `stage4_network_communities.png`, `stage4_communities_vs_interests.png` (same layout coloured by declared interest vs found community).

## 7. Database, API and website (Stages 5-8)

**Database (SQLite).** Tables `communities`, `users`, `connections`, `posts`, `post_hashtags` plus the view `friendships` (every edge in both directions). Primary keys, foreign keys, `CHECK` rules (age 13-100, no negative likes, `user_id_1 < user_id_2`, no self-friendship) and indexes are defined in the schema, so the database itself refuses bad data. Nine checks confirm that it agrees with the CSV files and the graph.

**API (Flask).** Read-only endpoints for users (filter, search, paging), profiles, friends, "people you may know" (friends-of-friends ranked by mutual friends), the network (nodes + links, with filters), communities, posts, hashtags, statistics; write endpoints `POST /api/predict` and `POST /api/users`; spread endpoints. Queries use `?` placeholders (safe against SQL injection); bad input returns a readable 400 error; the reading connection is opened read-only.

**Website.** One page with tabs: **Dashboard** (KPIs, community sizes, friendship heat-map between communities, top users, hashtags), **Network** (D3 force layout on a canvas: zoom, pan, drag, hover highlights friends, click opens a profile; filters by community, minimum friends, size), **Communities**, **Users**, **Spread**, **Join**. The browser calls the API with `fetch()` (Stage 8), so the website shows live database content.

## 8. New users: prediction, recommendation, saving (Stage 9)

**Prediction.** A *Naive Bayes* classifier: for each community, multiply how likely its members are to have this interest, city, age, account type, hashtags and known contacts (sum of logarithms, +1 smoothing); a softmax with a tuned temperature turns the scores into percentages. It learns from the database and re-learns after every new user.

**Accuracy** (leave-one-out: each user is hidden, then predicted; 990 users):

| Information given | Accuracy |
|---|---|
| interest only | 96.4% |
| interest + city + age + account type | 96.4% |
| + 3 hashtags the user posted | 96.1% |
| + 3 people the user knows | 96.4% |
| city + age + account type only (no interest) | 65.1% |
| 3 random friends only | 93.6% |
| *always guessing the biggest community* | *23.9%* |

Honest reading: **interest and known friends do almost all the work**; city and age add almost nothing. Caveat: the communities were computed from all friendships (including the hidden user's), so the "people you know" result is slightly optimistic.

**Recommendation.** Score = probability of the candidate's community + same interest + same city + popularity + mutual contacts with the people the new user already knows. Six suggestions from the predicted community plus two *bridge users* (many friends outside their group) from the runner-up community.

**Saving.** One database transaction inserts the user and the chosen connections, raises the friends' degrees, and recomputes every community's statistics; if anything fails, nothing is saved. Tests confirm: foreign keys intact, sum of degrees = 2 x edges, community sizes add to 1,001, duplicate usernames rejected.

## 9. Information flow (Stage 10)

**Model: independent cascade.** Seed users post at round 0; each user who receives it gets one chance to pass it to each friend with probability *p*.

*A. Marketing: who should post first?* (5 seeds, p = 0.12, 300 runs): the most connected users, top "bridge" users and one-top-user-per-community reach about **30-31%** of the network; five random users reach **25.6%**. Hubs beat random seeds, but only modestly, because this network is densely connected everywhere.

*Tipping point:* with 5 top-degree seeds, reach rises from 1.7% (p = 0.02) and 12% (p = 0.08) to 30% (p = 0.12) and 80% (p = 0.30). A small increase in how shareable a post is changes its reach enormously.

*B. Fake news: block users to stop a rumour* (starts at a random user, p = 0.12): average reach is about 81 users with no blocking. Blocking the 5 most connected users cuts it to 29, the top 10 to 8, and the top 40 to about **2**, while blocking 40 *random* users only reaches 51. Reason: 68% of rumours die under 15 users, and the 31% that grow beyond 100 users cause 98% of all spreading; blocking hubs removes those big outbreaks.

Validation (9 checks): p = 0 reaches only the seeds; p = 1 reaches the whole connected group; nobody is reached twice; same random seed gives the same run; reach grows with p; blocked users are never reached; hubs beat random; blocking hubs beats blocking random; k = 0 gives the same baseline for every method. The website animates one run round by round on the network.

## 10. Verification summary

| Stage | Automated checks |
|---|---|
| 1 exploration: found vs planted errors | 17 / 17 match |
| 2 cleaning (validation + answer key) | 13 |
| 3 graph analysis | 8 |
| 4 communities | 7 |
| 5 database | 9 |
| 6-9 API, web pages, join, spread endpoints | 75 |
| 9 recommender | 6 (+ leave-one-out accuracy test) |
| 10 spread model | 9 |
| **Total** | **144** |

The website was also tested in a real browser (login, every tab, filters, search, profile panel, creating a user, spread animation, phone-width layout) with no JavaScript errors.

## 11. Limitations (say them before the examiner does)

* **Synthetic data.** The results describe a designed network, so they show that the *methods* work, not facts about real people. The pipeline accepts any CSVs with the same columns.
* **The prediction is mostly the interest column.** With no interest it drops to 65%.
* **Sign-in is a demo gate** checked in the browser; the API has no authentication, so anyone who can reach it can add users.
* **SQLite** allows one writer at a time and NetworkX keeps the graph in memory: fine for 1,000 users, but a real platform would use PostgreSQL plus a graph database or a distributed graph engine.
* **Independent cascade** uses one probability *p* for every friendship; real sharing depends on content, time and person.
* **Clustering is low (0.04),** so the network has hubs and communities but not the many friend triangles of real social networks.

## 12. Conclusion and future work

The project delivers the full path from raw data to an interactive product: cleaning, graph theory, community detection, database, API, website, recommendation and information-flow simulation. It shows that community structure can be recovered from friendships alone (purity 0.96), that a handful of hubs control how far a post or rumour travels, and that blocking hubs is far more effective than blocking random users.
Future work: real datasets (for example public SNAP Facebook/Twitter graphs), directed follow edges, time-stamped diffusion, graph neural networks for recommendation, and real authentication.

---

## Appendix A. How to run everything (in order)

```
pip install pandas numpy matplotlib networkx flask
python stage1_create_dataset.py     python stage1_explore_data.py
python stage2_clean_data.py         python stage3_graph_analysis.py
python stage4_communities.py        python stage5_database.py
python stage9_recommender.py        python stage10_spread.py
python stage6_test_api.py           # 75 automatic API tests
python stage6_api.py                # website + API at http://127.0.0.1:5000  (login: demo / graph123)
```
`stage7_frontend.py` is used automatically by `stage6_api.py` to write the `frontend/` folder.

## Appendix B. Five-to-seven-minute demo (suggested order)

1. **(30 s) Idea.** "Social networks are graphs; I built the whole pipeline and a website on top."
2. **(45 s) Data and cleaning.** Show `stage2_before_after.png`: "15 kinds of problems, all zero after cleaning; row counts match the hidden answer key."
3. **(60 s) Dashboard.** 1,000 users, 3,897 friendships, density 0.78%, 82% of friendships inside communities; the heat-map.
4. **(90 s) Network.** Colour by community; hover a hub; click `ira_shah53` (110 friends); filter one community; search a user.
5. **(45 s) Communities.** Click Music: top users, hashtags, links to other communities. "Louvain never saw the interest column, yet purity is 0.96."
6. **(90 s) Join.** Enter a Music fan in Jaipur who knows `nisha_roy34`; show the prediction, the reasons and the suggested people; create the account; watch the Dashboard go from 1,000 to 1,001 and find the new user in the network.
7. **(90 s) Spread.** Run experiments: hubs vs random, blocking hubs vs random users; then animate a post on the network.
8. **(30 s) Limits and conclusion.** Synthetic data, demo login, prediction driven by interest.

## Appendix C. Likely viva questions

1. **What is a graph here?** Vertices = users, edges = friendships; simple undirected graph (no loops, no repeated edges).
2. **What is degree, isolated, pendent?** Degree = number of friends; isolated = degree 0 (10 users); pendent = degree 1 (16 users).
3. **What is density?** Edges divided by the maximum n(n-1)/2 = 499,500; here 0.0078.
4. **What is the complement graph?** All friendships that do *not* exist: 499,500 - 3,897 = 495,603 edges.
5. **Why is the average path only about 3 hops in a graph this sparse?** Hubs and a few cross-community friendships act as shortcuts (small-world effect).
6. **Difference between degree, betweenness and PageRank?** Number of friends / how often a user lies on shortest paths (a bridge) / importance inherited from important friends.
7. **What does Louvain do and what is modularity?** It moves users between groups to maximise modularity, the fraction of edges inside groups minus what random wiring would give (0.62 here).
8. **How do you know the communities are real?** They match the hidden interests (purity 0.96, NMI 0.90), and shuffled labels give modularity of about 0.
9. **Why synthetic data?** Real social data is private; synthetic data lets me plant known errors and know the ground truth. The pipeline works on any CSVs with these columns.
10. **How did you clean the data without cheating?** The cleaning code uses only rules found in the data; the answer key is used at the end to check counts.
11. **Why SQLite, and would it scale?** One file, no server, part of Python. For a real platform: PostgreSQL for tables and a graph database for multi-hop queries.
12. **How does the new-user prediction work?** Naive Bayes over interest, city, age, type, hashtags and known contacts; accuracy 96.4% with interest, 65% without it (leave-one-out).
13. **What is the weakness of that model?** It mostly copies the interest column, and the "people you know" test is slightly optimistic because communities were computed with all friendships.
14. **What is the independent cascade model?** Each newly informed user gets one chance to inform each friend with probability p; run many times and average.
15. **Main finding on spread?** A small rise in p sharply raises reach (tipping point), hubs beat random seeds by a modest margin, and blocking hubs removes the large outbreaks: 40 hubs cut a rumour to about 2 users, 40 random users to 51.
16. **How is bad input handled?** The form and the API validate every field; the database has its own constraints; saving a user is one transaction, so a failure leaves nothing half-saved.
17. **What would you improve next?** Real datasets, directed follow edges, time-aware diffusion, graph neural networks, proper authentication.
