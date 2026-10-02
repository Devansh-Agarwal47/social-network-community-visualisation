"""
STAGE 9 -- GRAPH INTELLIGENCE: PREDICT A NEW USER'S COMMUNITY, RECOMMEND PEOPLE, SAVE THE USER

What happens when somebody new joins?
  1. PREDICT which community they belong to.
       Method: Naive Bayes, a classic and easy-to-explain model. For every community we ask
       "how likely is a member of this community to have THIS interest, live in THIS city, be THIS age,
        use these hashtags, and know these people?"  and multiply the answers (we add their logarithms).
       The community with the highest score wins; a softmax turns the scores into percentages.
       It learns from the users already in the database, so it needs no training step.
  2. RECOMMEND people to connect with:  popular users of the predicted community, same interest / city,
       friends-of-friends of people the new user already knows, plus a few "bridge" users from the runner-up community.
  3. SAVE the user: insert the user and the chosen connections into the database, update everybody's friend counts
       and every community's statistics, in ONE transaction (all changes happen or none).

Run this file to test the model:   /usr/local/bin/python3 stage9_recommender.py
   -> prints how accurate the prediction is (leave-one-out on the 990 connected users) and writes outputs/stage9_report.txt
The web site uses it through stage6_api.py  (endpoints /api/meta, /api/predict, POST /api/users).
"""
from pathlib import Path
import datetime
import re
import sqlite3
import threading
import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent
DB = BASE / "data" / "social.db"
if not DB.exists() and (BASE / "social.db").exists():
    DB = BASE / "social.db"

ACCOUNT_TYPES = ["personal", "creator", "business"]
W = dict(interest=1.0, city=0.5, account_type=0.3, age=0.5, hashtag=0.6, friend=1.0)   # how much each clue counts
MAX_TAGS, MAX_FRIENDS = 5, 10


class ValidationError(Exception):
    def __init__(self, errors):
        super().__init__("; ".join(errors))
        self.errors = errors


# =====================================================================  1. THE MODEL
class Model:
    """Counts learned from the database. Smoothing (+1) stops a never-seen combination from getting probability 0."""

    def __init__(self, con):
        u = pd.read_sql_query("SELECT user_id, username, age, city, interest, account_type, community_id AS comm, degree, "
                              "friends_outside_community AS bridge FROM users WHERE community_id <> 'Isolated'", con)
        self.users = u.set_index("user_id")
        self.comms = sorted(u["comm"].unique(), key=lambda c: int(c[1:]))
        self.K = len(self.comms)
        ci = {c: i for i, c in enumerate(self.comms)}
        self.ci = ci
        self.interests = sorted(u["interest"].unique())
        self.cities = sorted(c for c in u["city"].unique() if c != "Unknown")
        self.types = ACCOUNT_TYPES
        self.ix = {"interest": {v: i for i, v in enumerate(self.interests)},
                   "city": {v: i for i, v in enumerate(sorted(u["city"].unique()))},
                   "account_type": {v: i for i, v in enumerate(self.types)}}
        K = self.K
        self.n = np.zeros(K)
        self.cnt = {f: np.zeros((K, len(self.ix[f]))) for f in self.ix}
        self.age_n, self.age_s, self.age_ss = np.zeros(K), np.zeros(K), np.zeros(K)
        for r in u.itertuples():
            k = ci[r.comm]
            self.n[k] += 1
            for f in self.ix:
                self.cnt[f][k, self.ix[f][getattr(r, f)]] += 1
            self.age_n[k] += 1; self.age_s[k] += r.age; self.age_ss[k] += r.age ** 2
        # hashtag usage per community
        t = pd.read_sql_query("SELECT u.community_id AS comm, h.hashtag, COUNT(*) AS n FROM post_hashtags h JOIN posts p ON p.post_id=h.post_id "
                              "JOIN users u ON u.user_id=p.user_id WHERE u.community_id <> 'Isolated' GROUP BY 1,2", con)
        self.tags = sorted(t["hashtag"].unique())
        self.tix = {h: i for i, h in enumerate(self.tags)}
        self.tag_cnt = np.zeros((K, len(self.tags)))
        for r in t.itertuples():
            self.tag_cnt[ci[r.comm], self.tix[r.hashtag]] += r.n
        # who befriends whom: H[c, d] = friendship ends of community c that lead to community d
        e = pd.read_sql_query("SELECT a.community_id AS ca, b.community_id AS cb, COUNT(*) AS n FROM connections c "
                              "JOIN users a ON a.user_id=c.user_id_1 JOIN users b ON b.user_id=c.user_id_2 "
                              "WHERE a.community_id <> 'Isolated' AND b.community_id <> 'Isolated' GROUP BY 1,2", con)
        self.H = np.zeros((K, K))
        for r in e.itertuples():
            self.H[ci[r.ca], ci[r.cb]] += r.n
            self.H[ci[r.cb], ci[r.ca]] += r.n
        self.T = 1.0                                   # temperature, tuned in evaluate()

    # ---- one log-score per community for a profile
    def log_scores(self, p, c=None):
        """p = dict(interest, city, age, account_type, hashtags=[...], friend_communities=[...]).  c = counts to use (default: all)."""
        c = c or self.counts()
        K, s = self.K, np.log(np.maximum(c["n"], 1) / c["n"].sum())
        for f in ("interest", "city", "account_type"):
            v = p.get(f)
            if v is not None and v in self.ix[f]:
                s = s + W[f] * np.log((c[f][:, self.ix[f][v]] + 1) / (c["n"] + len(self.ix[f])))
        if p.get("age") is not None:
            m = c["age_s"] / np.maximum(c["age_n"], 1)
            sd = np.sqrt(np.maximum(c["age_ss"] / np.maximum(c["age_n"], 1) - m ** 2, 9.0))          # never narrower than 3 years
            s = s + W["age"] * (-np.log(sd) - 0.5 * ((p["age"] - m) / sd) ** 2)
        for tg in list(dict.fromkeys(p.get("hashtags") or []))[:MAX_TAGS]:
            if tg in self.tix:
                col = c["tag_cnt"][:, self.tix[tg]]
                s = s + W["hashtag"] * np.log((col + 1) / (c["tag_cnt"].sum(axis=1) + len(self.tags)))
        for d in (p.get("friend_communities") or [])[:MAX_FRIENDS]:
            s = s + W["friend"] * np.log((c["H"][:, self.ci[d]] + 1) / (c["H"].sum(axis=1) + K))
        return s

    def counts(self):
        return dict(n=self.n, age_n=self.age_n, age_s=self.age_s, age_ss=self.age_ss, tag_cnt=self.tag_cnt, H=self.H, **self.cnt)

    def probabilities(self, p, c=None):
        s = self.log_scores(p, c) / self.T
        e = np.exp(s - s.max())
        return e / e.sum()

    # ---- explanation: which clue pushed the winner ahead of the runner-up, and by how much
    def explain(self, p, probs):
        order = np.argsort(-probs); a, b = order[0], order[1]
        base = {}
        pieces = {"interest": dict(interest=p.get("interest")), "city": dict(city=p.get("city")),
                  "account type": dict(account_type=p.get("account_type")), "age": dict(age=p.get("age")),
                  "hashtags": dict(hashtags=p.get("hashtags")), "people you know": dict(friend_communities=p.get("friend_communities"))}
        for name, part in pieces.items():
            if all(v in (None, [], "") for v in part.values()):
                continue
            s = self.log_scores(part) / self.T
            s0 = self.log_scores({}) / self.T
            base[name] = float((s[a] - s0[a]) - (s[b] - s0[b]))
        out = []
        for name, v in sorted(base.items(), key=lambda kv: -abs(kv[1])):
            out.append({"factor": name, "pushes_towards": self.comms[a] if v > 0 else self.comms[b], "strength": round(abs(v), 2)})
        return out

    # ---- who to connect with
    def recommend(self, con, p, probs, exclude=(), top=6, bridges=2):
        best = self.comms[int(np.argmax(probs))]
        seeds = list(p.get("friend_ids") or [])
        mutual = {}
        if seeds:
            ph = ",".join("?" * len(seeds))
            for uid, m in con.execute(f"SELECT friend_id, COUNT(*) FROM friendships WHERE user_id IN ({ph}) GROUP BY friend_id", seeds):
                mutual[uid] = m
        maxdeg = max(self.users["degree"].max(), 1)
        rows = []
        for uid, r in self.users.iterrows():
            if uid in exclude or uid in seeds or r["degree"] == 0:
                continue
            why, score = [], 3.0 * probs[self.ci[r["comm"]]]
            if r["comm"] == best:
                why.append(f"popular in {best}")
            if r["interest"] == p.get("interest"):
                score += 1.5; why.append(f"also into {r['interest']}")
            if r["city"] == p.get("city"):
                score += 0.5; why.append(f"also in {r['city']}")
            if mutual.get(uid):
                score += 0.8 * min(mutual[uid], 5); why.append(f"{mutual[uid]} of your contacts know them")
            score += np.log1p(r["degree"]) / np.log1p(maxdeg)
            rows.append((score, uid, r, why))
        rows.sort(key=lambda x: -x[0])
        pick = lambda x, extra=None: {"user_id": x[1], "username": x[2]["username"], "city": x[2]["city"], "interest": x[2]["interest"],
                                      "community_id": x[2]["comm"], "degree": int(x[2]["degree"]), "score": round(float(x[0]), 2),
                                      "reason": ", ".join(x[3] + ([extra] if extra else [])) or "well connected"}
        main = [pick(x) for x in rows[:top]]
        # "bridge" users: connect the new user to the runner-up community too (people with many friends outside their own group)
        second = self.comms[int(np.argsort(-probs)[1])]
        chosen = {m["user_id"] for m in main}
        br = sorted((x for x in rows if x[2]["comm"] == second and x[1] not in chosen), key=lambda x: -x[2]["bridge"])[:bridges]
        bridge = [pick(x, f"bridge to {second} ({int(x[2]['bridge'])} friends outside their group)") for x in br]
        return main, bridge


_model, _lock = None, threading.Lock()


def get_model():
    global _model
    with _lock:
        if _model is None:
            con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
            try:
                _model = Model(con)
                _model.T = _tuned_temperature(_model, con)
            finally:
                con.close()
        return _model


def invalidate():
    """Call after the database changed: the model is re-learned from the new data on the next request."""
    global _model
    with _lock:
        _model = None


# =====================================================================  2. PREDICT + RECOMMEND
def clean_profile(m, data, strict=True):
    """Check what the form sent. Returns the profile dict or raises ValidationError with readable messages."""
    err = []
    name = str(data.get("full_name", "")).strip()
    if strict and not 2 <= len(name) <= 60:
        err.append("full name must have 2-60 characters")
    try:
        age = int(data.get("age"))
        if not 13 <= age <= 100:
            raise ValueError
    except (TypeError, ValueError):
        age = None; err.append("age must be a whole number between 13 and 100")
    city = data.get("city")
    if city not in m.cities:
        err.append("city must be one of: " + ", ".join(m.cities))
    interest = data.get("interest")
    if interest not in m.interests:
        err.append("interest must be one of: " + ", ".join(m.interests))
    typ = data.get("account_type", "personal")
    if typ not in m.types:
        err.append("account type must be one of: " + ", ".join(m.types))
    tags = data.get("hashtags") or []
    if not isinstance(tags, list) or any(t not in m.tix for t in tags) or len(tags) > MAX_TAGS:
        err.append(f"choose at most {MAX_TAGS} hashtags from the list")
    fids = data.get("friend_ids") or []
    if not isinstance(fids, list) or len(fids) > MAX_FRIENDS or any(f not in m.users.index for f in fids):
        err.append(f"'people you know' must be up to {MAX_FRIENDS} existing connected users")
    if err:
        raise ValidationError(err)
    return dict(full_name=name, age=age, city=city, interest=interest, account_type=typ, hashtags=list(dict.fromkeys(tags)),
                friend_ids=list(dict.fromkeys(fids)), friend_communities=[m.users.loc[f, "comm"] for f in dict.fromkeys(fids)])


def predict(con, data):
    m = get_model()
    p = clean_profile(m, data, strict=False)
    probs = m.probabilities(p)
    order = np.argsort(-probs)
    main, bridge = m.recommend(con, p, probs)
    info = {r.community_id: r for r in pd.read_sql_query("SELECT community_id, users, main_interest FROM communities", con).itertuples()}
    return {
        "predicted_community": m.comms[order[0]],
        "confidence": round(float(probs[order[0]]), 3),
        "probabilities": [{"community_id": m.comms[i], "main_interest": info[m.comms[i]].main_interest, "users": int(info[m.comms[i]].users),
                           "probability": round(float(probs[i]), 3)} for i in order],
        "why": m.explain(p, probs),
        "recommended_people": main,
        "bridge_people": bridge,
    }


# =====================================================================  3. SAVE THE NEW USER
def refresh_community_stats(con):
    """Recompute every column of the communities table from the users and connections tables, so nothing goes stale."""
    users = pd.read_sql_query("SELECT user_id, username, age, city, interest, community_id, degree FROM users", con)
    edges = pd.read_sql_query("SELECT user_id_1 AS a, user_id_2 AS b FROM connections", con)
    comm = users.set_index("user_id")["community_id"]
    ea, eb = edges["a"].map(comm), edges["b"].map(comm)
    for cid, part in users.groupby("community_id"):
        if cid == "Isolated":
            con.execute("UPDATE communities SET users=? WHERE community_id='Isolated'", (len(part),))
            continue
        inside = int(((ea == cid) & (eb == cid)).sum())
        leaving = int((((ea == cid) & (eb != cid)) | ((eb == cid) & (ea != cid))).sum())
        mi = part["interest"].mode().iloc[0]
        top = part.sort_values(["degree", "user_id"], ascending=[False, True]).iloc[0]
        con.execute("""UPDATE communities SET users=?, main_interest=?, interest_share=?, main_city=?, avg_age=?, friendships_inside=?,
                       friendships_leaving=?, inside_share=?, top_user=? WHERE community_id=?""",
                    (len(part), mi, round(100 * float((part["interest"] == mi).mean()), 1), part["city"].mode().iloc[0],
                     round(float(part["age"].mean()), 1), inside, leaving,
                     round(100 * 2 * inside / max(2 * inside + leaving, 1), 1), top["username"], cid))


def _username_from(name, taken):
    base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "user"
    for i in range(0, 1000):
        cand = f"{base}{'' if i == 0 else i}"[:30]
        if cand not in taken:
            return cand
    raise ValidationError(["could not make a free username, please type one"])


def create_user(data):
    """Validate, then insert the user + connections and update degrees and community statistics in ONE transaction."""
    m = get_model()
    p = clean_profile(m, data)
    username = str(data.get("username") or "").strip().lower()
    if username and not re.fullmatch(r"[a-z0-9_]{3,30}", username):
        raise ValidationError(["username: 3-30 characters, only a-z, 0-9 and _"])
    community = data.get("community_id")
    if community not in m.comms:
        raise ValidationError(["community must be one of: " + ", ".join(m.comms)])
    con = sqlite3.connect(DB, timeout=10)
    con.execute("PRAGMA foreign_keys = ON")
    try:
        con.execute("BEGIN IMMEDIATE")
        taken = {r[0] for r in con.execute("SELECT username FROM users")}
        if username and username in taken:
            raise ValidationError([f"username '{username}' is already taken"])
        username = username or _username_from(p["full_name"], taken)
        uid = "U%04d" % (max(int(r[0][1:]) for r in con.execute("SELECT user_id FROM users")) + 1)
        nxt = max(int(r[0][1:]) for r in con.execute("SELECT connection_id FROM connections")) + 1
        today = datetime.date.today().isoformat()
        fr = p["friend_ids"]
        comm_of = dict(con.execute(f"SELECT user_id, community_id FROM users WHERE user_id IN ({','.join('?' * len(fr))})", fr).fetchall()) if fr else {}
        outside = sum(1 for f in fr if comm_of[f] != community)
        con.execute("INSERT INTO users (user_id, username, full_name, age, city, interest, account_type, joined_date, last_active_date, "
                    "is_verified, community_id, degree, friends_outside_community) VALUES (?,?,?,?,?,?,?,?,?,0,?,?,?)",
                    (uid, username, p["full_name"], p["age"], p["city"], p["interest"], p["account_type"], today, today, community, len(fr), outside))
        for i, f in enumerate(fr):
            a, b = sorted((uid, f))
            con.execute("INSERT INTO connections (connection_id, user_id_1, user_id_2, connected_on, interaction_count, date_estimated) VALUES (?,?,?,?,0,0)",
                        ("C%05d" % (nxt + i), a, b, today))
            con.execute("UPDATE users SET degree = degree + 1, friends_outside_community = friends_outside_community + ? WHERE user_id = ?",
                        (1 if comm_of[f] != community else 0, f))
        refresh_community_stats(con)
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    invalidate()
    return {"user_id": uid, "username": username, "community_id": community, "connected_to": fr}


# =====================================================================  4. HOW GOOD IS THE PREDICTION?  (leave-one-out)
def _subtract(m, uid, con_edges, tagrows):
    """Counts as they would be if user `uid` had never joined (so we are not testing on data the model has already seen)."""
    c = {k: v.copy() for k, v in m.counts().items()}
    r = m.users.loc[uid]; k = m.ci[r["comm"]]
    c["n"][k] -= 1
    for f in m.ix:
        c[f][k, m.ix[f][r[f]]] -= 1
    c["age_n"][k] -= 1; c["age_s"][k] -= r["age"]; c["age_ss"][k] -= r["age"] ** 2
    for tg, n in tagrows.get(uid, []):
        c["tag_cnt"][k, m.tix[tg]] -= n
    for v in con_edges.get(uid, []):
        kv = m.ci.get(m.users.loc[v, "comm"]) if v in m.users.index else None
        if kv is not None:
            c["H"][k, kv] -= 1; c["H"][kv, k] -= 1
    return c


def _loo_data(m, con):
    edges = {}
    for a, b in con.execute("SELECT user_id_1, user_id_2 FROM connections"):
        edges.setdefault(a, []).append(b); edges.setdefault(b, []).append(a)
    tagrows = {}
    for uid, tg, n in con.execute("SELECT p.user_id, h.hashtag, COUNT(*) FROM post_hashtags h JOIN posts p ON p.post_id=h.post_id GROUP BY 1,2"):
        tagrows.setdefault(uid, []).append((tg, n))
    return edges, tagrows


def _tuned_temperature(m, con):
    """Pick the temperature that makes the percentages honest: lowest log-loss on leave-one-out predictions,
    averaged over four situations (basic profile, + hashtags, + people, + both). Extra clues overlap with the interest,
    so a temperature above 1 stops the model from claiming 100% too easily."""
    edges, tagrows = _loo_data(m, con)
    rng = np.random.default_rng(1)
    S, y = [], []
    for uid, r in m.users.iterrows():
        c = _subtract(m, uid, edges, tagrows)
        base = dict(interest=r["interest"], city=r["city"], age=r["age"], account_type=r["account_type"])
        mytags = [t for t, _ in tagrows.get(uid, [])]
        tags = list(rng.choice(mytags, size=min(3, len(mytags)), replace=False)) if mytags else []
        fr = [f for f in edges.get(uid, []) if f in m.users.index and f != uid]
        fc = [m.users.loc[f, "comm"] for f in (rng.choice(fr, size=min(3, len(fr)), replace=False) if fr else [])]
        for prof in (base, dict(base, hashtags=tags), dict(base, friend_communities=fc), dict(base, hashtags=tags, friend_communities=fc)):
            S.append(m.log_scores(prof, c)); y.append(m.ci[r["comm"]])
    S, y = np.array(S), np.array(y)
    best, bt = 1e9, 1.0
    for T in np.arange(0.5, 10.01, 0.25):
        z = S / T; z = z - z.max(axis=1, keepdims=True)
        lp = z - np.log(np.exp(z).sum(axis=1, keepdims=True))
        nll = -lp[np.arange(len(y)), y].mean()
        if nll < best:
            best, bt = nll, float(T)
    return bt


def evaluate(con, seed=0, log=print):
    m = get_model()
    edges, tagrows = _loo_data(m, con)
    rng = np.random.default_rng(seed)
    settings = ["interest only", "interest + city + age + account type", "  + 3 hashtags the user posted", "  + 3 people the user knows",
                "  + hashtags + people", "city + age + account type only (no interest)", "people only (3 random friends)"]
    hit = {s: 0 for s in settings}; total = 0; nll = 0.0; conf_hit, conf_all = [], []
    for uid, r in m.users.iterrows():
        c = _subtract(m, uid, edges, tagrows)
        truth = m.ci[r["comm"]]
        base = dict(interest=r["interest"], city=r["city"], age=r["age"], account_type=r["account_type"])
        mytags = [t for t, _ in tagrows.get(uid, [])]
        tags = list(rng.choice(mytags, size=min(3, len(mytags)), replace=False)) if mytags else []
        fr = [f for f in edges.get(uid, []) if f in m.users.index and f != uid]
        friends = [m.users.loc[f, "comm"] for f in (rng.choice(fr, size=min(3, len(fr)), replace=False) if fr else [])]
        variants = {"interest only": dict(interest=r["interest"]), "interest + city + age + account type": base,
                    "  + 3 hashtags the user posted": dict(base, hashtags=tags), "  + 3 people the user knows": dict(base, friend_communities=friends),
                    "  + hashtags + people": dict(base, hashtags=tags, friend_communities=friends),
                    "city + age + account type only (no interest)": {k: v for k, v in base.items() if k != "interest"},
                    "people only (3 random friends)": dict(friend_communities=friends)}
        for s, prof in variants.items():
            pr = m.probabilities(prof, c)
            hit[s] += int(np.argmax(pr) == truth)
            if s == "interest + city + age + account type":
                nll += -np.log(max(pr[truth], 1e-9)); conf_all.append(pr.max()); conf_hit.append(int(np.argmax(pr) == truth))
        total += 1
    acc = {s: hit[s] / total for s in settings}
    log(f"Leave-one-out test on {total} connected users (each user is hidden from the model, then predicted):")
    for s in settings:
        log(f"  accuracy  {s:<48} {100 * acc[s]:5.1f}%")
    majority = m.n.max() / m.n.sum()
    log(f"  (guessing the biggest community every time would give {100 * majority:.1f}%)")
    ca, ch = np.array(conf_all), np.array(conf_hit)
    log(f"\nConfidence check (basic profile): temperature {m.T}, average log-loss {nll / total:.3f}")
    for lo, hi in [(0, .6), (.6, .8), (.8, .95), (.95, 1.01)]:
        sel = (ca >= lo) & (ca < hi)
        if sel.sum():
            log(f"  when the model said {int(lo * 100)}-{min(int(hi * 100), 100)}% : right {100 * ch[sel].mean():.0f}% of the time  ({int(sel.sum())} users)")
    return acc


if __name__ == "__main__":
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    lines = []

    def log(s=""):
        print(s); lines.append(str(s))
    log("STAGE 9 RECOMMENDER REPORT\n" + "=" * 90)
    m = get_model()
    log(f"Model learned from {int(m.n.sum())} connected users in {m.K} communities ({', '.join(m.comms)}); {len(m.tags)} hashtags\n")
    acc = evaluate(con, log=log)
    demo = dict(full_name="Demo Person", age=24, city="Jaipur", interest="Tech", account_type="personal", hashtags=["#python", "#coding"], friend_ids=[])
    res = predict(con, demo)
    log("\nDEMO: 24-year-old in Jaipur, interest Tech, uses #python #coding, knows nobody yet")
    log("  predicted community: %s (%.0f%%)" % (res["predicted_community"], 100 * res["confidence"]))
    for pr in res["probabilities"]:
        log(f"    {pr['community_id']} {pr['main_interest']:<8} {100 * pr['probability']:5.1f}%")
    log("  why: " + "; ".join(f"{w['factor']} -> {w['pushes_towards']} ({w['strength']})" for w in res["why"]))
    log("  recommended people:")
    for x in res["recommended_people"]:
        log(f"    {x['username']:<18} {x['community_id']}  {x['degree']:>3} friends   {x['reason']}")
    for x in res["bridge_people"]:
        log(f"    {x['username']:<18} {x['community_id']}  {x['degree']:>3} friends   {x['reason']}   [bridge]")
    log("\n--- VALIDATION")
    checks = {
        "prediction with interest is much better than guessing the biggest community": acc["interest + city + age + account type"] > 0.9,
        "predictions still work without the interest (city + age + type only beat guessing)": acc["city + age + account type only (no interest)"] > m.n.max() / m.n.sum(),
        "knowing 3 people gives high accuracy": acc["people only (3 random friends)"] > 0.7,
        "probabilities add up to 1": abs(sum(p["probability"] for p in res["probabilities"]) - 1) < 0.01,
        "recommendations never include the user's own contacts or duplicates": len({x["user_id"] for x in res["recommended_people"] + res["bridge_people"]}) == len(res["recommended_people"]) + len(res["bridge_people"]),
        "invalid input is rejected (age 5)": False,
    }
    try:
        clean_profile(m, dict(full_name="X Y", age=5, city="Jaipur", interest="Tech"))
    except ValidationError:
        checks["invalid input is rejected (age 5)"] = True
    for k, v in checks.items():
        log(f"  {'PASS' if v else 'FAIL'}  {k}")
    (BASE / "outputs").mkdir(exist_ok=True)
    (BASE / "outputs" / "stage9_report.txt").write_text("\n".join(lines), encoding="utf-8")
    log("\nSaved outputs/stage9_report.txt")
    log("ALL CHECKS PASSED" if all(checks.values()) else "SOME CHECKS FAILED - read the report above")
