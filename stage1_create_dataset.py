"""
STAGE 1 -- Create a synthetic social-media dataset (about 1,000 users) with deliberate errors.

Why synthetic?  Real social-media data is private.  Making our own lets us
  * choose columns that fit the project (users, friendships, posts),
  * hide a "ground truth" (each user's real interest group) to test community detection later,
  * plant 2-5% ERRORS so that Stage 2 (data cleaning) has something real to fix.

Output (data/raw/):            users.csv        one row per person
                               connections.csv  one row per friendship (an edge of the graph)
                               posts.csv        one row per post
Answer key (data/answer_key/): anomalies.csv    a list of every planted error, so we can check
                                                in Stage 2 that our cleaning found them all.

Run:  python stage1_create_dataset.py
"""
import random
from pathlib import Path
import numpy as np
import pandas as pd

SEED = 2026
rng = random.Random(SEED)
nrng = np.random.default_rng(SEED)
SNAPSHOT = pd.Timestamp("2026-09-01")          # "today" inside the dataset
BASE = Path(__file__).resolve().parent          # works from any terminal folder
RAW, KEY = BASE / "data" / "raw", BASE / "data" / "answer_key"
RAW.mkdir(parents=True, exist_ok=True); KEY.mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------------ ingredients
INTERESTS = {            # interest -> (number of users, hashtag pool, post sentences)
    "Tech":    (240, ["#AI", "#coding", "#python", "#startup", "#gadgets", "#opensource", "#datascience"],
                ["Just tried a new project, so much fun to build!", "Anyone else excited about this year in tech?",
                 "Weekend hackathon done, learned a lot.", "Reading about how this works under the hood."]),
    "Sports":  (200, ["#cricket", "#IPL", "#football", "#fitness", "#kabaddi", "#marathon", "#gym"],
                ["What a match last night!", "Morning workout complete.", "Cannot believe that final over.",
                 "Training for the next race."]),
    "Music":   (170, ["#bollywood", "#indie", "#concert", "#playlist", "#guitar", "#hiphop", "#lofi"],
                ["On repeat all week.", "Best concert I have been to.", "Made a new playlist for the weekend.",
                 "Learning a new song on guitar."]),
    "Food":    (150, ["#streetfood", "#biryani", "#recipe", "#cafe", "#foodie", "#chai", "#baking"],
                ["Tried this place today, loved it.", "Sharing my favourite recipe.", "Nothing beats a good chai.",
                 "Baked something new this weekend."]),
    "Travel":  (140, ["#trekking", "#roadtrip", "#backpacking", "#heritage", "#beach", "#mountains", "#wanderlust"],
                ["Finally made it to the top!", "Planning the next trip already.", "Sunrise views were unreal.",
                 "Best road trip of the year."]),
    "Fashion": (100, ["#ootd", "#streetstyle", "#thrift", "#sneakers", "#denim", "#vintage", "#style"],
                ["Today's outfit.", "Found the best thrift store.", "New sneakers just dropped.",
                 "Trying a new look."]),
}
CITIES = ["Jaipur", "Delhi", "Mumbai", "Bengaluru", "Kolkata", "Chennai", "Hyderabad", "Pune", "Ahmedabad", "Lucknow"]
FIRST = ["Aarav", "Vivaan", "Aditya", "Diya", "Ananya", "Ishaan", "Kavya", "Rohan", "Saanvi", "Arjun", "Meera", "Kabir",
         "Riya", "Neha", "Rahul", "Priya", "Karan", "Sneha", "Vikram", "Pooja", "Manav", "Tanvi", "Yash", "Nisha", "Dev",
         "Isha", "Harsh", "Aisha", "Nikhil", "Simran", "Aryan", "Kiara", "Rishi", "Anika", "Varun", "Tara", "Sameer",
         "Naina", "Kunal", "Zara", "Om", "Divya", "Rajat", "Mira", "Tejas", "Sara", "Lakshay", "Ira", "Pranav", "Ritu"]
LAST = ["Sharma", "Verma", "Gupta", "Singh", "Patel", "Iyer", "Nair", "Reddy", "Das", "Mehta", "Joshi", "Khan", "Roy",
        "Kapoor", "Bose", "Menon", "Agarwal", "Chopra", "Jain", "Shah", "Rao", "Malhotra", "Saxena", "Bhatt", "Pillai"]
DOMAINS = ["example.com", "example.org", "example.net"]        # reserved fake domains: no real person can own them


def rand_date(start, end):
    """Random date between two Timestamps."""
    return start + pd.Timedelta(days=int(nrng.integers(0, max((end - start).days, 1) + 1)))


# ------------------------------------------------------------------ 1. users (clean version)
def make_users():
    interests = [i for i, (n, _, _) in INTERESTS.items() for _ in range(n)]
    rng.shuffle(interests)                                    # so user ids do not reveal the community
    rows, used = [], set()
    for k, interest in enumerate(interests, start=1):
        first, last = rng.choice(FIRST), rng.choice(LAST)
        username = f"{first}_{last}{rng.randint(1, 99)}".lower()
        while username in used:
            username = f"{first}_{last}{rng.randint(1, 999)}".lower()
        used.add(username)
        home = CITIES[list(INTERESTS).index(interest) % len(CITIES)]
        joined = rand_date(pd.Timestamp("2019-01-01"), pd.Timestamp("2025-12-31"))
        active_gap = int((SNAPSHOT - joined).days * nrng.beta(4, 1.5))
        rows.append(dict(
            user_id=f"U{k:04d}", username=username, full_name=f"{first} {last}",
            email=f"{username}@{rng.choice(DOMAINS)}",
            age=int(np.clip(nrng.normal(27, 7), 16, 60)),
            city=home if rng.random() < 0.6 else rng.choice(CITIES),
            interest=interest,
            account_type=rng.choices(["personal", "creator", "business"], [0.80, 0.15, 0.05])[0],
            joined_date=joined.strftime("%Y-%m-%d"),
            last_active_date=(joined + pd.Timedelta(days=active_gap)).strftime("%Y-%m-%d"),
            is_verified=False))
    df = pd.DataFrame(rows)
    df["is_verified"] = [(t == "creator" and rng.random() < 0.10) or (t == "business" and rng.random() < 0.3)
                         for t in df["account_type"]]
    return df


# ------------------------------------------------------------------ 2. connections (clean version)
def make_connections(users):
    n = len(users)
    grp = pd.factorize(users["interest"])[0]
    same = grp[:, None] == grp[None, :]
    P = np.where(same, 0.025, 0.0006)                         # friends are far more likely inside the same interest group
    A = np.triu(nrng.random((n, n)) < P, 1)
    edges = {tuple(e) for e in np.argwhere(A)}
    for g in range(grp.max() + 1):                            # 3 "influencers" per group with many friends
        members = np.where(grp == g)[0]
        others = np.where(grp != g)[0]
        for hub in nrng.choice(members, 3, replace=False):
            for v in nrng.choice(members, int(0.35 * len(members)), replace=False):
                if v != hub: edges.add((min(hub, v), max(hub, v)))
            for v in nrng.choice(others, int(0.03 * len(others)), replace=False):
                edges.add((min(hub, v), max(hub, v)))
    lonely = set(nrng.choice(n, 10, replace=False).tolist())  # a few users with no friends at all
    edges = {e for e in edges if e[0] not in lonely and e[1] not in lonely}
    joined = pd.to_datetime(users["joined_date"]).to_numpy()
    rows = []
    for a, b in sorted(edges):
        start = pd.Timestamp(max(joined[a], joined[b]))
        rows.append(dict(user_id_1=users.at[a, "user_id"], user_id_2=users.at[b, "user_id"],
                         connected_on=rand_date(start, SNAPSHOT).strftime("%Y-%m-%d"),
                         interaction_count=1 + int(nrng.poisson(6 if grp[a] == grp[b] else 2))))
    df = pd.DataFrame(rows).sample(frac=1, random_state=SEED).reset_index(drop=True)
    for i in range(len(df)):                                  # random orientation, so (a,b) vs (b,a) shows no pattern
        if rng.random() < 0.5:
            df.loc[i, ["user_id_1", "user_id_2"]] = df.loc[i, ["user_id_2", "user_id_1"]].to_numpy()
    df.insert(0, "connection_id", [f"C{k:05d}" for k in range(1, len(df) + 1)])
    return df


# ------------------------------------------------------------------ 3. posts (clean version)
def make_posts(users, conns):
    degree = pd.concat([conns["user_id_1"], conns["user_id_2"]]).value_counts()
    all_tags = sum((v[1] for v in INTERESTS.values()), [])
    rows = []
    for u in users.itertuples():
        n_posts = int(nrng.poisson(6 if u.account_type == "creator" else 3))
        deg = degree.get(u.user_id, 0)
        for _ in range(n_posts):
            _, tags, texts = INTERESTS[u.interest]
            pool = tags if rng.random() < 0.88 else all_tags
            likes = int(nrng.lognormal(1.5 + 0.35 * np.log1p(deg), 0.7))   # popular users get more likes
            when = rand_date(pd.Timestamp(u.joined_date), SNAPSHOT) + pd.Timedelta(seconds=int(nrng.integers(0, 86400)))
            rows.append(dict(user_id=u.user_id, posted_at=when.strftime("%Y-%m-%d %H:%M:%S"),
                             text=rng.choice(texts), hashtags=" ".join(rng.sample(pool, rng.randint(1, 3))),
                             likes=likes, shares=int(nrng.binomial(likes, 0.08)), comments=int(nrng.binomial(likes, 0.05))))
    df = pd.DataFrame(rows).sample(frac=1, random_state=SEED).reset_index(drop=True)
    df.insert(0, "post_id", [f"P{k:05d}" for k in range(1, len(df) + 1)])
    return df


# ------------------------------------------------------------------ 4. plant the errors
class Planter:
    """Picks DIFFERENT rows for every error type (so nothing overlaps) and writes each error to the answer key."""
    def __init__(self, df, id_col, table):
        self.df, self.id_col, self.table, self.key = df.copy(), id_col, table, []
        self.pool = list(range(len(df)))
        rng.shuffle(self.pool)

    def take(self, k):
        return [self.pool.pop() for _ in range(k)]

    def log(self, i, column, kind, detail=""):
        self.key.append(dict(table=self.table, record_id=self.df.at[i, self.id_col], column=column,
                             anomaly_type=kind, detail=detail))


def rows_for(rate, n):
    return max(1, round(rate * n))


def plant_users(users):
    p = Planter(users, "user_id", "users")
    df = p.df
    n = len(df)
    dup_idx = p.take(10)                                       # 1% exact duplicate rows
    for i in p.take(8):  p.log(i, "age", "missing_value"); df.at[i, "age"] = np.nan
    for i in p.take(6):  p.log(i, "city", "missing_value"); df.at[i, "city"] = rng.choice(["", "N/A"])
    for i in p.take(4):  p.log(i, "email", "missing_value"); df.at[i, "email"] = ""
    for i in p.take(4):
        bad = rng.choice([-5, 0, 150, 999]); p.log(i, "age", "invalid_value", f"age={bad}"); df.at[i, "age"] = bad
    for i in p.take(8):                                        # inconsistent spelling of city
        old = df.at[i, "city"]
        new = rng.choice([old.lower(), old.upper(), old + " ", {"Bengaluru": "Bangalore", "Delhi": "New Delhi"}.get(old, " " + old)])
        p.log(i, "city", "inconsistent_format", f"'{old}' -> '{new}'"); df.at[i, "city"] = new
    for i in p.take(5):                                        # date written in a different style
        d = pd.Timestamp(df.at[i, "joined_date"])
        new = rng.choice([d.strftime("%d/%m/%Y"), d.strftime("%B %d, %Y")])
        p.log(i, "joined_date", "inconsistent_format", f"'{df.at[i, 'joined_date']}' -> '{new}'"); df.at[i, "joined_date"] = new
    dups = df.loc[dup_idx].copy()
    for i in dup_idx: p.log(i, "(whole row)", "duplicate_row")
    df = pd.concat([df, dups]).sample(frac=1, random_state=SEED).reset_index(drop=True)
    return df, p.key


def plant_connections(conns, users):
    p = Planter(conns, "connection_id", "connections")
    df, n = p.df, len(conns)
    joined = users.set_index("user_id")["joined_date"].pipe(pd.to_datetime)
    dup_idx, rev_idx = p.take(rows_for(0.011, n)), p.take(rows_for(0.006, n))
    for i in p.take(rows_for(0.005, n)):
        p.log(i, "user_id_2", "self_connection"); df.at[i, "user_id_2"] = df.at[i, "user_id_1"]
    for i in p.take(rows_for(0.006, n)):
        ghost = f"U{rng.randint(5000, 9999)}"; p.log(i, "user_id_2", "unknown_user", ghost); df.at[i, "user_id_2"] = ghost
    for i in p.take(rows_for(0.005, n)):
        p.log(i, "connected_on", "missing_value"); df.at[i, "connected_on"] = ""
    for i in p.take(rows_for(0.004, n)):
        latest = max(joined[df.at[i, "user_id_1"]], joined[df.at[i, "user_id_2"]])
        new = (latest - pd.Timedelta(days=int(nrng.integers(30, 400)))).strftime("%Y-%m-%d")
        p.log(i, "connected_on", "date_before_accounts_existed", new); df.at[i, "connected_on"] = new
    dups = df.loc[dup_idx].copy()
    for i in dup_idx: p.log(i, "(whole row)", "duplicate_row")
    rev = df.loc[rev_idx].copy()                               # same friendship again, ids swapped, new connection_id
    rev[["user_id_1", "user_id_2"]] = rev[["user_id_2", "user_id_1"]].to_numpy()
    rev["connection_id"] = [f"C{n + 1 + k:05d}" for k in range(len(rev))]
    for _, r in rev.iterrows():
        p.key.append(dict(table="connections", record_id=r["connection_id"], column="user_id_1/user_id_2",
                          anomaly_type="reversed_duplicate", detail="same friendship written the other way round"))
    df = pd.concat([df, dups, rev]).sample(frac=1, random_state=SEED).reset_index(drop=True)
    return df, p.key


def plant_posts(posts, users):
    p = Planter(posts, "post_id", "posts")
    df, n = p.df, len(posts)
    joined = users.set_index("user_id")["joined_date"].pipe(pd.to_datetime)
    dup_idx = p.take(rows_for(0.010, n))
    for i in p.take(rows_for(0.010, n)):
        p.log(i, "text", "missing_value"); df.at[i, "text"] = rng.choice(["", "N/A"])
    for i in p.take(rows_for(0.005, n)):
        bad = -int(nrng.integers(1, 50)); p.log(i, "likes", "invalid_value", f"likes={bad}"); df.at[i, "likes"] = bad
    for i in p.take(rows_for(0.005, n)):
        ghost = f"U{rng.randint(5000, 9999)}"; p.log(i, "user_id", "unknown_user", ghost); df.at[i, "user_id"] = ghost
    for i in p.take(rows_for(0.005, n)):
        new = (joined[df.at[i, "user_id"]] - pd.Timedelta(days=int(nrng.integers(30, 500)))).strftime("%Y-%m-%d %H:%M:%S")
        p.log(i, "posted_at", "date_before_accounts_existed", new); df.at[i, "posted_at"] = new
    for i in p.take(rows_for(0.003, n)):
        new = (SNAPSHOT + pd.Timedelta(days=int(nrng.integers(30, 600)))).strftime("%Y-%m-%d %H:%M:%S")
        p.log(i, "posted_at", "date_in_future", new); df.at[i, "posted_at"] = new
    dups = df.loc[dup_idx].copy()
    for i in dup_idx: p.log(i, "(whole row)", "duplicate_row")
    df = pd.concat([df, dups]).sample(frac=1, random_state=SEED).reset_index(drop=True)
    return df, p.key


# ------------------------------------------------------------------ main
if __name__ == "__main__":
    users = make_users()
    conns = make_connections(users)
    posts = make_posts(users, conns)
    clean_sizes = {"users": len(users), "connections": len(conns), "posts": len(posts)}

    users_raw, k1 = plant_users(users)
    conns_raw, k2 = plant_connections(conns, users)
    posts_raw, k3 = plant_posts(posts, users)

    users_raw["age"] = users_raw["age"].astype("Int64")       # whole numbers (a blank stays blank, not "23.0")
    users_raw.to_csv(RAW / "users.csv", index=False)
    conns_raw.to_csv(RAW / "connections.csv", index=False)
    posts_raw.to_csv(RAW / "posts.csv", index=False)
    key = pd.DataFrame(k1 + k2 + k3)
    key.to_csv(KEY / "anomalies.csv", index=False)

    print(f"{'table':<12}{'rows in file':>13}{'planted errors':>16}{'error rate':>12}")
    for name, df, k in [("users", users_raw, k1), ("connections", conns_raw, k2), ("posts", posts_raw, k3)]:
        print(f"{name:<12}{len(df):>13}{len(k):>16}{100 * len(k) / len(df):>11.1f}%")
    print("\nplanted errors by type:\n" + key.groupby(["table", "anomaly_type"]).size().to_string())
