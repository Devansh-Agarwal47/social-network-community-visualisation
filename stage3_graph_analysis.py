"""
STAGE 3 -- GRAPH ANALYSIS WITH NETWORKX
clean CSV -> graph  ->  how many users / connections?  who is most connected?  how dense?  who is alone?

Graph words used here (from the course):
  vertex (node) = a user            edge = a friendship (undirected: A-B is the same as B-A)
  degree        = number of friends of a user
  density       = edges / maximum possible edges  n(n-1)/2      (0 = nobody connected, 1 = everybody connected)
  isolated      = degree 0          pendent = degree 1 (a "leaf")
  component     = a group of users who can reach each other through friends

Input : data/clean/users.csv, connections.csv, posts.csv   (made in Stage 2)
Output: data/graph/node_metrics.csv       (one row per user: degree, friends' interest mix, ... used in Stage 4+)
        outputs/stage3_graph_report.txt   (all numbers below)
        outputs/stage3_degree_distribution.png, outputs/stage3_top_users.png

HOW TO RUN IN VS CODE: open this file and press the Run triangle (or run "# %%" cells one by one, or: python stage3_graph_analysis.py)
Needs: pip install networkx pandas numpy matplotlib
"""
# %% 0. Setup
from pathlib import Path
import numpy as np
import pandas as pd
import networkx as nx
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

pd.set_option("display.width", 200)
BASE = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
CLEAN = BASE / "data" / "clean"
if not (CLEAN / "users.csv").exists():           # clean files sitting next to the script
    CLEAN = BASE
OUT, GRAPH_DIR = BASE / "outputs", BASE / "data" / "graph"
OUT.mkdir(exist_ok=True)
GRAPH_DIR.mkdir(parents=True, exist_ok=True)

report = []


def open_files(*paths):
    """Open the saved pictures in the computer's default image viewer (pass --no-open to skip)."""
    import subprocess, sys, os
    if "--no-open" in sys.argv:
        return
    for p in paths:
        try:
            if sys.platform == "darwin":
                subprocess.run(["open", str(p)])
            elif sys.platform.startswith("win"):
                os.startfile(str(p))
            else:
                subprocess.run(["xdg-open", str(p)])
        except Exception:
            pass


def say(text=""):
    print(text)
    report.append(str(text))


# %% 1. Load clean tables and BUILD THE GRAPH
users = pd.read_csv(CLEAN / "users.csv")
conns = pd.read_csv(CLEAN / "connections.csv")
posts = pd.read_csv(CLEAN / "posts.csv")

G = nx.Graph()                                                        # Graph = simple undirected graph
for row in users.to_dict("records"):                                  # every user becomes a vertex, with attributes
    G.add_node(row.pop("user_id"), **row)
G.add_edges_from(zip(conns["user_id_1"], conns["user_id_2"]))         # every connection row becomes an edge

n, m = G.number_of_nodes(), G.number_of_edges()
say("STAGE 3 GRAPH REPORT")
say("=" * 90)
say(f"Graph built: {n} users (vertices), {m} friendships (edges)")

# %% 2. Basic facts (Unit 1: vertices, edges, degree, density)
deg = pd.Series(dict(G.degree()), name="degree")
max_edges = n * (n - 1) // 2
isolated = deg[deg == 0].index.tolist()
pendent = deg[deg == 1].index.tolist()
comps = sorted(nx.connected_components(G), key=len, reverse=True)
giant = G.subgraph(comps[0])

say("\n--- A. BASIC FACTS")
facts = {
    "users (vertices)": n,
    "friendships (edges)": m,
    "maximum possible edges  n(n-1)/2": max_edges,
    "density  (edges / max possible)": round(nx.density(G), 5),
    "average degree  (2m / n)": round(2 * m / n, 2),
    "median degree": float(deg.median()),
    "highest degree": int(deg.max()),
    "lowest degree": int(deg.min()),
    "isolated users (degree 0)": len(isolated),
    "pendent users (degree 1)": len(pendent),
    "edges in the complement graph  (max - m)": max_edges - m,
    "connected components": len(comps),
    "users in the biggest (giant) component": len(giant),
    "share of users in the giant component": f"{100 * len(giant) / n:.1f}%",
    "diameter of giant component (longest shortest path, hops)": nx.diameter(giant),
    "average shortest path in giant component (hops)": round(nx.average_shortest_path_length(giant), 2),
    "global clustering (are my friends friends with each other?)": round(nx.transitivity(G), 3),
}
for k, v in facts.items():
    say(f"  {k:<62} {v}")
say("\n  Reading: density is tiny because a real person knows only a small part of everyone.")
say("  Reading: about 3 hops between almost any two users is the 'small-world' effect. Clustering is low here (0.04), so this")
say("           network has hubs and communities but few tight friend triangles; Stage 4 will show the communities.")

# %% 3. Who is most connected?  (degree, plus two smarter measures)
say("\n--- B. MOST CONNECTED USERS (top 10 by number of friends)")
metrics = users.set_index("user_id")[["username", "full_name", "city", "interest", "account_type", "is_verified"]].copy()
metrics["degree"] = deg
metrics["degree_rank"] = metrics["degree"].rank(ascending=False, method="min").astype(int)
metrics["pagerank"] = pd.Series(nx.pagerank(G))                        # friends of important people are important
metrics["betweenness"] = pd.Series(nx.betweenness_centrality(G))       # how often a user sits on shortest paths = "bridge"
metrics["clustering"] = pd.Series(nx.clustering(G))
metrics["component"] = -1
for i, c in enumerate(comps):
    metrics.loc[list(c), "component"] = i
top = metrics.sort_values("degree", ascending=False).head(10)
say(top[["username", "city", "interest", "account_type", "degree", "pagerank", "betweenness"]].round(4).to_string())

say("\n  Top 10 by PageRank (importance, not just friend count):")
say(metrics.sort_values("pagerank", ascending=False).head(10)[["username", "interest", "degree", "pagerank"]].round(4).to_string())
say("\n  Top 10 'bridges' by betweenness (users connecting different parts of the network):")
say(metrics.sort_values("betweenness", ascending=False).head(10)[["username", "interest", "degree", "betweenness"]].round(4).to_string())

# %% 4. Isolated users and small components
say("\n--- C. ISOLATED AND SMALL COMPONENTS")
say(f"  Isolated users (no friends): {len(isolated)}  -> {', '.join(isolated[:12])}{' ...' if len(isolated) > 12 else ''}")
say(f"  Component sizes (largest first): {[len(c) for c in comps[:10]]}{' ...' if len(comps) > 10 else ''}")
say("  Note: isolated users are real accounts. Community detection (Stage 4) will treat them as their own 'group of one'.")

# %% 5. Does the network match the data? (homophily = same interest -> friends)
say("\n--- D. DO FRIENDS SHARE INTERESTS?  (homophily)")
interest = users.set_index("user_id")["interest"]
same = (conns["user_id_1"].map(interest) == conns["user_id_2"].map(interest))
say(f"  Friendships between users with the SAME interest: {same.mean() * 100:.1f}%")
sizes = interest.value_counts()
expected = ((sizes / n) ** 2).sum()
say(f"  If friendships were random we would expect only:   {expected * 100:.1f}%")
say("  -> Interest groups are clearly visible in the graph, so community detection in Stage 4 has real structure to find.")
mix = pd.crosstab(conns["user_id_1"].map(interest), conns["user_id_2"].map(interest))
mix = mix.add(mix.T, fill_value=0).astype(int)
say("\n  Friendships between interest groups (diagonal = inside a group; a diagonal pair is counted twice):")
say(mix.to_string())

say("\n--- E. AVERAGE DEGREE BY USER TYPE")
say(metrics.groupby("account_type")["degree"].agg(["count", "mean", "max"]).round(2).to_string())
say("\n--- F. AVERAGE DEGREE BY CITY")
say(metrics.groupby("city")["degree"].agg(["count", "mean"]).round(2).sort_values("mean", ascending=False).to_string())

# %% 6. Validate the numbers (cross-check with independent calculations)
say("\n--- VALIDATION")
checks = {
    "vertices = number of rows in users.csv": n == len(users),
    "edges = number of rows in connections.csv (clean: one row per friendship)": m == len(conns),
    "handshake lemma: sum of degrees = 2 x edges": int(deg.sum()) == 2 * m,
    "edges + complement edges = n(n-1)/2": m + facts["edges in the complement graph  (max - m)"] == max_edges,
    "component sizes add up to n": sum(len(c) for c in comps) == n,
    "no self-loops": nx.number_of_selfloops(G) == 0,
    "degree from pandas (counting connections table) = degree from NetworkX":
        bool((pd.concat([conns["user_id_1"], conns["user_id_2"]]).value_counts().reindex(deg.index).fillna(0).astype(int) == deg).all()),
    "PageRank adds up to 1": abs(metrics["pagerank"].sum() - 1) < 1e-6,
}
for k, v in checks.items():
    say(f"  {'PASS' if v else 'FAIL'}  {k}")

# %% 7. Save node metrics + report
metrics.reset_index().to_csv(GRAPH_DIR / "node_metrics.csv", index=False)
say(f"\nSaved {GRAPH_DIR / 'node_metrics.csv'}  ({len(metrics)} users x {metrics.shape[1] + 1} columns)")

# %% 8. Figures
palette = {"Tech": "#4c78a8", "Sports": "#f58518", "Music": "#54a24b", "Food": "#e45756", "Travel": "#72b7b2", "Fashion": "#b279a2"}

fig, ax = plt.subplots(1, 2, figsize=(12, 4.6))
ax[0].hist(deg, bins=range(0, int(deg.max()) + 2, 1 if deg.max() < 60 else 2), color="#4c78a8", edgecolor="white")
ax[0].axvline(deg.mean(), color="#e45756", ls="--", label=f"average = {deg.mean():.1f}")
ax[0].set_xlabel("degree (number of friends)"); ax[0].set_ylabel("number of users")
ax[0].set_title("Degree distribution"); ax[0].legend()
counts = deg.value_counts().sort_index()
ax[1].loglog(counts.index[counts.index > 0], counts[counts.index > 0], "o", color="#4c78a8", alpha=.8)
ax[1].set_xlabel("degree (log scale)"); ax[1].set_ylabel("users (log scale)")
ax[1].set_title("Same data on log-log axes\n(most users have under 20 friends, a small group of hubs has 60-110)")
plt.tight_layout(); plt.savefig(OUT / "stage3_degree_distribution.png", dpi=140); plt.close()

t = metrics.sort_values("degree").tail(15)
fig, ax = plt.subplots(figsize=(8, 5.5))
ax.barh(t["username"], t["degree"], color=[palette.get(i, "#999") for i in t["interest"]])
ax.set_xlabel("number of friends"); ax.set_title("15 most connected users (colour = interest)")
handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in palette.values()]
ax.legend(handles, palette.keys(), loc="lower right", fontsize=8)
plt.tight_layout(); plt.savefig(OUT / "stage3_top_users.png", dpi=140); plt.close()

open(OUT / "stage3_graph_report.txt", "w", encoding="utf-8").write("\n".join(report))
say("Saved outputs/stage3_graph_report.txt, stage3_degree_distribution.png, stage3_top_users.png")
say("ALL CHECKS PASSED" if all(checks.values()) else "SOME CHECKS FAILED - read the report above")
open_files(OUT / "stage3_degree_distribution.png", OUT / "stage3_top_users.png")
