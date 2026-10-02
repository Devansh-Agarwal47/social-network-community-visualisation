"""
STAGE 6 (part 2) -- automatic test of every API endpoint. No server needs to be running.
It calls each URL through Flask's test client and compares the answers with the database / earlier stages.
Run:  /usr/local/bin/python3 stage6_test_api.py
"""
import sqlite3
from pathlib import Path
from stage6_api import app, DB

client = app.test_client()
con = sqlite3.connect(DB)
results = []


def check(name, condition):
    results.append(condition)
    print(f"  {'PASS' if condition else 'FAIL'}  {name}")


get = lambda url: client.get(url)
j = lambda url: client.get(url).get_json()
sql = lambda s, p=(): con.execute(s, p).fetchone()[0]

print("API TESTS")
check("web site (/) loads", get("/").status_code == 200 and b"<canvas" in get("/").data)
check("API index (/api) loads", get("/api").status_code == 200 and b"Social network API" in get("/api").data)
check("static files are served (app.js, d3)", get("/static/app.js").status_code == 200 and get("/static/vendor/d3.min.js").status_code == 200)
cl = j("/api/community_links")["links"]
check("community_links: all rows add up to all 3897 friendships", sum(x["friendships"] for x in cl) == 3897)
check("community_links: rows with a != b equal cross-community friendships",
      sum(x["friendships"] for x in cl if x["a"] != x["b"]) == sql("SELECT COUNT(*) FROM connections c JOIN users a ON a.user_id=c.user_id_1 JOIN users b ON b.user_id=c.user_id_2 WHERE a.community_id<>b.community_id"))
check("/api/health ok", j("/api/health") == {"status": "ok", "users": sql("SELECT COUNT(*) FROM users")})

s = j("/api/stats")
check("/api/stats: 1000 users, 3897 friendships", (s["users"], s["friendships"]) == (1000, 3897))
check("/api/stats: 6 communities, 10 isolated", (s["communities"], s["isolated_users"]) == (6, 10))

u = j("/api/users?limit=5&sort=degree")
check("/api/users: total 1000, 5 returned, sorted by friends", u["total"] == 1000 and len(u["users"]) == 5 and u["users"][0]["degree"] == sql("SELECT MAX(degree) FROM users"))
check("/api/users: community filter", all(x["community_id"] == "C2" for x in j("/api/users?community=C2&limit=500")["users"]) and j("/api/users?community=C2")["total"] == 196)
check("/api/users: search q=ira finds ira_shah53", any(x["username"] == "ira_shah53" for x in j("/api/users?q=ira_shah")["users"]))
check("/api/users: paging (offset) gives different rows", j("/api/users?limit=3&offset=0")["users"] != j("/api/users?limit=3&offset=3")["users"])
check("/api/users: SQL injection text is harmless", get("/api/users?city=x'%20OR%20'1'='1").get_json()["total"] == 0)
check("/api/users: limit is capped at 500", j("/api/users?limit=99999")["limit"] == 500)
check("/api/users: bad limit gives 400", get("/api/users?limit=abc").status_code == 400)

p = j("/api/users/U0040")
check("/api/users/U0040: profile has degree 110 and posts", p["degree"] == 110 and p["post_count"] > 0 and len(p["recent_posts"]) <= 5)
check("/api/users/NOPE gives 404 with message", get("/api/users/NOPE").status_code == 404 and "error" in j("/api/users/NOPE"))

f = j("/api/users/U0040/friends?limit=500")
check("friends: count equals degree", f["total"] == 110 and len(f["friends"]) == 110)
check("friends: nobody is listed twice or is the user", len({x["user_id"] for x in f["friends"]}) == 110 and all(x["user_id"] != "U0040" for x in f["friends"]))

sg = j("/api/users/U0338/suggestions")["suggestions"]
friends_of = {x["user_id"] for x in j("/api/users/U0338/friends?limit=500")["friends"]}
check("suggestions: not existing friends, not self", sg and all(x["user_id"] not in friends_of and x["user_id"] != "U0338" for x in sg))
check("suggestions: sorted by mutual friends", [x["mutual_friends"] for x in sg] == sorted([x["mutual_friends"] for x in sg], reverse=True))

nw = j("/api/network?limit=300")
ids = {x["id"] for x in nw["nodes"]}
check("network: 300 nodes, links only between returned nodes", nw["node_count"] == 300 and all(l["source"] in ids and l["target"] in ids for l in nw["links"]))
check("network: node_count/link_count match lists", nw["link_count"] == len(nw["links"]))
full = j("/api/network?limit=2000")
check("network: full graph = 1000 nodes and 3897 links", (full["node_count"], full["link_count"]) == (1000, 3897))
check("network: community filter", {x["community"] for x in j("/api/network?community=C3")["nodes"]} == {"C3"})
check("network: min_degree filter", all(x["degree"] >= 30 for x in j("/api/network?min_degree=30")["nodes"]))

c = j("/api/communities")["communities"]
check("communities: 7 rows (6 + Isolated), sizes add to 1000", len(c) == 7 and sum(x["users"] for x in c) == 1000)
c1 = j("/api/communities/C1")
check("community C1: 237 users, top users, hashtags, links to others", c1["users"] == 237 and len(c1["top_users"]) == 5 and len(c1["top_hashtags"]) == 5 and len(c1["links_to_other_communities"]) >= 4)
check("community unknown gives 404", get("/api/communities/C99").status_code == 404)

ps = j("/api/posts?community=C1&limit=5")
check("posts: community filter and paging", ps["total"] > 5 and len(ps["posts"]) == 5 and all(x["community_id"] == "C1" for x in ps["posts"]))
check("posts: newest first", [x["posted_at"] for x in ps["posts"]] == sorted([x["posted_at"] for x in ps["posts"]], reverse=True))
check("posts: hashtag filter (%23 = #)", all("#cricket" in x["hashtags"] for x in j("/api/posts?hashtag=%23cricket&limit=50")["posts"]))
check("posts: total for all = 3370", j("/api/posts")["total"] == 3370)

h = j("/api/hashtags?community=C2&limit=3")["hashtags"]
check("hashtags: C2 top 3 are sports tags", len(h) == 3 and h[0]["hashtag"] in ("#cricket", "#football", "#kabaddi"))
check("CORS header present", get("/api/health").headers.get("Access-Control-Allow-Origin") == "*")
try:
    ro = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    ro.execute("DELETE FROM users"); wrote = True
except sqlite3.OperationalError:
    wrote = False
check("database is opened read-only (API cannot change data)", not wrote)


# ---------------------------------------------------------------- information flow (Stage 10)
print("\nSPREAD TESTS")
sp = j("/api/spread?strategy=top%20degree&k=5&p=0.12&seed=7")
flat = [u for r in sp["rounds"] for u in r]
check("spread: 5 seeds, rounds start with the seeds, nobody reached twice", len(sp["seeds"]) == 5 and set(sp["rounds"][0]) == {x["user_id"] for x in sp["seeds"]} and len(flat) == len(set(flat)) == sp["reached"])
check("spread: same seed gives the same run", j("/api/spread?strategy=top%20degree&k=5&p=0.12&seed=7")["rounds"] == sp["rounds"])
check("spread: per-community numbers add up to the reached total", sum(v["reached"] for v in sp["by_community"].values()) == sp["reached"])
check("spread: p=0.01 reaches (far) fewer users than p=0.4", j("/api/spread?p=0.01&seed=1")["reached"] < j("/api/spread?p=0.4&seed=1")["reached"])
check("spread: custom seeds work", j("/api/spread?seeds=U0040,U0254&p=0.1&seed=2")["seeds"][0]["user_id"] == "U0040")
check("spread: unknown seed / bad strategy / bad p give 400", get("/api/spread?seeds=U9999").status_code == 400 and get("/api/spread?strategy=magic").status_code == 400 and get("/api/spread?p=abc").status_code == 400)
cmpj = j("/api/spread/compare?trials=60")
check("compare: 4 strategies, hubs reach more than random", len(cmpj["strategies"]) == 4 and cmpj["strategies"]["top degree"]["mean"] > cmpj["strategies"]["random"]["mean"])
ctj = j("/api/spread/containment?trials=60")
check("containment: k=0 baseline is identical for every method, blocking hubs beats random", len({v[0] for v in ctj["average_reach"].values()}) == 1 and ctj["average_reach"]["top degree"][-1] < ctj["average_reach"]["random users"][-1])

# ---------------------------------------------------------------- join the network (Stage 9). Runs on a COPY of the database.
import shutil, tempfile, stage6_api, stage9_recommender as rec
tmp = Path(tempfile.mkdtemp()) / "social_copy.db"
shutil.copy(DB, tmp)
stage6_api.DB = tmp; rec.DB = tmp; rec.invalidate()
tcon = lambda: sqlite3.connect(tmp)
post = lambda url, body: client.post(url, json=body)
print("\nJOIN-THE-NETWORK TESTS (on a temporary copy, your real database is untouched)")

meta = j("/api/meta")
check("meta: cities, interests, account types, hashtags", len(meta["cities"]) == 10 and "Unknown" not in meta["cities"] and len(meta["interests"]) == 6 and len(meta["hashtags_by_interest"]["Tech"]) == 7)
profile = dict(full_name="Test Person", age=24, city="Jaipur", interest="Tech", account_type="personal", hashtags=["#python", "#coding"], friend_ids=[])
r = post("/api/predict", profile); pr = r.get_json()
check("predict: 200 and Tech user is placed in the Tech community (C1)", r.status_code == 200 and pr["predicted_community"] == "C1")
check("predict: probabilities add up to 1 and are sorted", abs(sum(x["probability"] for x in pr["probabilities"]) - 1) < 0.01 and pr["probabilities"][0]["community_id"] == "C1")
check("predict: gives reasons and 6 + 2 people", len(pr["why"]) >= 3 and len(pr["recommended_people"]) == 6 and len(pr["bridge_people"]) == 2)
check("predict: changes nothing in the database", sqlite3.connect(tmp).execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1000)
music = post("/api/predict", dict(profile, interest="Music", hashtags=[])).get_json()
check("predict: Music interest -> C3", music["predicted_community"] == "C3")
seeds = ["U0040", "U0254"]                                       # two Tech hubs
withf = post("/api/predict", dict(profile, interest="Music", hashtags=[], friend_ids=seeds)).get_json()
check("predict: people the user knows pull the prediction (Music + 2 Tech hubs: C1 probability rises)",
      next(x["probability"] for x in withf["probabilities"] if x["community_id"] == "C1") > next(x["probability"] for x in music["probabilities"] if x["community_id"] == "C1"))
check("predict: recommended people exclude the ones the user already knows", not {x["user_id"] for x in withf["recommended_people"]} & set(seeds))
for bad, msg in [(dict(profile, age=5), "age"), (dict(profile, city="Atlantis"), "city"), (dict(profile, interest="Golf"), "interest"),
                 (dict(profile, hashtags=["#nope"]), "hashtag"), (dict(profile, friend_ids=["U9999"]), "people you know")]:
    rr = post("/api/predict", bad)
    check(f"predict: bad {msg} rejected with 400 and a message", rr.status_code == 400 and msg in rr.get_json()["error"])
check("predict: non-JSON body gives 400", client.post("/api/predict", data="x", content_type="text/plain").status_code == 400)

before_deg = {u: sql("SELECT degree FROM users WHERE user_id=?", (u,)) for u in seeds}
new = dict(profile, username="test_person_1", community_id="C1", friend_ids=seeds + ["U0507"])       # U0507 is a Sports user (bridge)
rc = post("/api/users", new); created = rc.get_json()
check("create: 201 and new id U1001", rc.status_code == 201 and created["user_id"] == "U1001" and created["community_id"] == "C1")
c2 = tcon(); one2 = lambda q, p=(): c2.execute(q, p).fetchone()[0]
check("create: user row saved with degree 3 and 1 friend outside the community", c2.execute("SELECT degree, friends_outside_community, community_id, username FROM users WHERE user_id='U1001'").fetchone() == (3, 1, "C1", "test_person_1"))
check("create: 3 connection rows saved, ordered user_id_1 < user_id_2", one2("SELECT COUNT(*) FROM connections WHERE 'U1001' IN (user_id_1,user_id_2)") == 3 and one2("SELECT COUNT(*) FROM connections WHERE user_id_1 >= user_id_2") == 0)
check("create: the friends' degrees went up by exactly 1", all(one2("SELECT degree FROM users WHERE user_id=?", (u,)) == before_deg[u] + 1 for u in seeds))
check("create: database still consistent (foreign keys, handshake lemma, degrees = counted friends)",
      len(c2.execute("PRAGMA foreign_key_check").fetchall()) == 0 and one2("SELECT SUM(degree) FROM users") == 2 * one2("SELECT COUNT(*) FROM connections")
      and one2("SELECT COUNT(*) FROM users u WHERE u.degree <> (SELECT COUNT(*) FROM friendships f WHERE f.user_id=u.user_id)") == 0)
check("create: community C1 now has 238 users and all community sizes add up to 1001", one2("SELECT users FROM communities WHERE community_id='C1'") == 238 and one2("SELECT SUM(users) FROM communities") == 1001)
inside = one2("SELECT COUNT(*) FROM connections c JOIN users a ON a.user_id=c.user_id_1 JOIN users b ON b.user_id=c.user_id_2 WHERE a.community_id='C1' AND b.community_id='C1'")
check("create: stored 'friendships inside' for C1 equals a fresh count", one2("SELECT friendships_inside FROM communities WHERE community_id='C1'") == inside)
check("create: the API shows the new user (stats, profile, friends, network)",
      j("/api/stats")["users"] == 1001 and j("/api/users/U1001")["degree"] == 3 and len(j("/api/users/U1001/friends")["friends"]) == 3
      and "U1001" in {x["id"] for x in j("/api/network?limit=2000")["nodes"]})
check("create: the model learned the new user (re-fitted)", int(rec.get_model().n.sum()) == 991)
check("create: same username again is rejected", post("/api/users", new).status_code == 400 and one2("SELECT COUNT(*) FROM users") == 1001)
check("create: username availability endpoint", j("/api/username_available?u=test_person_1")["available"] is False and j("/api/username_available?u=free_name_123")["available"] is True)
auto = post("/api/users", dict(profile, community_id="C1", friend_ids=[])).get_json()
check("create: no username given -> a free one is generated; user with no friends allowed", auto["username"] == "test_person" and j(f"/api/users/{auto['user_id']}")["degree"] == 0)
for bad, msg in [(dict(new, username="x!"), "username"), (dict(new, username="ok_name", community_id="C9"), "community"), (dict(new, username="ok_name", age="abc"), "age"), (dict(new, username="ok_name", full_name="A"), "full name")]:
    rr = post("/api/users", bad)
    check(f"create: bad {msg} rejected, nothing saved", rr.status_code == 400 and one2("SELECT COUNT(*) FROM users") == 1002)
shutil.rmtree(tmp.parent, ignore_errors=True)

print("\nALL API TESTS PASSED" if all(results) else f"\n{results.count(False)} TEST(S) FAILED")
