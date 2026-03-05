from flask import Flask, render_template, request, redirect, session, jsonify, Response
from pymongo import MongoClient
import os
from bson.objectid import ObjectId
from datetime import datetime

# Vercel structure
app = Flask(__name__, template_folder='../templates', static_folder='../static')

# SECURITY: Secret key for session management
app.secret_key = os.getenv("SECRET_KEY", "dev_secret_key_123")

# VERCEL SESSION FIX: Cookie settings
app.config.update(
    SESSION_COOKIE_NAME='session',
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    PERMANENT_SESSION_LIFETIME=600
)

# MONGODB CONNECTION
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    print("CRITICAL: MONGO_URI not found in Environment Variables!")
client = MongoClient(MONGO_URI)
db = client.student_hub_db

# --- MAIN ROUTES ---

@app.route("/")
def home():
    leaders = list(db.users.find({}, {"_id": 0, "username": 1, "level": 1}).sort([("level", -1), ("xp", -1)]).limit(5))
    return render_template("index.html", leaders=leaders)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        u, p = request.form["username"], request.form["password"]
        secret_input = request.form.get("admin_secret", "")
        
        MASTER_ADMIN_CODE = os.getenv("ADMIN_CODE") 
        role = 'admin' if MASTER_ADMIN_CODE and secret_input == MASTER_ADMIN_CODE else 'user'
        
        if db.users.find_one({"username": u}):
            return "Username Already Exists!"
        
        db.users.insert_one({
            "username": u, 
            "password": p, 
            "role": role, 
            "level": 1, 
            "xp": 0,
            "joined_at": datetime.utcnow()
        })
        return redirect("/login")
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u, p = request.form["username"], request.form["password"]
        user = db.users.find_one({"username": u, "password": p})
        if user:
            session.permanent = True 
            session["user"] = user["username"]
            session["role"] = user["role"]
            return redirect("/")
        return "Wrong ID or Password!"
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/update_xp", methods=["POST"])
def update_xp():
    if "user" in session:
        data = request.json
        db.users.update_one(
            {"username": session["user"]}, 
            {"$set": {"level": data['level'], "xp": data['xp']}}
        )
        return jsonify({"status": "ok"})
    return jsonify({"status": "error", "message": "Unauthorized"}), 401

# --- CONTENT ROUTES ---

@app.route("/notes")
def notes():
    items = list(db.notes.find())
    return render_template("notes.html", items=items)

@app.route("/pyq")
def pyq():
    items = list(db.pyq.find())
    return render_template("pyq.html", items=items)

@app.route("/tools")
def tools():
    return render_template("tools.html")

@app.route("/schedule")
def schedule():
    return render_template("schedule.html")

@app.route("/profile")
def profile():
    if "user" not in session: return redirect("/login")
    user_data = db.users.find_one({"username": session["user"]})
    return render_template("profile.html", user=user_data)

# --- PHASE 5: FORUM SYSTEM ---

@app.route('/forum')
def forum():
    posts = list(db.forum_posts.find().sort("_id", -1))
    return render_template('forum.html', posts=posts)

@app.route('/post_doubt', methods=['POST'])
def post_doubt():
    data = request.json
    # Frontend se direct username uthana (Vercel session backup)
    username = data.get('username') or session.get('user')
    
    if not username or username == "None":
        return jsonify({"error": "Session Expired! Please login again."}), 401
    
    content = data.get('content')
    if not content or len(content.strip()) == 0:
        return jsonify({"error": "Content cannot be empty!"}), 400

    user_data = db.users.find_one({"username": username})
    current_lvl = user_data.get('level', 1) if user_data else 1
    
    # Entry in Forum
    db.forum_posts.insert_one({
        "username": username,
        "user_level": current_lvl,
        "content": content,
        "timestamp": datetime.utcnow()
    })
    
    # Give XP
    db.users.update_one(
        {"username": username},
        {"$inc": {"xp": 10}}
    )
    
    return jsonify({"success": True})

# --- ADMIN ROUTES ---

@app.route("/admin")
def admin():
    if session.get("role") != "admin": 
        return "403: Access Denied!", 403
    
    all_users = list(db.users.find())
    all_notes = list(db.notes.find())
    all_pyqs = list(db.pyq.find())
    return render_template("admin.html", users=all_users, notes=all_notes, pyqs=all_pyqs)

@app.route("/upload", methods=["POST"])
def upload():
    if session.get("role") == "admin":
        subj = request.form["subject"]
        doc_type = request.form["type"] 
        file_url = request.form["file_url"]
        
        if file_url:
            db[doc_type].insert_one({
                "subject": subj, 
                "url": file_url
            })
    return redirect("/admin")

@app.route("/delete/<doc_type>/<id>")
def delete_item(doc_type, id):
    if session.get("role") == "admin":
        db[doc_type].delete_one({"_id": ObjectId(id)})
    return redirect("/admin")


# --- REPLY SYSTEM ---
@app.route('/post_reply/<post_id>', methods=['POST'])
def post_reply(post_id):
    username = session.get('user')
    if not username:
        return jsonify({"error": "Login required"}), 401
    
    data = request.json
    reply_text = data.get('reply')
    
    if not reply_text:
        return jsonify({"error": "Reply cannot be empty"}), 400

    # Post update karke usme comment array mein data daalna
    db.forum_posts.update_one(
        {"_id": ObjectId(post_id)},
        {"$push": {
            "replies": {
                "username": username,
                "content": reply_text,
                "timestamp": datetime.utcnow()
            }
        }}
    )
    return jsonify({"success": True})

# --- ADMIN DELETE POST ---
@app.route('/delete_post/<post_id>')
def delete_post(post_id):
    if session.get("role") == "admin":
        db.forum_posts.delete_one({"_id": ObjectId(post_id)})
        return redirect('/forum')
    return "Unauthorized", 403

# --- UTILS ---

@app.route('/sitemap.xml')
def sitemap():
    pages = ["https://student-hub-v2.vercel.app/", "https://student-hub-v2.vercel.app/notes"]
    xml = '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    for page in pages:
        xml += f'<url><loc>{page}</loc></url>'
    xml += '</urlset>'
    return Response(xml, mimetype='application/xml')

@app.route('/predictor')
def predictor(): return render_template('predictor.html')

@app.route('/about')
def about(): return render_template('about.html')

@app.route('/privacy')
def privacy(): return render_template('privacy.html')

@app.route('/contact')
def contact(): return render_template('contact.html')

# Essential for Vercel
app = app