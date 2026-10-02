"""
STAGE 2 -- DATA CLEANING
raw CSV  ->  remove duplicates  ->  fix / fill missing values  ->  select the required columns  ->  clean CSV

Input : data/raw/users.csv, connections.csv, posts.csv          (made in Stage 1)
Output: data/clean/users.csv, connections.csv, posts.csv
        outputs/stage2_cleaning_log.txt   (every step and how many rows it touched)
        outputs/stage2_before_after.png   (bar chart of the problems before vs after)

HOW TO RUN IN VS CODE
  * Open this folder in VS Code, open this file, press the "Run Python File" (triangle) button.
  * OR run cell by cell: every "# %%" line shows a "Run Cell" button (needs the Python extension).
  * OR in a terminal:  python stage2_clean_data.py
The script finds its own folder, so it works no matter where the terminal is opened.

RULE: the answer key (data/answer_key) is used ONLY at the very end to check our work. Never to clean.
"""
# %% 0. Setup
from pathlib import Path
import pandas as pd
import numpy as np

BASE = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
RAW, CLEAN, OUT = BASE / "data" / "raw", BASE / "data" / "clean", BASE / "outputs"
if not (RAW / "users.csv").exists():             # CSVs were downloaded loose next to this script: use them from there
    RAW = BASE
    print(f"(data/raw not found, reading the raw CSVs from {BASE})")
CLEAN.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

SNAPSHOT = pd.Timestamp("2026-09-01")            # "today" of the dataset; later dates are impossible
CANON_CITIES = ["Jaipur", "Delhi", "Mumbai", "Bengaluru", "Kolkata", "Chennai", "Hyderabad", "Pune", "Ahmedabad", "Lucknow"]
CITY_FIX = {c.lower(): c for c in CANON_CITIES}   # 'jaipur', ' Pune' , 'JAIPUR'  ->  'Jaipur', 'Pune' ...
MIN_AGE, MAX_AGE = 13, 100

log = []


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
    log.append(str(text))


def step(table, what, before, after):
    """Write one line in the log: what we did and how many rows it removed."""
    say(f"[{table:<11}] {what:<58} rows {before:>5} -> {after:>5}   (removed {before - after})")


def read_dates(series):
    """Read dates written in mixed styles: 2024-05-03 (normal) or 15/03/2022 or 'March 15, 2022'.
    Trap: dayfirst=True would misread the normal ISO date 2021-03-05 as 5 May, so ISO is read separately."""
    s = series.astype("string").str.strip()
    is_iso = s.str.match(r"^\d{4}-\d{2}-\d{2}( \d{2}:\d{2}:\d{2})?$").fillna(False)
    out = pd.to_datetime(s.where(is_iso), errors="coerce")
    other = ~is_iso & s.notna()
    if other.any():
        out[other] = pd.to_datetime(s[other], format="mixed", dayfirst=True, errors="coerce")
    return out


# %% 1. Load the raw files
users_raw = pd.read_csv(RAW / "users.csv")
conns_raw = pd.read_csv(RAW / "connections.csv")
posts_raw = pd.read_csv(RAW / "posts.csv")
say("STAGE 2 CLEANING LOG")
say("=" * 110)
say(f"raw rows: users {len(users_raw)}, connections {len(conns_raw)}, posts {len(posts_raw)}\n")


# %% 2. Snapshot of the problems BEFORE cleaning (used for the before/after chart)
def problems(users, conns, posts):
    """Count each kind of problem in a set of tables. Same function is run before AND after cleaning."""
    ud = users.drop_duplicates("user_id")
    joined = read_dates(ud.set_index("user_id")["joined_date"])
    known = set(users["user_id"])
    ok_pair = conns.drop_duplicates()[lambda d: d["user_id_1"] != d["user_id_2"]]   # count only pure both-ways repeats
    pair = ok_pair.apply(lambda r: tuple(sorted((r["user_id_1"], r["user_id_2"]))), axis=1) if len(ok_pair) else pd.Series(dtype=object)
    cd = read_dates(conns["connected_on"])
    latest_join = pd.concat([conns["user_id_1"].map(joined), conns["user_id_2"].map(joined)], axis=1).max(axis=1)
    pd_ = read_dates(posts["posted_at"])
    return {
        "users: duplicate rows": int(users.duplicated().sum()),
        "users: missing age": int(users["age"].isna().sum()),
        "users: impossible age": int(((users["age"] < MIN_AGE) | (users["age"] > MAX_AGE)).sum()),
        "users: missing / odd city": int(users["city"].isna().sum() + (users["city"].notna() & ~users["city"].isin(CANON_CITIES + ["Unknown"])).sum()),
        "users: date not YYYY-MM-DD": int((~users["joined_date"].astype(str).str.match(r"^\d{4}-\d{2}-\d{2}$")).sum()),
        "connections: duplicate rows": int(conns.duplicated().sum()),
        "connections: self-connection": int((conns["user_id_1"] == conns["user_id_2"]).sum()),
        "connections: unknown user id": int((~conns["user_id_1"].isin(known) | ~conns["user_id_2"].isin(known)).sum()),
        "connections: both-ways duplicate": int(pair.duplicated().sum()),
        "connections: missing / impossible date": int((conns["connected_on"].isna() | (cd < latest_join)).sum()),
        "posts: duplicate rows": int(posts.duplicated().sum()),
        "posts: missing text": int(posts["text"].isna().sum()),
        "posts: negative likes": int((posts["likes"] < 0).sum()),
        "posts: unknown user id": int((~posts["user_id"].isin(known)).sum()),
        "posts: impossible date": int(((pd_.dt.normalize() < posts["user_id"].map(joined)) | (pd_ >= SNAPSHOT + pd.Timedelta(days=1))).sum()),
    }


before = problems(users_raw, conns_raw, posts_raw)

# %% 3. Clean USERS  (expected: 1010 -> 1000 rows)
say("--- USERS " + "-" * 100)
u = users_raw.copy()
n = len(u)

# 3a. exact duplicate rows (the same person pasted twice)
u = u.drop_duplicates().reset_index(drop=True)
step("users", "drop exact duplicate rows", n, len(u)); n = len(u)
assert u["user_id"].is_unique, "user_id must be unique after removing duplicates"

# 3b. dates: read every style, store one style (YYYY-MM-DD)
for col in ["joined_date", "last_active_date"]:
    u[col] = read_dates(u[col])
say(f"[users      ] joined_date / last_active_date converted to one format   ({int((u['joined_date'].isna()).sum())} unreadable)")

# 3c. city: fix spelling / spaces / capitals, then fill the still-missing ones with 'Unknown'
fixed = u["city"].str.strip().str.lower().map(CITY_FIX)
n_fixed = int((u["city"].notna() & (fixed != u["city"])).sum())
u["city"] = fixed
n_missing_city = int(u["city"].isna().sum())
u["city"] = u["city"].fillna("Unknown")          # not guessed: a wrong city is worse than an honest 'Unknown'
say(f"[users      ] city: {n_fixed} spellings normalised, {n_missing_city} missing filled with 'Unknown'")

# 3d. age: impossible values become 'missing', then every missing age = median age of the user's interest group
bad_age = (u["age"] < MIN_AGE) | (u["age"] > MAX_AGE)
u.loc[bad_age, "age"] = np.nan
group_median = u.groupby("interest")["age"].transform("median")
n_age = int(u["age"].isna().sum())
u["age"] = u["age"].fillna(group_median).round().astype("Int64")
say(f"[users      ] age: {int(bad_age.sum())} impossible -> missing; {n_age} missing filled with the median age of the same interest group")

# 3e. select the required columns (e-mail is personal data and not needed for a graph)
users = u[["user_id", "username", "full_name", "age", "city", "interest", "account_type",
           "joined_date", "last_active_date", "is_verified"]]
say(f"[users      ] columns kept: {len(users.columns)} of {len(users_raw.columns)}  (dropped: email, personal data not needed)\n")

# %% 4. Clean CONNECTIONS  (expected: 4008 -> 3897 rows)
say("--- CONNECTIONS " + "-" * 94)
c = conns_raw.copy()
known = set(users["user_id"])
n = len(c)

c = c.drop_duplicates().reset_index(drop=True)
step("connections", "drop exact duplicate rows", n, len(c)); n = len(c)

c = c[c["user_id_1"] != c["user_id_2"]]
step("connections", "drop self-connections (a user befriending themselves)", n, len(c)); n = len(c)

c = c[c["user_id_1"].isin(known) & c["user_id_2"].isin(known)]
step("connections", "drop connections to users that do not exist", n, len(c)); n = len(c)

# The same friendship written both ways (A,B) and (B,A): put the smaller id first, then drop repeats.
# An undirected graph has ONE edge per friendship, so this matters for degree counts in Stage 3.
a = c[["user_id_1", "user_id_2"]].min(axis=1)
b = c[["user_id_1", "user_id_2"]].max(axis=1)
c["user_id_1"], c["user_id_2"] = a, b
c = c.sort_values("connection_id").drop_duplicates(["user_id_1", "user_id_2"], keep="first")
step("connections", "drop the same friendship written the other way round", n, len(c)); n = len(c)

# dates: a friendship cannot start before both accounts exist, nor be missing.
# We do not delete the row (the friendship is real); we estimate the date and mark it.
joined = users.set_index("user_id")["joined_date"]
earliest_possible = pd.concat([c["user_id_1"].map(joined), c["user_id_2"].map(joined)], axis=1).max(axis=1)
c["connected_on"] = read_dates(c["connected_on"])
bad_date = c["connected_on"].isna() | (c["connected_on"] < earliest_possible) | (c["connected_on"] > SNAPSHOT)
c["date_estimated"] = bad_date
c.loc[bad_date, "connected_on"] = earliest_possible[bad_date]
say(f"[connections] {int(c['date_estimated'].sum())} missing/impossible dates set to the day the younger account joined (flag column date_estimated = True)")

c["interaction_count"] = c["interaction_count"].fillna(0).astype(int)
connections = c[["connection_id", "user_id_1", "user_id_2", "connected_on", "interaction_count", "date_estimated"]] \
    .sort_values("connection_id").reset_index(drop=True)
say(f"[connections] columns kept: {len(connections.columns)} (added date_estimated)\n")

# %% 5. Clean POSTS  (expected: 3482 -> 3370 rows)
say("--- POSTS " + "-" * 100)
p = posts_raw.copy()
n = len(p)

p = p.drop_duplicates().reset_index(drop=True)
step("posts", "drop exact duplicate rows", n, len(p)); n = len(p)

p = p[p["user_id"].isin(known)]
step("posts", "drop posts written by users that do not exist", n, len(p)); n = len(p)

p = p[p["text"].notna() & (p["text"].astype(str).str.strip() != "")]
step("posts", "drop posts with no text (nothing to analyse)", n, len(p)); n = len(p)

p["posted_at"] = read_dates(p["posted_at"])
too_early = p["posted_at"].dt.normalize() < p["user_id"].map(joined)
too_late = p["posted_at"] >= SNAPSHOT + pd.Timedelta(days=1)
p = p[p["posted_at"].notna() & ~too_early & ~too_late]
step("posts", f"drop impossible timestamps ({int(too_early.sum())} before join, {int(too_late.sum())} in future)", n, len(p)); n = len(p)

neg = p["likes"] < 0
med_likes = int(p.loc[~neg, "likes"].median())
p.loc[neg, "likes"] = med_likes
say(f"[posts      ] likes: {int(neg.sum())} negative values replaced with the median ({med_likes})")
p["hashtags"] = p["hashtags"].fillna("")
posts = p[["post_id", "user_id", "posted_at", "text", "hashtags", "likes", "shares", "comments"]] \
    .sort_values("post_id").reset_index(drop=True)
say(f"[posts      ] columns kept: {len(posts.columns)}\n")

# %% 6. Save the clean tables
for name, df in [("users", users), ("connections", connections), ("posts", posts)]:
    df.to_csv(CLEAN / f"{name}.csv", index=False, date_format="%Y-%m-%d %H:%M:%S" if name == "posts" else "%Y-%m-%d")
say(f"SAVED clean files to {CLEAN}")

# %% 7. Validate: run the SAME problem checks on the clean data + some structural rules
after = problems(pd.read_csv(CLEAN / "users.csv"), pd.read_csv(CLEAN / "connections.csv"), pd.read_csv(CLEAN / "posts.csv"))
cu, cc, cp = (pd.read_csv(CLEAN / f"{t}.csv") for t in ["users", "connections", "posts"])
checks = {
    "no problem of any kind left (all 15 counts are 0)": all(v == 0 for v in after.values()),
    "user_id unique": cu["user_id"].is_unique,
    "no missing values in users": int(cu.isna().sum().sum()) == 0,
    "every connection joins two existing users": bool(cc["user_id_1"].isin(cu["user_id"]).all() and cc["user_id_2"].isin(cu["user_id"]).all()),
    "every connection has user_id_1 < user_id_2 (one edge per friendship)": bool((cc["user_id_1"] < cc["user_id_2"]).all()),
    "no repeated friendship": not cc.duplicated(["user_id_1", "user_id_2"]).any(),
    "no missing values in connections / posts": int(cc.isna().sum().sum() + cp.drop(columns="hashtags").isna().sum().sum()) == 0,
    "likes never negative": bool((cp["likes"] >= 0).all()),
    "every post belongs to an existing user": bool(cp["user_id"].isin(cu["user_id"]).all()),
    "ages between 13 and 100": bool(cu["age"].between(MIN_AGE, MAX_AGE).all()),
}
say("\nVALIDATION")
for k, v in checks.items():
    say(f"  {'PASS' if v else 'FAIL'}  {k}")
say("\nPROBLEMS BEFORE vs AFTER")
say(pd.DataFrame({"before": before, "after": after}).to_string())

# %% 8. Check against the hidden answer key (verification only, the key was NOT used to clean)
key_path = next((p for p in [BASE / "data" / "answer_key" / "anomalies.csv", BASE / "anomalies.csv"] if p.exists()), BASE / "anomalies.csv")
if key_path.exists():
    key = pd.read_csv(key_path)
    exp = {"users": 1010 - (key.query("table=='users' and anomaly_type=='duplicate_row'").shape[0]),
           "connections": len(conns_raw) - key.query("table=='connections' and anomaly_type in ['duplicate_row','self_connection','unknown_user','reversed_duplicate']").shape[0],
           "posts": len(posts_raw) - key.query("table=='posts' and anomaly_type in ['duplicate_row','unknown_user','missing_value','date_before_accounts_existed','date_in_future']").shape[0]}
    got = {"users": len(users), "connections": len(connections), "posts": len(posts)}
    say("\nANSWER-KEY CHECK (rows expected after removing planted bad rows vs rows we kept)")
    for t in exp:
        say(f"  {'PASS' if exp[t] == got[t] else 'FAIL'}  {t}: expected {exp[t]}, got {got[t]}")
    checks["answer key row counts match"] = all(exp[t] == got[t] for t in exp)

# %% 9. Before / after chart
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(10, 6.5))
labels = list(before)[::-1]
y = np.arange(len(labels))
ax.barh(y + 0.2, [before[k] for k in labels], 0.4, color="#d1495b", label="before cleaning")
ax.barh(y - 0.2, [after[k] for k in labels], 0.4, color="#2a9d8f", label="after cleaning")
ax.set_yticks(y, labels)
ax.set_xlabel("number of problem rows")
ax.set_title("Stage 2: problems found in the data, before vs after cleaning")
ax.legend(loc="lower right")
plt.tight_layout()
plt.savefig(OUT / "stage2_before_after.png", dpi=140)
plt.close()

open(OUT / "stage2_cleaning_log.txt", "w", encoding="utf-8").write("\n".join(log))
say(f"\nSaved outputs/stage2_cleaning_log.txt and outputs/stage2_before_after.png")
say("ALL CHECKS PASSED" if all(checks.values()) else "SOME CHECKS FAILED - read the log above")
open_files(OUT / "stage2_before_after.png")
