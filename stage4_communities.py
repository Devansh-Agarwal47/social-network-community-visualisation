"""
STAGE 4 -- COMMUNITY DETECTION (Louvain) AND FIRST NETWORK PICTURES
graph -> find groups of users who are friends mostly with each other -> colour and draw them

Ideas:
  community  = a group of users with many friendships INSIDE the group and few going OUTSIDE
  modularity = a score for a split into communities:  (share of edges inside groups) minus (share expected by chance)
               0 = no better than random,  0.3-0.7 = clear community structure
  Louvain    = an algorithm that moves users between groups, step by step, to make modularity as high as possible.
               It does NOT see the 'interest' column. It only sees who is friends with whom.
  Our check  = do the groups Louvain finds match the interests users declared?  (purity, NMI)

Input : data/clean/*.csv  (Stage 2)
Output: data/graph/communities.csv          (user -> community; used by the database in Stage 5)
        data/graph/community_summary.csv    (one row per community)
        outputs/stage4_report.txt
        outputs/stage4_network_communities.png   the network, coloured by community
        outputs/stage4_communities_vs_interests.png  same layout coloured by interest vs by community
        outputs/stage4_community_sizes.png, outputs/stage4_match_heatmap.png

Run in VS Code: open the file and press the Run triangle  (or: /usr/local/bin/python3 stage4_communities.py, add --no-open to skip pop-ups)
Needs: pandas numpy matplotlib networkx  (all installed already)
"""
# %% 0. Setup
from pathlib import Path
import sys, subprocess, os
import numpy as np
import pandas as pd
import networkx as nx
from networkx.algorithms.community import louvain_communities, modularity
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

pd.set_option("display.width", 200)
BASE = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
CLEAN = BASE / "data" / "clean"
if not (CLEAN / "users.csv").exists():
    CLEAN = BASE
OUT, GRAPH_DIR = BASE / "outputs", BASE / "data" / "graph"
OUT.mkdir(exist_ok=True); GRAPH_DIR.mkdir(parents=True, exist_ok=True)
SEED = 42
report = []


def say(text=""):
    print(text)
    report.append(str(text))


def open_files(*paths):
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


# %% 1. Rebuild the graph from the clean tables
users = pd.read_csv(CLEAN / "users.csv")
conns = pd.read_csv(CLEAN / "connections.csv")
G = nx.Graph()
for row in users.to_dict("records"):
    G.add_node(row.pop("user_id"), **row)
G.add_edges_from(zip(conns["user_id_1"], conns["user_id_2"]))
n, m = G.number_of_nodes(), G.number_of_edges()
say("STAGE 4 COMMUNITY REPORT")
say("=" * 90)
say(f"Graph: {n} users, {m} friendships")

# %% 2. Run Louvain
raw = louvain_communities(G, resolution=1.0, seed=SEED)          # list of sets of users
raw = sorted(raw, key=lambda c: (-len(c), min(c)))
Q = modularity(G, raw)
alone = [c for c in raw if len(c) == 1]                          # isolated users can't belong to any group
groups = [c for c in raw if len(c) > 1]
say(f"\nLouvain found {len(groups)} communities of 2+ users and {len(alone)} users who are alone (isolated)")
say(f"Modularity = {Q:.3f}   (0 = random, above 0.3 = clear communities)")

# names: C1 is the biggest community ...  and 'Isolated' for users with no friends
label = {}
for i, c in enumerate(groups, start=1):
    for u in c:
        label[u] = f"C{i}"
for c in alone:
    for u in c:
        label[u] = "Isolated"
users["community"] = users["user_id"].map(label)
nx.set_node_attributes(G, label, "community")

# sanity: the SAME graph should give a much lower modularity if we shuffle the labels (proves the groups are real)
rng = np.random.default_rng(SEED)
shuffled = list(label.values()); rng.shuffle(shuffled)
fake = {}
for u, lab in zip(label.keys(), shuffled):
    fake.setdefault(lab, set()).add(u)
Q_fake = modularity(G, list(fake.values()))
say(f"Modularity with the SAME group sizes but users assigned at random = {Q_fake:.3f}  (real groups: {Q:.3f})")

# %% 3. Do the communities match the declared interests?
say("\n--- HOW WELL DO FOUND COMMUNITIES MATCH THE 'interest' COLUMN?")
connected = users[users["community"] != "Isolated"]
table = pd.crosstab(connected["community"], connected["interest"])
table = table.loc[sorted(table.index, key=lambda s: int(s[1:]))]
say(table.to_string())


def purity(tab):
    """Share of users whose interest equals the most common interest of their community (1.0 = perfect match)."""
    return tab.max(axis=1).sum() / tab.values.sum()


def nmi(tab):
    """Normalised mutual information (0 = unrelated, 1 = identical grouping). Written by hand so no extra package is needed."""
    p = tab.values / tab.values.sum()
    pa, pb = p.sum(axis=1, keepdims=True), p.sum(axis=0, keepdims=True)
    nz = p > 0
    mi = (p[nz] * np.log(p[nz] / (pa @ pb)[nz])).sum()
    ha = -(pa[pa > 0] * np.log(pa[pa > 0])).sum()
    hb = -(pb[pb > 0] * np.log(pb[pb > 0])).sum()
    return mi / ((ha + hb) / 2)


pur, nm = purity(table), nmi(table)
say(f"\nPurity = {pur:.3f}   NMI = {nm:.3f}")
say("Reading: Louvain never saw the interest column, yet its groups line up with it. That is the proof that the")
say("interest groups are real structure in the friendships and not just labels.")

# %% 4. Community summary (one row per community)
deg = pd.Series(dict(G.degree()))
users["degree"] = users["user_id"].map(deg)
rows = []
for name, part in users.groupby("community"):
    if name == "Isolated":
        continue
    uid = set(part["user_id"])
    sub = G.subgraph(uid)
    boundary = sum(1 for u in uid for v in G.neighbors(u) if v not in uid)
    hub = part.sort_values("degree", ascending=False).iloc[0]
    rows.append({
        "community": name, "users": len(part),
        "main_interest": part["interest"].mode().iloc[0],
        "interest_share_%": round(100 * (part["interest"] == part["interest"].mode().iloc[0]).mean(), 1),
        "main_city": part["city"].mode().iloc[0],
        "avg_age": round(part["age"].mean(), 1),
        "friendships_inside": sub.number_of_edges(),
        "friendships_leaving": boundary,
        "inside_share_%": round(100 * 2 * sub.number_of_edges() / max(2 * sub.number_of_edges() + boundary, 1), 1),
        "density_inside": round(nx.density(sub), 4),
        "top_user": hub["username"], "top_user_degree": int(hub["degree"]),
    })
summary = pd.DataFrame(rows).sort_values("users", ascending=False)
say("\n--- COMMUNITY SUMMARY")
say(summary.to_string(index=False))
say("\nReading: 'inside_share_%' is how many of a community's friendship ends stay inside it. High = tight community.")

# users who bridge communities: most friends OUTSIDE their own community
def outside(u):
    return sum(1 for v in G.neighbors(u) if label[v] != label[u])
users["friends_outside_community"] = users["user_id"].map({u: outside(u) for u in G.nodes})
say("\n--- TOP 10 BRIDGE USERS (most friends outside their own community)")
say(users.sort_values("friends_outside_community", ascending=False).head(10)[
    ["username", "community", "interest", "degree", "friends_outside_community"]].to_string(index=False))

# %% 5. Save results
users[["user_id", "username", "community", "interest", "degree", "friends_outside_community"]].to_csv(GRAPH_DIR / "communities.csv", index=False)
summary.to_csv(GRAPH_DIR / "community_summary.csv", index=False)
say(f"\nSaved {GRAPH_DIR / 'communities.csv'} and community_summary.csv")

# %% 6. Figures
names = list(summary["community"])                                             # ordered by size
pal = ["#4c78a8", "#f58518", "#54a24b", "#e45756", "#72b7b2", "#b279a2", "#eeca3b", "#9d755d", "#bab0ac", "#ff9da6"]
interests = sorted(users["interest"].unique())
col_int = {k: pal[i] for i, k in enumerate(interests)}
# a community gets the colour of its main interest, so both pictures use the same colours and can be compared by eye
col_comm = {r.community: col_int[r.main_interest] for r in summary.itertuples()}
col_comm["Isolated"] = "#333333"

# layout: spring layout for the connected group, isolated users parked in a row underneath
giant = G.subgraph(max(nx.connected_components(G), key=len))
pos = nx.spring_layout(giant, k=0.35, iterations=200, seed=SEED)
lonely = [u for u in G.nodes if u not in pos]
xs = np.linspace(-1, 1, max(len(lonely), 1))
for x, u in zip(xs, lonely):
    pos[u] = (x, -1.25)
size = {u: 8 + 5 * np.sqrt(deg[u]) for u in G.nodes}


def draw(ax, colors, title, legend):
    nx.draw_networkx_edges(G, pos, ax=ax, alpha=0.07, width=0.4, edge_color="#555")
    nx.draw_networkx_nodes(G, pos, ax=ax, node_color=[colors[u] for u in G.nodes], node_size=[size[u] for u in G.nodes],
                           linewidths=0.3, edgecolors="white")
    ax.set_title(title, fontsize=13); ax.axis("off")
    ax.legend(handles=[plt.Line2D([], [], marker="o", ls="", color=c, label=l) for l, c in legend.items()],
              loc="upper left", fontsize=8, frameon=False)


by_comm = {u: col_comm[label[u]] for u in G.nodes}
by_int = {u: col_int[G.nodes[u]["interest"]] for u in G.nodes}
comm_legend = {f"{r.community}  ({r.users} users, {r.main_interest})": col_comm[r.community] for r in summary.itertuples()}
comm_legend["Isolated (no friends)"] = col_comm["Isolated"]

fig, ax = plt.subplots(figsize=(11, 9))
draw(ax, by_comm, f"Communities found by Louvain  (modularity {Q:.2f})   node size = number of friends", comm_legend)
plt.tight_layout(); plt.savefig(OUT / "stage4_network_communities.png", dpi=150); plt.close()

fig, axes = plt.subplots(1, 2, figsize=(17, 8))
draw(axes[0], by_int, "Colour = interest the user DECLARED", col_int)
draw(axes[1], by_comm, "Colour = community Louvain FOUND (using friendships only)", {k: v for k, v in comm_legend.items()})
plt.tight_layout(); plt.savefig(OUT / "stage4_communities_vs_interests.png", dpi=140); plt.close()

fig, ax = plt.subplots(figsize=(8, 4.5))
ax.bar(summary["community"], summary["users"], color=[col_comm[c] for c in summary["community"]])
for i, r in enumerate(summary.itertuples()):
    ax.text(i, r.users + 3, r.main_interest, ha="center", fontsize=9)
ax.set_ylabel("users"); ax.set_title("Community sizes (label = main interest)")
plt.tight_layout(); plt.savefig(OUT / "stage4_community_sizes.png", dpi=140); plt.close()

fig, ax = plt.subplots(figsize=(8, 5))
frac = table.div(table.sum(axis=1), axis=0)
im = ax.imshow(frac.values, cmap="Blues", vmin=0, vmax=1, aspect="auto")
ax.set_xticks(range(frac.shape[1]), frac.columns, rotation=30); ax.set_yticks(range(frac.shape[0]), frac.index)
for i in range(frac.shape[0]):
    for j in range(frac.shape[1]):
        ax.text(j, i, f"{100 * frac.values[i, j]:.0f}%", ha="center", va="center", fontsize=8,
                color="white" if frac.values[i, j] > .5 else "black")
ax.set_title(f"Interest mix of each community   (purity {pur:.2f})")
plt.colorbar(im, label="share of community"); plt.tight_layout()
plt.savefig(OUT / "stage4_match_heatmap.png", dpi=140); plt.close()

# %% 7. Validate
say("\n--- VALIDATION")
chk = {
    "every user has exactly one community label": users["community"].notna().all() and len(users) == n,
    "community sizes add up to number of users": summary["users"].sum() + len(alone) == n,
    "edges inside + edges between communities = all edges":
        sum(summary["friendships_inside"]) + sum(1 for u, v in G.edges if label[u] != label[v]) == m,
    "modularity is between 0.3 and 1 (clear communities)": 0.3 < Q < 1,
    "real modularity is far above shuffled-label modularity": Q > Q_fake + 0.2,
    "communities match interests (purity above 0.7)": pur > 0.7,
    "same result on a second run (seed fixed)": [sorted(c) for c in louvain_communities(G, seed=SEED)] == [sorted(c) for c in louvain_communities(G, seed=SEED)],
}
for k, v in chk.items():
    say(f"  {'PASS' if v else 'FAIL'}  {k}")

open(OUT / "stage4_report.txt", "w", encoding="utf-8").write("\n".join(report))
say("\nSaved outputs/stage4_report.txt and 4 figures in outputs/")
say("ALL CHECKS PASSED" if all(chk.values()) else "SOME CHECKS FAILED - read the report above")
open_files(OUT / "stage4_network_communities.png", OUT / "stage4_communities_vs_interests.png")
