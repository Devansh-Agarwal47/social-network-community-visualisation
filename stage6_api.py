"""
STAGE 6 -- FLASK BACKEND AND API
database -> small web server -> URLs that return JSON  (the web page in Stage 7 will call these URLs)

API = a list of URLs. Open one in the browser and the server answers with data (JSON) instead of a web page.
Flask = the Python library that turns Python functions into such URLs.

  URL                                   what it returns
  /                                     the WEB SITE (login, dashboard, network, communities, users)
  /api                                  a clickable list of all endpoints
  /api/community_links                  number of friendships between every pair of communities
  /api/health                           is the server alive, how many users
  /api/stats                            headline numbers (users, friendships, density, communities ...)
  /api/users?community=C1&interest=Tech&city=Jaipur&q=ira&sort=degree&limit=20&offset=0
  /api/users/<user_id>                  one profile + community + recent posts
  /api/users/<user_id>/friends          the user's friends
  /api/users/<user_id>/suggestions      "people you may know" (friends of friends, ranked by mutual friends)
  /api/network?community=C1&min_degree=5&limit=300   nodes + links for drawing the graph
  POST /api/predict                     new user's profile -> predicted community + people to follow (changes nothing)
  POST /api/users                       create the new user in the database (+ chosen connections)
  /api/meta                             allowed cities, interests, hashtags for the sign-up form
  /api/spread?strategy=top degree&k=5&p=0.12   one simulated spread (rounds) to animate
  /api/spread/compare, /api/spread/containment   marketing and fake-news experiments
  /api/communities                      all communities with their statistics
  /api/communities/<id>                 one community: stats, top users, top hashtags, links to other communities
  /api/posts?user=U0040&community=C1&hashtag=%23AI&limit=20
  /api/hashtags?community=C1            most used hashtags (for a word cloud)

Input : data/social.db  (Stage 5)
Run   : press the Run triangle in VS Code. Your browser opens http://127.0.0.1:5000 by itself (add --no-open to stop that). Stop with Ctrl+C.
        or:  /usr/local/bin/python3 stage6_api.py
Needs : pip install flask
"""
# %% 0. Setup
from pathlib import Path
import sqlite3
import sys
import threading
import webbrowser
import stage9_recommender as rec
import stage10_spread as spr
from flask import Flask, jsonify, request, g, abort, send_from_directory

BASE = Path(__file__).resolve().parent
DB = BASE / "data" / "social.db"
if not DB.exists() and (BASE / "social.db").exists():
    DB = BASE / "social.db"
if not DB.exists():
    raise SystemExit("data/social.db not found. Run stage5_database.py first.")

try:                                              # the web pages live in stage7_frontend.py; write them to frontend/ if missing or old
    import stage7_frontend
    FRONTEND = stage7_frontend.write_frontend(BASE)
except ImportError:
    FRONTEND = BASE / "frontend"
app = Flask(__name__, static_folder=str(FRONTEND), static_url_path="/static")
app.json.sort_keys = False                       # keep column order in the JSON


def db():
    """One read-only database connection per request. mode=ro means the API can never change the data."""
    if "db" not in g:
        g.db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        g.db.row_factory = sqlite3.Row           # rows behave like dictionaries
    return g.db


@app.teardown_appcontext
def close_db(_):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


@app.after_request
def allow_browser_pages(resp):
    """CORS: lets a web page opened from another place (Stage 7) call this API."""
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


def rows(sql, params=()):
    return [dict(r) for r in db().execute(sql, params).fetchall()]


def one(sql, params=()):
    r = db().execute(sql, params).fetchone()
    return dict(r) if r else None


def int_arg(name, default, lo, hi):
    """Read ?name=5 from the URL, keep it inside [lo, hi]. Bad input gives a clear 400 error, not a crash."""
    try:
        v = int(request.args.get(name, default))
    except ValueError:
        abort(400, description=f"'{name}' must be a whole number")
    return max(lo, min(hi, v))


def user_or_404(user_id):
    u = one("SELECT * FROM users WHERE user_id = ?", (user_id,))
    if u is None:
        abort(404, description=f"user '{user_id}' does not exist")
    return u


@app.errorhandler(400)
@app.errorhandler(404)
def json_error(e):
    return jsonify(error=e.description, status=e.code), e.code


@app.errorhandler(rec.ValidationError)
def bad_input(e):
    return jsonify(error="; ".join(e.errors), errors=e.errors, status=400), 400


def json_body():
    """The JSON sent by the browser. Must be an object; anything else is a clear 400 error."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, description="send a JSON object with Content-Type: application/json")
    return data


# %% 1. Web site (Stage 7/8) and API index
@app.get("/")
def site():
    """The web page. It lives in frontend/ and calls the /api/... URLs below from the browser."""
    if not (FRONTEND / "index.html").exists():
        return "frontend/index.html not found. Keep the frontend folder next to this file.", 404
    return send_from_directory(FRONTEND, "index.html")


@app.get("/api")
def home():
    links = [
        ("/api/health", "server status"), ("/api/stats", "headline numbers"),
        ("/api/communities", "all communities"), ("/api/communities/C1", "one community"),
        ("/api/users?limit=10&sort=degree", "10 most connected users"), ("/api/users/U0040", "one user (profile + posts)"),
        ("/api/users/U0040/friends?limit=10", "friends of a user"), ("/api/users/U0338/suggestions", "people you may know"),
        ("/api/network?min_degree=15", "graph data (nodes + links), users with 15+ friends"),
        ("/api/posts?community=C1&limit=5", "posts of one community"), ("/api/hashtags?community=C2", "top hashtags of one community"),
    ]
    li = "".join(f'<li><a href="{u}">{u}</a> &nbsp; <span style="color:#666">{d}</span></li>' for u, d in links)
    return (f"<!doctype html><title>Social graph API</title><body style='font-family:system-ui;max-width:760px;margin:40px auto'>"
            f"<h2>Social network API</h2><p>Click a link to see the JSON the server returns.</p><ul style='line-height:1.9'>{li}</ul></body>")


@app.get("/api/health")
def health():
    return jsonify(status="ok", users=one("SELECT COUNT(*) AS n FROM users")["n"])


@app.get("/api/stats")
def stats():
    n = one("SELECT COUNT(*) AS n FROM users")["n"]
    m = one("SELECT COUNT(*) AS n FROM connections")["n"]
    return jsonify(
        users=n, friendships=m, posts=one("SELECT COUNT(*) AS n FROM posts")["n"],
        communities=one("SELECT COUNT(*) AS n FROM communities WHERE community_id <> 'Isolated'")["n"],
        isolated_users=one("SELECT COUNT(*) AS n FROM users WHERE degree = 0")["n"],
        density=round(2 * m / (n * (n - 1)), 5), average_degree=round(2 * m / n, 2),
        max_degree=one("SELECT MAX(degree) AS d FROM users")["d"],
        share_friendships_inside_communities=round(one(
            """SELECT 1.0 * SUM(a.community_id = b.community_id) / COUNT(*) AS s FROM connections c
               JOIN users a ON a.user_id = c.user_id_1 JOIN users b ON b.user_id = c.user_id_2""")["s"], 3))


# %% 2. Users
@app.get("/api/users")
def users():
    where, params = [], []
    for arg, col in [("community", "community_id"), ("interest", "interest"), ("city", "city"), ("account_type", "account_type")]:
        if request.args.get(arg):
            where.append(f"{col} = ?"); params.append(request.args[arg])        # ? placeholders: safe against SQL injection
    if request.args.get("q"):
        where.append("(username LIKE ? OR full_name LIKE ?)"); params += [f"%{request.args['q']}%"] * 2
    sort = {"degree": "degree DESC", "name": "full_name", "age": "age", "joined": "joined_date"}.get(request.args.get("sort", "degree"), "degree DESC")
    limit, offset = int_arg("limit", 50, 1, 500), int_arg("offset", 0, 0, 10**6)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    total = one(f"SELECT COUNT(*) AS n FROM users {clause}", params)["n"]
    data = rows(f"""SELECT user_id, username, full_name, age, city, interest, account_type, is_verified, community_id, degree
                    FROM users {clause} ORDER BY {sort}, user_id LIMIT ? OFFSET ?""", params + [limit, offset])
    return jsonify(total=total, limit=limit, offset=offset, users=data)


@app.get("/api/users/<user_id>")
def user(user_id):
    u = user_or_404(user_id)
    u["recent_posts"] = rows("SELECT post_id, posted_at, text, hashtags, likes, shares, comments FROM posts WHERE user_id = ? ORDER BY posted_at DESC LIMIT 5", (user_id,))
    u["post_count"] = one("SELECT COUNT(*) AS n FROM posts WHERE user_id = ?", (user_id,))["n"]
    u["friends_in_own_community"] = u["degree"] - u["friends_outside_community"]
    return jsonify(u)


@app.get("/api/users/<user_id>/friends")
def friends(user_id):
    user_or_404(user_id)
    limit, offset = int_arg("limit", 50, 1, 500), int_arg("offset", 0, 0, 10**6)
    data = rows("""SELECT u.user_id, u.username, u.full_name, u.interest, u.community_id, u.degree, c.connected_on
                   FROM connections c JOIN users u ON u.user_id = CASE WHEN c.user_id_1 = ? THEN c.user_id_2 ELSE c.user_id_1 END
                   WHERE ? IN (c.user_id_1, c.user_id_2) ORDER BY u.degree DESC, u.user_id LIMIT ? OFFSET ?""",
                (user_id, user_id, limit, offset))
    return jsonify(user_id=user_id, total=one("SELECT degree AS d FROM users WHERE user_id = ?", (user_id,))["d"], friends=data)


@app.get("/api/users/<user_id>/suggestions")
def suggestions(user_id):
    user_or_404(user_id)
    limit = int_arg("limit", 5, 1, 50)
    data = rows("""SELECT u.user_id, u.username, u.interest, u.community_id, COUNT(*) AS mutual_friends
                   FROM friendships a JOIN friendships b ON b.user_id = a.friend_id JOIN users u ON u.user_id = b.friend_id
                   WHERE a.user_id = ? AND b.friend_id <> a.user_id
                     AND b.friend_id NOT IN (SELECT friend_id FROM friendships WHERE user_id = ?)
                   GROUP BY b.friend_id ORDER BY mutual_friends DESC, u.degree DESC, u.user_id LIMIT ?""", (user_id, user_id, limit))
    return jsonify(user_id=user_id, suggestions=data)


# %% 3. Network (what the graph drawing needs)
@app.get("/api/network")
def network():
    """Nodes + links. Filters keep the picture readable: only one community, only users with min_degree+ friends,
    at most `limit` users (the most connected ones are kept). Links are returned only when BOTH ends are in the node list."""
    where, params = [], []
    if request.args.get("community"):
        where.append("community_id = ?"); params.append(request.args["community"])
    min_degree = int_arg("min_degree", 0, 0, 10**4)
    where.append("degree >= ?"); params.append(min_degree)
    limit = int_arg("limit", 400, 1, 2000)
    nodes = rows(f"""SELECT user_id AS id, username, interest, community_id AS community, city, account_type, degree
                     FROM users WHERE {' AND '.join(where)} ORDER BY degree DESC, user_id LIMIT ?""", params + [limit])
    ids = [nd["id"] for nd in nodes]
    links = []
    if ids:
        ph = ",".join("?" * len(ids))
        links = rows(f"SELECT user_id_1 AS source, user_id_2 AS target, interaction_count AS weight FROM connections "
                     f"WHERE user_id_1 IN ({ph}) AND user_id_2 IN ({ph})", ids + ids)
    return jsonify(node_count=len(nodes), link_count=len(links), nodes=nodes, links=links)


# %% 4. Communities
@app.get("/api/communities")
def communities():
    return jsonify(communities=rows("SELECT * FROM communities ORDER BY users DESC"))


@app.get("/api/communities/<cid>")
def community(cid):
    c = one("SELECT * FROM communities WHERE community_id = ?", (cid,))
    if c is None:
        abort(404, description=f"community '{cid}' does not exist")
    c["top_users"] = rows("SELECT user_id, username, city, degree FROM users WHERE community_id = ? ORDER BY degree DESC LIMIT 5", (cid,))
    c["top_hashtags"] = rows("""SELECT h.hashtag, COUNT(*) AS uses FROM post_hashtags h JOIN posts p ON p.post_id = h.post_id
                                JOIN users u ON u.user_id = p.user_id WHERE u.community_id = ? GROUP BY h.hashtag
                                ORDER BY uses DESC, h.hashtag LIMIT 5""", (cid,))
    c["links_to_other_communities"] = rows("""SELECT CASE WHEN a.community_id = ? THEN b.community_id ELSE a.community_id END AS other_community,
                                              COUNT(*) AS friendships
                                              FROM connections c JOIN users a ON a.user_id = c.user_id_1 JOIN users b ON b.user_id = c.user_id_2
                                              WHERE (a.community_id = ? OR b.community_id = ?) AND a.community_id <> b.community_id
                                              GROUP BY other_community ORDER BY friendships DESC""", (cid, cid, cid))
    return jsonify(c)


@app.get("/api/community_links")
def community_links():
    return jsonify(links=rows("""SELECT a.community_id AS a, b.community_id AS b, COUNT(*) AS friendships
                                 FROM connections c JOIN users a ON a.user_id = c.user_id_1 JOIN users b ON b.user_id = c.user_id_2
                                 WHERE a.community_id <> 'Isolated' AND b.community_id <> 'Isolated'
                                 GROUP BY a.community_id, b.community_id"""))


# %% 4b. Join the network (Stage 9): predict community, recommend people, create the user
@app.get("/api/meta")
def meta():
    """Lists the form needs: allowed cities / interests / account types and the hashtags of every interest."""
    m = rec.get_model()
    per = {}                                            # the 7 hashtags each interest group uses most
    for r in rows("""SELECT u.interest, h.hashtag, COUNT(*) AS n FROM post_hashtags h JOIN posts p ON p.post_id = h.post_id
                     JOIN users u ON u.user_id = p.user_id GROUP BY 1, 2 ORDER BY 1, 3 DESC"""):
        if len(per.setdefault(r["interest"], [])) < 7:
            per[r["interest"]].append(r["hashtag"])
    return jsonify(cities=m.cities, interests=m.interests, account_types=m.types, hashtags_by_interest=per,
                   max_hashtags=rec.MAX_TAGS, max_friends=rec.MAX_FRIENDS, communities=[c for c in m.comms])


@app.get("/api/username_available")
def username_available():
    u = request.args.get("u", "").strip().lower()
    return jsonify(username=u, available=bool(u) and one("SELECT 1 AS x FROM users WHERE username = ?", (u,)) is None)


@app.post("/api/predict")
def predict():
    """Does NOT change the database. Returns the predicted community, probabilities, reasons and people to connect with."""
    return jsonify(rec.predict(db(), json_body()))


@app.post("/api/users")
def create_user():
    """Creates the user and the chosen connections, updates degrees and community statistics (one transaction)."""
    result = rec.create_user(json_body())
    return jsonify(result), 201


# %% 4c. Information flow (Stage 10)
def float_arg(name, default, lo, hi):
    try:
        v = float(request.args.get(name, default))
    except ValueError:
        abort(400, description=f"'{name}' must be a number")
    return max(lo, min(hi, v))


@app.get("/api/spread")
def spread():
    """One simulated cascade for the web page to animate. ?strategy=top degree&k=5&p=0.12  or  ?seeds=U0040,U0254&p=0.12"""
    adj, meta = spr.load_graph(db())
    p, k = float_arg("p", 0.12, 0.01, 0.6), int_arg("k", 5, 1, 20)
    if request.args.get("seeds"):
        seeds = list(dict.fromkeys(x.strip() for x in request.args["seeds"].split(",") if x.strip()))[:20]
        bad = [x for x in seeds if x not in adj]
        if bad:
            abort(400, description=f"unknown user(s): {', '.join(bad)}")
    else:
        strategy = request.args.get("strategy", "top degree")
        if strategy not in spr.STRATEGIES:
            abort(400, description="strategy must be one of: " + ", ".join(spr.STRATEGIES))
        seeds = spr.pick_seeds(strategy, k, meta, __import__("random").Random(request.args.get("seed", 0)))
    res = spr.simulate_once(adj, meta, seeds, p, seed=request.args.get("seed"))
    res.update(seeds=[{"user_id": s, "username": meta[s]["username"], "community": meta[s]["community"]} for s in seeds], p=p)
    return jsonify(res)


@app.get("/api/spread/compare")
def spread_compare():
    adj, meta = spr.load_graph(db())
    k, p, trials = int_arg("k", 5, 1, 20), float_arg("p", 0.12, 0.01, 0.6), int_arg("trials", 100, 20, 300)
    return jsonify(k=k, p=p, trials=trials, strategies=spr.compare_strategies(adj, meta, k, p, trials),
                   descriptions=spr.STRATEGIES)


@app.get("/api/spread/containment")
def spread_containment():
    adj, meta = spr.load_graph(db())
    p, trials = float_arg("p", 0.12, 0.01, 0.6), int_arg("trials", 100, 20, 300)
    ks, res = spr.containment(adj, meta, (0, 5, 10, 20, 40), p, trials)
    return jsonify(p=p, trials=trials, blocked=ks, average_reach=res)


# %% 5. Posts and hashtags
@app.get("/api/posts")
def posts():
    where, params = [], []
    if request.args.get("user"):
        where.append("p.user_id = ?"); params.append(request.args["user"])
    if request.args.get("community"):
        where.append("u.community_id = ?"); params.append(request.args["community"])
    if request.args.get("hashtag"):
        where.append("p.post_id IN (SELECT post_id FROM post_hashtags WHERE hashtag = ?)"); params.append(request.args["hashtag"])
    limit, offset = int_arg("limit", 20, 1, 200), int_arg("offset", 0, 0, 10**6)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    total = one(f"SELECT COUNT(*) AS n FROM posts p JOIN users u ON u.user_id = p.user_id {clause}", params)["n"]
    data = rows(f"""SELECT p.post_id, p.user_id, u.username, u.community_id, p.posted_at, p.text, p.hashtags, p.likes, p.shares, p.comments
                    FROM posts p JOIN users u ON u.user_id = p.user_id {clause} ORDER BY p.posted_at DESC LIMIT ? OFFSET ?""", params + [limit, offset])
    return jsonify(total=total, limit=limit, offset=offset, posts=data)


@app.get("/api/hashtags")
def hashtags():
    params, extra = [], ""
    if request.args.get("community"):
        extra = "WHERE u.community_id = ?"; params.append(request.args["community"])
    limit = int_arg("limit", 20, 1, 100)
    return jsonify(hashtags=rows(f"""SELECT h.hashtag, COUNT(*) AS uses FROM post_hashtags h JOIN posts p ON p.post_id = h.post_id
                                     JOIN users u ON u.user_id = p.user_id {extra} GROUP BY h.hashtag ORDER BY uses DESC, h.hashtag LIMIT ?""",
                                  params + [limit]))


# %% 6. Start the server
if __name__ == "__main__":
    print("Web site + API running.  Open  http://127.0.0.1:5000  in your browser (it opens by itself).   Stop with Ctrl+C")
    if "--no-open" not in sys.argv:
        threading.Timer(1.2, lambda: webbrowser.open("http://127.0.0.1:5000")).start()
    app.run(host="127.0.0.1", port=5000, debug=False)
