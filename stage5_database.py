"""
STAGE 5 -- SQLITE DATABASE
clean CSV + communities -> tables with keys and indexes -> SQL queries that answer real questions

Why a database?  The Flask API (Stage 6) and the web page (Stage 7+) must fetch data quickly and by question
("give me the friends of user U0040"), not re-read CSV files every time.  SQLite is one ordinary file, needs no server,
and Python already includes it (module `sqlite3`), so nothing new to install.

Tables (see the diagram at the bottom of the report):
  communities(community_id PK, users, main_interest, ...)
  users(user_id PK, username, ..., community_id FK, degree)
  connections(connection_id PK, user_id_1 FK, user_id_2 FK, connected_on, ...)   one row = one edge (user_id_1 < user_id_2)
  posts(post_id PK, user_id FK, posted_at, text, likes, ...)
  post_hashtags(post_id FK, hashtag)        one row per hashtag used in a post
  view friendships  = every edge listed in BOTH directions (makes "friends of X" a one-line query)

Input : data/clean/*.csv (Stage 2), data/graph/communities.csv + community_summary.csv (Stage 4)
Output: data/social.db, outputs/stage5_report.txt

Run in VS Code: open the file and press the Run triangle  (or: /usr/local/bin/python3 stage5_database.py)
"""
# %% 0. Setup
from pathlib import Path
import sqlite3
import pandas as pd

pd.set_option("display.width", 200)
BASE = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()


def find(*options):
    """First existing file: normal folder layout, else loose next to this script."""
    for p in options:
        if p.exists():
            return p
    raise FileNotFoundError(f"Could not find {options[-1].name}. Run the earlier stages first (Stage 2 makes clean CSVs, Stage 4 makes communities.csv).")


users = pd.read_csv(find(BASE / "data/clean/users.csv", BASE / "users.csv"))
conns = pd.read_csv(find(BASE / "data/clean/connections.csv", BASE / "connections.csv"))
posts = pd.read_csv(find(BASE / "data/clean/posts.csv", BASE / "posts.csv"))
comm = pd.read_csv(find(BASE / "data/graph/communities.csv", BASE / "communities.csv"))
csum = pd.read_csv(find(BASE / "data/graph/community_summary.csv", BASE / "community_summary.csv"))

DB = BASE / "data" / "social.db"
DB.parent.mkdir(exist_ok=True)
(BASE / "outputs").mkdir(exist_ok=True)
report = []


def say(text=""):
    print(text)
    report.append(str(text))


# %% 1. Create the empty database with its structure (schema)
if DB.exists():
    DB.unlink()                                   # start fresh every run so the script can be repeated safely
con = sqlite3.connect(DB)
con.execute("PRAGMA foreign_keys = ON")           # SQLite ignores foreign keys unless we ask
con.executescript("""
CREATE TABLE communities (
    community_id      TEXT PRIMARY KEY,           -- 'C1'..'C6' or 'Isolated'
    users             INTEGER,
    main_interest     TEXT,
    interest_share    REAL,
    main_city         TEXT,
    avg_age           REAL,
    friendships_inside  INTEGER,
    friendships_leaving INTEGER,
    inside_share      REAL,
    top_user          TEXT
);
CREATE TABLE users (
    user_id           TEXT PRIMARY KEY,
    username          TEXT NOT NULL UNIQUE,
    full_name         TEXT,
    age               INTEGER CHECK (age BETWEEN 13 AND 100),
    city              TEXT,
    interest          TEXT,
    account_type      TEXT CHECK (account_type IN ('personal','creator','business')),
    joined_date       TEXT,
    last_active_date  TEXT,
    is_verified       INTEGER,
    community_id      TEXT REFERENCES communities(community_id),
    degree            INTEGER,                    -- number of friends (from the graph)
    friends_outside_community INTEGER
);
CREATE TABLE connections (
    connection_id     TEXT PRIMARY KEY,
    user_id_1         TEXT NOT NULL REFERENCES users(user_id),
    user_id_2         TEXT NOT NULL REFERENCES users(user_id),
    connected_on      TEXT,
    interaction_count INTEGER,
    date_estimated    INTEGER,
    CHECK (user_id_1 < user_id_2),                -- one row per friendship, never A-B and B-A
    UNIQUE (user_id_1, user_id_2)
);
CREATE TABLE posts (
    post_id           TEXT PRIMARY KEY,
    user_id           TEXT NOT NULL REFERENCES users(user_id),
    posted_at         TEXT,
    text              TEXT NOT NULL,
    hashtags          TEXT,
    likes             INTEGER CHECK (likes >= 0),
    shares            INTEGER,
    comments          INTEGER
);
CREATE TABLE post_hashtags (
    post_id           TEXT NOT NULL REFERENCES posts(post_id),
    hashtag           TEXT NOT NULL,
    PRIMARY KEY (post_id, hashtag)
);
CREATE INDEX idx_conn_1 ON connections(user_id_1);
CREATE INDEX idx_conn_2 ON connections(user_id_2);
CREATE INDEX idx_posts_user ON posts(user_id);
CREATE INDEX idx_users_comm ON users(community_id);
CREATE INDEX idx_tags ON post_hashtags(hashtag);
CREATE VIEW friendships AS
    SELECT user_id_1 AS user_id, user_id_2 AS friend_id FROM connections
    UNION ALL
    SELECT user_id_2, user_id_1 FROM connections;
""")

# %% 2. Fill the tables
csum_db = csum.rename(columns={"community": "community_id", "interest_share_%": "interest_share", "inside_share_%": "inside_share",
                               "main_interest": "main_interest", "friendships_inside": "friendships_inside"})
csum_db = csum_db[["community_id", "users", "main_interest", "interest_share", "main_city", "avg_age",
                   "friendships_inside", "friendships_leaving", "inside_share", "top_user"]]
iso_row = pd.DataFrame([{"community_id": "Isolated", "users": int((comm["community"] == "Isolated").sum()), "main_interest": None,
                         "interest_share": None, "main_city": None, "avg_age": None, "friendships_inside": 0,
                         "friendships_leaving": 0, "inside_share": None, "top_user": None}])
pd.concat([csum_db, iso_row]).to_sql("communities", con, if_exists="append", index=False)

u = users.merge(comm[["user_id", "community", "degree", "friends_outside_community"]], on="user_id", how="left") \
         .rename(columns={"community": "community_id"})
u["is_verified"] = u["is_verified"].astype(int)
u.to_sql("users", con, if_exists="append", index=False)

c = conns.copy()
c["date_estimated"] = c["date_estimated"].astype(int)
c.to_sql("connections", con, if_exists="append", index=False)

posts.to_sql("posts", con, if_exists="append", index=False)
tags = posts[["post_id", "hashtags"]].dropna()
tags = tags.assign(hashtag=tags["hashtags"].str.split()).explode("hashtag")[["post_id", "hashtag"]]
tags = tags[tags["hashtag"].notna() & (tags["hashtag"] != "")].drop_duplicates()
tags.to_sql("post_hashtags", con, if_exists="append", index=False)
con.commit()

say("STAGE 5 DATABASE REPORT")
say("=" * 90)
say(f"Created {DB}  ({DB.stat().st_size / 1024:.0f} KB)")
for t in ["communities", "users", "connections", "posts", "post_hashtags"]:
    say(f"  table {t:<14} {con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]:>6} rows")


# %% 3. Ask questions with SQL
def q(title, sql, params=()):
    """Run one SQL query, print the SQL and the answer."""
    say(f"\n--- {title}")
    say("SQL: " + " ".join(sql.split()))
    df = pd.read_sql_query(sql, con, params=params)
    say(df.to_string(index=False) if len(df) else "(no rows)")
    return df


q("Q1. The 10 most connected users, with their community",
  """SELECT u.username, u.city, u.interest, u.community_id AS community, u.degree
     FROM users u ORDER BY u.degree DESC LIMIT 10""")

q("Q2. How big is each community and what is its average age?",
  """SELECT community_id, COUNT(*) AS users, ROUND(AVG(age),1) AS avg_age, ROUND(AVG(degree),1) AS avg_friends
     FROM users GROUP BY community_id ORDER BY users DESC""")

q("Q3. Top 3 hashtags in every community (JOIN of 4 tables + a ranking window function)",
  """SELECT community_id, hashtag, uses FROM (
         SELECT u.community_id, h.hashtag, COUNT(*) AS uses,
                ROW_NUMBER() OVER (PARTITION BY u.community_id ORDER BY COUNT(*) DESC, h.hashtag) AS rn
         FROM post_hashtags h JOIN posts p ON p.post_id = h.post_id JOIN users u ON u.user_id = p.user_id
         GROUP BY u.community_id, h.hashtag)
     WHERE rn <= 3 AND community_id <> 'Isolated' ORDER BY community_id, rn""")

q("Q4. Most liked 5 posts",
  """SELECT p.post_id, u.username, p.likes, p.shares, p.comments, SUBSTR(p.text,1,55) AS text
     FROM posts p JOIN users u ON u.user_id = p.user_id ORDER BY p.likes DESC LIMIT 5""")

q("Q5. Creators vs personal vs business accounts: posts and likes",
  """SELECT u.account_type, COUNT(DISTINCT u.user_id) AS users, COUNT(p.post_id) AS posts,
            ROUND(1.0*COUNT(p.post_id)/COUNT(DISTINCT u.user_id),2) AS posts_per_user,
            ROUND(AVG(p.likes),2) AS avg_likes
     FROM users u LEFT JOIN posts p ON p.user_id = u.user_id GROUP BY u.account_type""")

q("Q6. New friendships per year",
  """SELECT SUBSTR(connected_on,1,4) AS year, COUNT(*) AS new_friendships
     FROM connections GROUP BY year ORDER BY year""")

star = q("Q7. Friends of one user (uses the view 'friendships') -- the query the API will run for /api/users/<id>/friends",
         """SELECT f.friend_id, u.username, u.community_id AS community
            FROM friendships f JOIN users u ON u.user_id = f.friend_id WHERE f.user_id = ? ORDER BY u.username LIMIT 8""",
         ("U0040",))

q("Q8. Mutual friends of two users (first 10 shown)",
  """SELECT a.friend_id, u.username FROM friendships a JOIN friendships b ON a.friend_id = b.friend_id
     JOIN users u ON u.user_id = a.friend_id WHERE a.user_id = ? AND b.user_id = ? ORDER BY u.username LIMIT 10""", ("U0040", "U0254"))

q("Q9. 'People you may know' for one user: friends-of-friends they are NOT yet friends with, ranked by mutual friends",
  """SELECT u.username, u.community_id AS community, COUNT(*) AS mutual_friends
     FROM friendships a JOIN friendships b ON b.user_id = a.friend_id
     JOIN users u ON u.user_id = b.friend_id
     WHERE a.user_id = ? AND b.friend_id <> a.user_id
       AND b.friend_id NOT IN (SELECT friend_id FROM friendships WHERE user_id = ?)
     GROUP BY b.friend_id ORDER BY mutual_friends DESC, u.username LIMIT 5""", ("U0338", "U0338"))

q("Q10. Friendships between communities (the numbers behind the network's 'bridges')",
  """SELECT a.community_id AS from_community, b.community_id AS to_community, COUNT(*) AS friendships
     FROM connections c JOIN users a ON a.user_id = c.user_id_1 JOIN users b ON b.user_id = c.user_id_2
     WHERE a.community_id < b.community_id GROUP BY 1, 2 ORDER BY friendships DESC LIMIT 8""")

q("Q11. Users with no friends (isolated)",
  """SELECT user_id, username, city, interest FROM users WHERE degree = 0 ORDER BY user_id LIMIT 10""")

# %% 4. Validate: does the database agree with the CSV files and the graph?
say("\n--- VALIDATION")
one = lambda sql: con.execute(sql).fetchone()[0]
checks = {
    "row counts equal the clean CSV files":
        (one("SELECT COUNT(*) FROM users"), one("SELECT COUNT(*) FROM connections"), one("SELECT COUNT(*) FROM posts")) == (len(users), len(conns), len(posts)),
    "foreign keys: no orphan rows (PRAGMA foreign_key_check)": len(con.execute("PRAGMA foreign_key_check").fetchall()) == 0,
    "friendships view has exactly 2 x connections rows": one("SELECT COUNT(*) FROM friendships") == 2 * len(conns),
    "degree stored in users = friends counted by SQL for every user":
        one("""SELECT COUNT(*) FROM users u WHERE u.degree <> (SELECT COUNT(*) FROM friendships f WHERE f.user_id = u.user_id)""") == 0,
    "sum of degrees = 2 x edges (handshake lemma)": one("SELECT SUM(degree) FROM users") == 2 * len(conns),
    "community sizes add up to number of users": one("SELECT SUM(users) FROM communities") == len(users),
    "every user has a community": one("SELECT COUNT(*) FROM users WHERE community_id IS NULL") == 0,
    "no missing values in users": one("SELECT COUNT(*) FROM users WHERE age IS NULL OR city IS NULL OR interest IS NULL") == 0,
    "database refuses bad data (self-friendship is rejected)": None,
}
try:
    con.execute("INSERT INTO connections VALUES ('TEST','U0001','U0001','2025-01-01',1,0)")
    checks["database refuses bad data (self-friendship is rejected)"] = False
except sqlite3.IntegrityError:
    checks["database refuses bad data (self-friendship is rejected)"] = True
con.rollback()
for k, v in checks.items():
    say(f"  {'PASS' if v else 'FAIL'}  {k}")

# %% 5. Save
con.close()
say("""
--- TABLE RELATIONSHIPS
  communities 1 ---- * users 1 ---- * posts 1 ---- * post_hashtags
                        users * ---- * users   (through the connections table = the graph's edges)""")
open(BASE / "outputs" / "stage5_report.txt", "w", encoding="utf-8").write("\n".join(report))
say(f"\nSaved {DB} and outputs/stage5_report.txt")
say("ALL CHECKS PASSED" if all(checks.values()) else "SOME CHECKS FAILED - read the report above")
