# Lost & Found Campus - Single Page Edition

This is a **simplified** version of the project made specifically to be easy to
explain (e.g. in a viva or presentation). Same features, much less Python code.

## What changed from the original version

| | Original | Single Page Edition |
|---|---|---|
| HTML pages | 13 separate templates | **1** template (`index.html`) |
| Backend style | Renders full HTML pages | Sends small **JSON** responses |
| app.py length | ~500 lines | **~200 lines** |
| Navigation | Browser reloads a new page each click | JavaScript shows/hides sections — no reload |

## How to run it

```bash
pip install -r requirements.txt
python app.py
```
Open `http://127.0.0.1:5000`. Default admin: `admin@campus.edu` / `admin123`.

## How to explain `app.py` (walkthrough order)

1. **Database setup (`init_db`)** — same 3 tables as before: `users`, `items`, `claims`.
   Creates them automatically and seeds one admin account.

2. **`db()` / `close_db()`** — opens one SQLite connection per request, closes it
   when the request finishes. Standard Flask pattern.

3. **`login_required` / `admin_required`** — decorators. Any route wrapped with
   `@login_required` checks `session["user_id"]` exists before running; if not,
   it returns a JSON error instead of the page.

4. **`save_image()`** — checks the uploaded file is jpg/jpeg/png, saves it with a
   unique filename so two students uploading "photo.jpg" don't overwrite each other.

5. **Routes** — this is the shortest part to explain, because **every route just
   does 3 things**:
   - Read data from the request (`request.form`, `request.args`)
   - Run one SQL query
   - Return `jsonify(...)`

   For example, `login()`:
   ```python
   @app.route("/api/login", methods=["POST"])
   def login():
       d = request.form
       user = db().execute("SELECT * FROM users WHERE email=?", (d["email"],)).fetchone()
       if not user or not check_password_hash(user["password"], d["password"]):
           return jsonify(error="Invalid email or password"), 401
       session["user_id"], session["name"], session["role"] = user["id"], user["name"], user["role"]
       return jsonify(name=user["name"], role=user["role"])
   ```
   It checks the password hash, and if correct, stores the user's ID in the
   **session** (a cookie) so future requests know who's logged in.

6. **No template rendering logic** — because there's only one template
   (`index.html`), `app.py` never needs to decide *which page* to show. It just
   answers "what's the data?" and JavaScript in the browser decides what to display.

## How to explain `templates/index.html`

This single file contains **every screen** as a hidden `<div>`:
```html
<section id="home" class="section active">...</section>
<section id="login" class="section">...</section>
<section id="search" class="section">...</section>
...
```

Only one has the `active` class at a time (shown via CSS: `.section{display:none} .section.active{display:block}`).

The JavaScript function `showSection(id)` is the core idea of the whole page:
```javascript
function showSection(id){
  document.querySelectorAll(".section").forEach(s => s.classList.remove("active"));
  document.getElementById(id).classList.add("active");
}
```
It hides every section, then shows only the one requested — that's the entire
"page navigation" logic, no server involved.

Every button (Login, Report Lost, Search, etc.) calls a JavaScript function that:
1. Uses `fetch()` to call one of the `/api/...` routes in `app.py`
2. Gets back JSON data
3. Builds HTML from that data and drops it into the page

Example — loading the homepage stats:
```javascript
async function loadHome(){
  const stats = await (await fetch("/api/stats")).json();
  statLost.textContent = stats.lost;
  statFound.textContent = stats.found;
  ...
}
```

## The status workflow (unchanged)

```
Lost item reported   -> status: Lost
Found item reported  -> status: Found
     someone clicks Claim
         -> status: Claim Pending
     Admin approves -> status: Returned
     Admin rejects  -> status: Found (available again)
```

## Suggested viva talking points

- "I used **sessions** (cookies) to keep users logged in between requests."
- "Passwords are **hashed** with Werkzeug — never stored as plain text."
- "The backend is a small **REST API** — it only returns JSON, never HTML."
- "The frontend is a **single-page app (SPA)** — JavaScript swaps visible
  sections instead of reloading the browser, which feels faster."
- "A student can't claim their own found-item report — that check is done in
  `submit_claim()` on the server, not just hidden in the UI, so it can't be bypassed."
