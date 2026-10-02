"""
STAGE 10 -- INFORMATION FLOW: HOW DOES A POST SPREAD THROUGH THE NETWORK?
Model: INDEPENDENT CASCADE (a standard model in social-network research)
  * A few "seed" users share a post at round 0.
  * Every user who just received it gets ONE chance to pass it to each friend, and succeeds with probability p.
  * Repeat until nobody new is reached.  (Real use: viral marketing, fake-news control.)

Two questions answered with the model:
  A) MARKETING   which k users should a brand pay to post first?           (compare_strategies)
  B) FAKE NEWS   if a platform blocks k users, how much does a rumour spread?  (containment)

Run this file to test the model and see the results:  /usr/local/bin/python3 stage10_spread.py
   -> outputs/stage10_spread_report.txt and outputs/stage10_spread.png
The web site uses it through stage6_api.py (endpoints /api/spread, /api/spread/compare, /api/spread/containment).
"""
from pathlib import Path
import random
import sqlite3
import statistics as st

BASE = Path(__file__).resolve().parent
DB = BASE / "data" / "social.db"
if not DB.exists() and (BASE / "social.db").exists():
    DB = BASE / "social.db"

STRATEGIES = {
    "random": "random users",
    "top degree": "the users with most friends",
    "one per community": "the most connected user of each community",
    "top bridges": "users with most friends OUTSIDE their own community",
}


def load_graph(con):
    """adjacency {user: [friends]} plus each user's community, degree and bridge count, straight from the database."""
    adj, meta = {}, {}
    for uid, comm, deg, bridge, name in con.execute("SELECT user_id, community_id, degree, friends_outside_community, username FROM users"):
        adj[uid] = []; meta[uid] = dict(community=comm, degree=deg, bridge=bridge, username=name)
    for a, b in con.execute("SELECT user_id_1, user_id_2 FROM connections"):
        adj[a].append(b); adj[b].append(a)
    return adj, meta


def cascade(adj, seeds, p, rng, blocked=frozenset()):
    """One random run. Returns rounds: rounds[t] = users first reached in round t (round 0 = the seeds)."""
    active = {s for s in seeds if s not in blocked}
    rounds, frontier = [sorted(active)], sorted(active)
    while frontier:
        new = []
        for u in frontier:
            for v in adj[u]:
                if v not in active and v not in blocked and rng.random() < p:
                    active.add(v); new.append(v)
        if not new:
            break
        rounds.append(new); frontier = new
    return rounds


def pick_seeds(strategy, k, meta, rng, exclude=frozenset()):
    pool = [u for u in meta if u not in exclude and meta[u]["degree"] > 0]
    by = lambda key: sorted(pool, key=lambda u: (-meta[u][key], u))
    if strategy == "random":
        return rng.sample(pool, min(k, len(pool)))
    if strategy == "top degree":
        return by("degree")[:k]
    if strategy == "top bridges":
        return by("bridge")[:k]
    if strategy == "one per community":
        best = {}
        for u in by("degree"):
            c = meta[u]["community"]
            if c != "Isolated" and c not in best:
                best[c] = u
        seeds = list(best.values())[:k]
        return seeds + [u for u in by("degree") if u not in seeds][:max(0, k - len(seeds))]
    raise ValueError(f"unknown strategy '{strategy}'")


def reach(adj, seeds, p, trials, rng, blocked=frozenset()):
    """List of reach sizes (users reached, seeds included) over many random runs."""
    return [sum(len(r) for r in cascade(adj, seeds, p, rng, blocked)) for _ in range(trials)]


def mean_ci(xs):
    m = st.mean(xs)
    return m, (1.96 * st.stdev(xs) / len(xs) ** 0.5 if len(xs) > 1 else 0.0)


def compare_strategies(adj, meta, k=5, p=0.12, trials=200, seed=0):
    """Marketing question. Random seeds are re-drawn in every trial so 'random' is an honest average."""
    rng = random.Random(seed)
    out = {}
    for s in STRATEGIES:
        if s == "random":
            xs = [sum(len(r) for r in cascade(adj, pick_seeds("random", k, meta, rng), p, rng)) for _ in range(trials)]
        else:
            xs = reach(adj, pick_seeds(s, k, meta, rng), p, trials, rng)
        m, ci = mean_ci(xs)
        out[s] = dict(mean=round(m, 1), ci95=round(ci, 1), share=round(100 * m / len(adj), 1))
    return out


def containment(adj, meta, ks=(0, 5, 10, 20, 40), p=0.12, trials=200, seed=1):
    """Fake-news question: a rumour starts at a random user. How far does it get if we block k users?
    Fair comparison: the SAME start users, the SAME random numbers (trial i always uses random stream i),
    and the random blocked users are nested (the 10 include the 5), so only the blocked set changes between columns."""
    rng = random.Random(seed)
    nodes = [u for u in meta if meta[u]["degree"] > 0]
    starts = [rng.choice(nodes) for _ in range(trials)]
    shuffled = rng.sample(nodes, max(ks))
    res = {"random users": [], "top degree": [], "top bridges": []}
    for k in ks:
        blocked_sets = {"random users": set(shuffled[:k]),
                        "top degree": set(pick_seeds("top degree", k, meta, rng)),
                        "top bridges": set(pick_seeds("top bridges", k, meta, rng))}
        for name, blocked in blocked_sets.items():
            xs = [sum(len(r) for r in cascade(adj, [s], p, random.Random(seed * 100003 + i), blocked))
                  for i, s in enumerate(starts) if s not in blocked]
            res[name].append(round(st.mean(xs), 1))
    return list(ks), res


def simulate_once(adj, meta, seeds, p, seed=None):
    """What the web page animates: one run, with the round in which every user was reached."""
    rng = random.Random(seed)
    rounds = cascade(adj, seeds, p, rng)
    return {"rounds": rounds, "reached": sum(len(r) for r in rounds), "users": len(adj), "n_rounds": len(rounds) - 1,
            "by_community": _by_community(rounds, meta)}


def _by_community(rounds, meta):
    tot, hit = {}, {}
    for u, m in meta.items():
        tot[m["community"]] = tot.get(m["community"], 0) + 1
    for r in rounds:
        for u in r:
            hit[meta[u]["community"]] = hit.get(meta[u]["community"], 0) + 1
    return {c: {"reached": hit.get(c, 0), "users": tot[c]} for c in sorted(tot)}


# ============================================================ run as a script: tests + report + figure
if __name__ == "__main__":
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    adj, meta = load_graph(con)
    lines = []

    def log(s=""):
        print(s); lines.append(str(s))
    n = len(adj)
    log("STAGE 10 SPREAD SIMULATION REPORT\n" + "=" * 90)
    log(f"Network: {n} users, {sum(len(v) for v in adj.values()) // 2} friendships\n")

    P, K, TR = 0.12, 5, 300
    log(f"A) MARKETING: which {K} users should post first?  (spread probability p = {P}, {TR} random runs each)")
    cmp_ = compare_strategies(adj, meta, K, P, TR)
    for s, r in sorted(cmp_.items(), key=lambda kv: -kv[1]["mean"]):
        log(f"   {s:<18} reaches {r['mean']:6.1f} users  (+/- {r['ci95']:.1f})   = {r['share']:4.1f}% of the network   [{STRATEGIES[s]}]")
    gain = cmp_["top degree"]["mean"] / cmp_["random"]["mean"]
    log(f"   -> five hubs reach {gain:.1f}x as many users as five random users.\n")

    log("   Effect of the spread probability p (5 top-degree seeds):")
    curve = []
    rng = random.Random(3)
    hubs = pick_seeds("top degree", 5, meta, rng)
    for p in (0.02, 0.05, 0.08, 0.12, 0.16, 0.2, 0.3):
        m, _ = mean_ci(reach(adj, hubs, p, 150, rng)); curve.append((p, m))
        log(f"      p = {p:<5} -> {m:6.1f} users ({100 * m / n:4.1f}%)")
    log("   -> a small rise in p makes a huge difference: this is the 'tipping point' of viral content.\n")

    log("   One example run (5 top-degree seeds, p = 0.12): users reached per community")
    one = simulate_once(adj, meta, hubs, 0.12, seed=7)
    for c, v in one["by_community"].items():
        log(f"      {c:<9} {v['reached']:>4} of {v['users']:>3}")
    log(f"      finished in {one['n_rounds']} rounds, {one['reached']} users reached\n")

    KS = (0, 5, 10, 20, 40)
    log(f"B) FAKE NEWS: a rumour starts at a random user (p = {P}). Average users reached if we block k users first:")
    ks, cont = containment(adj, meta, KS, P, TR)
    log(f"   {'blocked k':<10}" + "".join(f"{name:>16}" for name in cont))
    for i, k in enumerate(ks):
        log(f"   {k:<10}" + "".join(f"{cont[name][i]:>16.1f}" for name in cont))
    best = min(("top degree", "top bridges"), key=lambda nme: cont[nme][-1])
    log(f"   -> blocking the {ks[-1]} {best} users cuts the rumour from {cont['top degree'][0]:.0f} to {cont[best][-1]:.0f} users; blocking {ks[-1]} random users only gets it to {cont['random users'][-1]:.0f}.")
    rr = random.Random(1); nodes_ = [u for u in meta if meta[u]["degree"] > 0]
    sizes = [sum(len(x) for x in cascade(adj, [rr.choice(nodes_)], P, rr)) for _ in range(2000)]
    small = sum(x < 15 for x in sizes) / len(sizes); bigs = [x for x in sizes if x >= 100]
    log(f"   Why hubs matter: with no blocking, {100 * small:.0f}% of rumours stay under 15 users, but the {100 * len(bigs) / len(sizes):.0f}% that reach 100+ users")
    log(f"   cause {100 * sum(bigs) / sum(sizes):.0f}% of all spreading. The table above shows that blocking hubs removes those big outbreaks.\n")

    # ---- validation
    log("--- VALIDATION")
    rng = random.Random(0)
    seedsV = pick_seeds("top degree", 3, meta, rng)
    comp = {}
    stack = [seedsV[0]]; comp[seedsV[0]] = 1
    while stack:
        u = stack.pop()
        for v in adj[u]:
            if v not in comp:
                comp[v] = 1; stack.append(v)
    full = cascade(adj, seedsV[:1], 1.0, rng)
    checks = {
        "p = 0: only the seeds are reached": sum(len(r) for r in cascade(adj, seedsV, 0.0, rng)) == len(seedsV),
        "p = 1: everybody in the seed's connected group is reached": sum(len(r) for r in full) == len(comp),
        "nobody is reached twice": (lambda r: len([u for x in r for u in x]) == len({u for x in r for u in x}))(cascade(adj, seedsV, 0.3, rng)),
        "same random seed gives the same run": cascade(adj, seedsV, 0.2, random.Random(5)) == cascade(adj, seedsV, 0.2, random.Random(5)),
        "reach grows with p": all(curve[i][1] < curve[i + 1][1] for i in range(len(curve) - 1)),
        "blocked users are never reached": not ({u for r in cascade(adj, seedsV, 0.5, rng, blocked=set(hubs)) for u in r} & set(hubs)),
        "hubs beat random seeds (the confidence intervals do not overlap)": cmp_["top degree"]["mean"] - cmp_["top degree"]["ci95"] > cmp_["random"]["mean"] + cmp_["random"]["ci95"],
        "blocking hubs reduces the spread more than blocking random users": cont["top degree"][-1] < cont["random users"][-1],
        "k = 0 gives the same baseline for all blocking methods": len({cont[nme][0] for nme in cont}) == 1,
    }
    for k_, v in checks.items():
        log(f"  {'PASS' if v else 'FAIL'}  {k_}")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 3, figsize=(16, 4.6))
    names = sorted(cmp_, key=lambda s: -cmp_[s]["mean"])
    ax[0].barh(names[::-1], [cmp_[s]["mean"] for s in names[::-1]], xerr=[cmp_[s]["ci95"] for s in names[::-1]], color="#4c78a8")
    ax[0].set_xlabel("users reached (average)"); ax[0].set_title(f"A) Who should post first? ({K} seeds, p={P})")
    ax[1].plot([c[0] for c in curve], [c[1] for c in curve], "o-", color="#e45756")
    ax[1].set_xlabel("probability p that a friend passes it on"); ax[1].set_ylabel("users reached"); ax[1].set_title("Tipping point of a post")
    for name, colr in zip(cont, ["#999999", "#4c78a8", "#e45756"]):
        ax[2].plot(ks, cont[name], "o-", label=name, color=colr)
    ax[2].set_xlabel("number of users blocked"); ax[2].set_ylabel("rumour reach (average)"); ax[2].legend(); ax[2].set_title("B) Blocking users to stop a rumour")
    plt.tight_layout(); (BASE / "outputs").mkdir(exist_ok=True); plt.savefig(BASE / "outputs" / "stage10_spread.png", dpi=140); plt.close()
    (BASE / "outputs" / "stage10_spread_report.txt").write_text("\n".join(lines), encoding="utf-8")
    log("\nSaved outputs/stage10_spread_report.txt and outputs/stage10_spread.png")
    log("ALL CHECKS PASSED" if all(checks.values()) else "SOME CHECKS FAILED - read the report above")
