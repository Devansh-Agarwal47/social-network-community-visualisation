"""
STAGE 1 (part 2) -- CSV -> pandas -> understand the columns.

We do NOT fix anything here (that is Stage 2). We only LOOK at the data and list what seems wrong.
At the end we compare our findings with the answer key, to see whether our checks caught every planted error.

Run:  python stage1_explore_data.py        (writes outputs/stage1_data_profile.txt)
"""
import re
from pathlib import Path
import pandas as pd

BASE = Path(__file__).resolve().parent          # works from any terminal folder

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)
SNAPSHOT = pd.Timestamp("2026-09-01")
report = []


def say(text=""):
    print(text)
    report.append(str(text))


def column_summary(df):
    """One row per column: type, how many filled / missing, how many different values, an example."""
    return pd.DataFrame({
        "dtype": df.dtypes.astype(str),
        "filled": df.notna().sum(),
        "missing": df.isna().sum(),
        "unique": df.nunique(),
        "example": [df[c].dropna().iloc[0] for c in df.columns],
    })


# =============================================================== 1. load the three CSV files
users = pd.read_csv(BASE / "data/raw/users.csv")
conns = pd.read_csv(BASE / "data/raw/connections.csv")
posts = pd.read_csv(BASE / "data/raw/posts.csv")

for name, df in [("USERS  (one row per person)", users), ("CONNECTIONS  (one row per friendship = one edge)", conns),
                 ("POSTS  (one row per post)", posts)]:
    say("=" * 100)
    say(name)
    say("=" * 100)
    say(f"rows x columns: {df.shape[0]} x {df.shape[1]}\n")
    say(column_summary(df).to_string())
    say("\nfirst 3 rows:")
    say(df.head(3).to_string())
    say()

# =============================================================== 2. describe the columns (what the data looks like)
say("=" * 100)
say("WHAT THE DATA LOOKS LIKE")
say("=" * 100)
say("users.interest (the hidden 'true' community of each user):")
say(users["interest"].value_counts().to_string())
say("\nusers.account_type:")
say(users["account_type"].value_counts().to_string())
say("\nusers.city (notice the odd spellings at the bottom!):")
say(users["city"].value_counts(dropna=False).to_string())
say("\nusers.age summary (look at min and max):")
say(users["age"].describe().round(1).to_string())
say("\nconnections.interaction_count summary:")
say(conns["interaction_count"].describe().round(1).to_string())
say("\nposts likes / shares / comments summary (look at the minimum of likes):")
say(posts[["likes", "shares", "comments"]].describe().round(1).to_string())

# =============================================================== 3. spot the problems (find, do not fix)
say()
say("=" * 100)
say("SPOTTING PROBLEMS  (Stage 2 will fix them)")
say("=" * 100)
CANON_CITIES = ["Jaipur", "Delhi", "Mumbai", "Bengaluru", "Kolkata", "Chennai", "Hyderabad", "Pune", "Ahmedabad", "Lucknow"]
known = set(users["user_id"])

def read_dates(series):
    """Most dates are YYYY-MM-DD, a few are written as 15/03/2022 or 'March 15, 2022'.
    We read the two styles separately. (Trap: dayfirst=True would misread the normal ISO date 2021-03-05 as 5 May!)"""
    s = series.astype("string")
    is_iso = s.str.match(r"^\d{4}-\d{2}-\d{2}( \d{2}:\d{2}:\d{2})?$").fillna(False)
    out = pd.to_datetime(s.where(is_iso), errors="coerce")
    out[~is_iso & s.notna()] = pd.to_datetime(s[~is_iso & s.notna()], format="mixed", dayfirst=True)
    return out


joined = read_dates(users.drop_duplicates("user_id").set_index("user_id")["joined_date"])

found = {}
# ---- users
found["users: duplicate rows"] = int(users.duplicated().sum())
found["users: missing age / city / email"] = int(users[["age", "city", "email"]].isna().sum().sum())
found["users: impossible age (<13 or >100)"] = int(((users["age"] < 13) | (users["age"] > 100)).sum())
found["users: city not in the standard list"] = int((users["city"].notna() & ~users["city"].isin(CANON_CITIES)).sum())
found["users: joined_date not YYYY-MM-DD"] = int((~users["joined_date"].astype(str).str.match(r"^\d{4}-\d{2}-\d{2}$")).sum())
# ---- connections
found["connections: duplicate rows"] = int(conns.duplicated().sum())
found["connections: user connected to themselves"] = int((conns["user_id_1"] == conns["user_id_2"]).sum())
found["connections: user id not in users table"] = int((~conns["user_id_1"].isin(known) | ~conns["user_id_2"].isin(known)).sum())
found["connections: missing date"] = int(conns["connected_on"].isna().sum())
# the same friendship written twice the other way round: sort each pair so (A,B) and (B,A) look identical
no_self = conns.drop_duplicates()[lambda d: d["user_id_1"] != d["user_id_2"]]      # self-connections are a separate problem
pair_key = no_self.apply(lambda r: tuple(sorted((r["user_id_1"], r["user_id_2"]))), axis=1)
found["connections: same friendship written both ways"] = int(pair_key.duplicated().sum())
cdate = read_dates(conns["connected_on"])
latest_join = pd.concat([conns["user_id_1"].map(joined), conns["user_id_2"].map(joined)], axis=1).max(axis=1)
found["connections: dated before both accounts existed"] = int((cdate < latest_join).sum())
# ---- posts
found["posts: duplicate rows"] = int(posts.duplicated().sum())
found["posts: missing text"] = int(posts["text"].isna().sum())
found["posts: negative likes"] = int((posts["likes"] < 0).sum())
found["posts: user id not in users table"] = int((~posts["user_id"].isin(known)).sum())
pdate = read_dates(posts["posted_at"])
found["posts: posted before the account existed"] = int((pdate.dt.normalize() < posts["user_id"].map(joined)).sum())
found["posts: dated in the future"] = int((pdate >= SNAPSHOT + pd.Timedelta(days=1)).sum())

# =============================================================== 4. did we find everything?  (compare with answer key)
key = pd.read_csv(BASE / "data/answer_key/anomalies.csv")


def planted(table, kind, column=None):
    k = key[(key["table"] == table) & (key["anomaly_type"] == kind)]
    return len(k if column is None else k[k["column"] == column])


planted_counts = {
    "users: duplicate rows": planted("users", "duplicate_row"),
    "users: missing age / city / email": planted("users", "missing_value"),
    "users: impossible age (<13 or >100)": planted("users", "invalid_value"),
    "users: city not in the standard list": planted("users", "inconsistent_format", "city"),
    "users: joined_date not YYYY-MM-DD": planted("users", "inconsistent_format", "joined_date"),
    "connections: duplicate rows": planted("connections", "duplicate_row"),
    "connections: user connected to themselves": planted("connections", "self_connection"),
    "connections: user id not in users table": planted("connections", "unknown_user"),
    "connections: missing date": planted("connections", "missing_value"),
    "connections: same friendship written both ways": planted("connections", "reversed_duplicate"),
    "connections: dated before both accounts existed": planted("connections", "date_before_accounts_existed"),
    "posts: duplicate rows": planted("posts", "duplicate_row"),
    "posts: missing text": planted("posts", "missing_value"),
    "posts: negative likes": planted("posts", "invalid_value"),
    "posts: user id not in users table": planted("posts", "unknown_user"),
    "posts: posted before the account existed": planted("posts", "date_before_accounts_existed"),
    "posts: dated in the future": planted("posts", "date_in_future"),
}
result = pd.DataFrame({"found by pandas": found, "planted (answer key)": planted_counts})
result["match"] = result["found by pandas"] == result["planted (answer key)"]
say(result.to_string())
say(f"\nAll {len(result)} checks match the answer key: {bool(result['match'].all())}")
say(f"Problem rows planted: users {len(key[key.table=='users'])}/{len(users)} "
    f"({100*len(key[key.table=='users'])/len(users):.1f}%), connections {len(key[key.table=='connections'])}/{len(conns)} "
    f"({100*len(key[key.table=='connections'])/len(conns):.1f}%), posts {len(key[key.table=='posts'])}/{len(posts)} "
    f"({100*len(key[key.table=='posts'])/len(posts):.1f}%)")

(BASE / "outputs").mkdir(exist_ok=True)
open(BASE / "outputs/stage1_data_profile.txt", "w").write("\n".join(report))
print("\nSaved outputs/stage1_data_profile.txt")
