"""
Lost & Found Campus - SIMPLE SINGLE PAGE VERSION
--------------------------------------------------
Everything the browser sees is ONE page (templates/index.html).
This file only stores/reads data and sends it back as JSON.
Run:  python app.py   then open  http://127.0.0.1:5000
"""

import os, sqlite3
from datetime import datetime
from functools import wraps
from flask import Flask, request, session, jsonify, render_template, send_from_directory, g
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "campus-secret-key"

DB = os.path.join(os.path.dirname(__file__), "database.db")
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ---------- Database ----------
def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(e=None):
    d = g.pop("db", None)
    if d:
        d.close()


def init_db():
    conn = sqlite3.connect(DB)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT UNIQUE,
        password TEXT, role TEXT DEFAULT 'student', created_at TEXT);
    CREATE TABLE IF NOT EXISTS items(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, item_name TEXT,
        category TEXT, description TEXT, image TEXT, location TEXT, date TEXT,
        type TEXT, status TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS claims(
        id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER, user_id INTEGER,
        reason TEXT, proof TEXT, status TEXT DEFAULT 'Pending', created_at TEXT);
    """)
    if not conn.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
        conn.execute("INSERT INTO users(name,email,password,role,created_at) VALUES(?,?,?,?,?)",
                      ("Admin", "admin@campus.edu", generate_password_hash("admin123"),
                       "admin", str(datetime.now())))
    conn.commit()
    conn.close()


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def row_to_dict(row):
    return dict(row) if row else None


# ---------- Auth helpers ----------
def login_required(f):
    @wraps(f)
    def wrap(*a, **k):
        if "user_id" not in session:
            return jsonify(error="Login required"), 401
        return f(*a, **k)
    return wrap


def admin_required(f):
    @wraps(f)
    def wrap(*a, **k):
        if session.get("role") != "admin":
            return jsonify(error="Admin only"), 403
        return f(*a, **k)
    return wrap


def save_image(file):
    """Save an uploaded image if valid; return filename or None."""
    if not file or file.filename == "":
        return None
    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in ("jpg", "jpeg", "png"):
        return None
    name = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{secure_filename(file.filename)}"
    file.save(os.path.join(UPLOAD_DIR, name))
    return name


# ---------- Page + uploads ----------
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/uploads/<name>")
def uploaded(name):
    return send_from_directory(UPLOAD_DIR, name)


# ---------- Auth API ----------
@app.route("/api/register", methods=["POST"])
def register():
    d = request.form
    if d["password"] != d["confirm_password"]:
        return jsonify(error="Passwords do not match"), 400
    if db().execute("SELECT 1 FROM users WHERE email=?", (d["email"],)).fetchone():
        return jsonify(error="Email already registered"), 400
    db().execute("INSERT INTO users(name,email,password,role,created_at) VALUES(?,?,?,?,?)",
                 (d["name"], d["email"], generate_password_hash(d["password"]), "student", now()))
    db().commit()
    return jsonify(message="Registered! Please login.")


@app.route("/api/login", methods=["POST"])
def login():
    d = request.form
    user = db().execute("SELECT * FROM users WHERE email=?", (d["email"],)).fetchone()
    if not user or not check_password_hash(user["password"], d["password"]):
        return jsonify(error="Invalid email or password"), 401
    session["user_id"], session["name"], session["role"] = user["id"], user["name"], user["role"]
    return jsonify(name=user["name"], role=user["role"])


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify(message="Logged out")


@app.route("/api/session")
def who_am_i():
    if "user_id" in session:
        return jsonify(loggedIn=True, name=session["name"], role=session["role"])
    return jsonify(loggedIn=False)


# ---------- Items API ----------
@app.route("/api/items", methods=["GET", "POST"])
def items():
    if request.method == "POST":  # report lost or found item
        if "user_id" not in session:
            return jsonify(error="Login required"), 401
        d = request.form
        image = save_image(request.files.get("image"))
        status = d["type"]  # 'Lost' or 'Found'
        db().execute("""INSERT INTO items(user_id,item_name,category,description,image,
                        location,date,type,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                     (session["user_id"], d["item_name"], d["category"], d.get("description", ""),
                      image, d["location"], d["date"], d["type"], status, now()))
        db().commit()
        return jsonify(message="Item reported successfully")

    # GET -> search / list items, with optional filters
    q, params = "SELECT * FROM items WHERE 1=1", []
    for field in ("item_name", "category", "location", "type", "status"):
        val = request.args.get(field)
        if val:
            q += f" AND {field} LIKE ?" if field in ("item_name", "location") else f" AND {field}=?"
            params.append(f"%{val}%" if field in ("item_name", "location") else val)
    q += " ORDER BY created_at DESC"
    rows = db().execute(q, params).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/items/<int:item_id>")
def item_detail(item_id):
    row = db().execute("""SELECT items.*, users.name AS reporter_name FROM items
                           JOIN users ON items.user_id=users.id WHERE items.id=?""", (item_id,)).fetchone()
    return jsonify(dict(row)) if row else (jsonify(error="Not found"), 404)


@app.route("/api/stats")
def stats():
    d = db()
    def count(where):
        return d.execute(f"SELECT COUNT(*) c FROM {where}").fetchone()["c"]
    return jsonify(
        lost=count("items WHERE type='Lost'"),
        found=count("items WHERE type='Found'"),
        returned=count("items WHERE status='Returned'"),
        users=count("users WHERE role='student'"),
        pending_claims=count("claims WHERE status='Pending'"),
    )


@app.route("/api/my/items")
@login_required
def my_items():
    rows = db().execute("SELECT * FROM items WHERE user_id=? ORDER BY created_at DESC",
                         (session["user_id"],)).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/admin/items/<int:item_id>/delete", methods=["POST"])
@admin_required
def delete_item(item_id):
    db().execute("DELETE FROM claims WHERE item_id=?", (item_id,))
    db().execute("DELETE FROM items WHERE id=?", (item_id,))
    db().commit()
    return jsonify(message="Deleted")


# ---------- Claims API ----------
@app.route("/api/claims", methods=["POST"])
@login_required
def submit_claim():
    d = request.form
    item = db().execute("SELECT * FROM items WHERE id=?", (d["item_id"],)).fetchone()
    if not item:
        return jsonify(error="Item not found"), 404
    if item["user_id"] == session["user_id"]:
        return jsonify(error="You cannot claim your own reported item"), 400
    if item["status"] != "Found":
        return jsonify(error="This item is not available for claiming"), 400

    db().execute("INSERT INTO claims(item_id,user_id,reason,proof,status,created_at) VALUES(?,?,?,?,?,?)",
                 (d["item_id"], session["user_id"], d["reason"], d.get("proof", ""), "Pending", now()))
    db().execute("UPDATE items SET status='Claim Pending' WHERE id=?", (d["item_id"],))
    db().commit()
    return jsonify(message="Claim submitted for admin review")


@app.route("/api/my/claims")
@login_required
def my_claims():
    rows = db().execute("""SELECT claims.*, items.item_name, items.location FROM claims
                            JOIN items ON claims.item_id=items.id
                            WHERE claims.user_id=? ORDER BY claims.created_at DESC""",
                         (session["user_id"],)).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/admin/claims")
@admin_required
def admin_claims():
    rows = db().execute("""SELECT claims.*, items.item_name, items.location,
                            users.name AS student_name, users.email AS student_email
                            FROM claims JOIN items ON claims.item_id=items.id
                            JOIN users ON claims.user_id=users.id
                            ORDER BY claims.created_at DESC""").fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/admin/claims/<int:claim_id>/<action>", methods=["POST"])
@admin_required
def decide_claim(claim_id, action):
    claim = db().execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()
    if not claim:
        return jsonify(error="Claim not found"), 404

    if action == "approve":
        db().execute("UPDATE claims SET status='Approved' WHERE id=?", (claim_id,))
        db().execute("UPDATE items SET status='Returned' WHERE id=?", (claim["item_id"],))
        db().execute("UPDATE claims SET status='Rejected' WHERE item_id=? AND id!=? AND status='Pending'",
                     (claim["item_id"], claim_id))
    elif action == "reject":
        db().execute("UPDATE claims SET status='Rejected' WHERE id=?", (claim_id,))
        db().execute("UPDATE items SET status='Found' WHERE id=?", (claim["item_id"],))
    else:
        return jsonify(error="Invalid action"), 400

    db().commit()
    return jsonify(message=f"Claim {action}d")


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
