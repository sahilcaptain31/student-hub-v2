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
    # Leaderboard data
    leaders = list(db.users.find({}, {"_id": 0, "username": 1, "level": 1}).sort([("level", -1), ("xp", -1)]).limit(5))
    
    # User data fetch karna zaroori hai template ke liye
    user_data = None
    if "user" in session:
        user_data = db.users.find_one({"username": session["user"]})
        
    return render_template("index.html", leaders=leaders, user=user_data)

# Default Avatar Links
BOY_AVATAR = "https://raw.githubusercontent.com/Arunanshu/Student-Hub-Assets/main/boy_avatar.jpg"
GIRL_AVATAR = "https://raw.githubusercontent.com/Arunanshu/Student-Hub-Assets/main/girl_avatar.jpg"

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]
        gender = request.form.get("gender", "male")
        secret_input = request.form.get("admin_secret", "")
        
        MASTER_ADMIN_CODE = os.getenv("ADMIN_CODE") 
        role = 'admin' if MASTER_ADMIN_CODE and secret_input == MASTER_ADMIN_CODE else 'user'
        
        avatar_url = BOY_AVATAR if gender == "male" else GIRL_AVATAR
        
        if db.users.find_one({"username": u}):
            return "Username Already Exists!"
        
        # Initial Mission Data
        # app.py register route snippet
        default_tasks = [
            {"id": 1, "title": "Neural Link Established", "status": "completed", "xp": 10},
            {"id": 2, "title": "Complete First Mission", "status": "pending", "xp": 50},
            {"id": 3, "title": "Reach Level 10", "status": "pending", "xp": 100}
        ]
        
        db.users.insert_one({
            "username": u, 
            "password": p, 
            "role": role, 
            "level": 1, 
            "xp": 0,
            "gender": gender,
            "avatar": avatar_url,
            "tasks": default_tasks,
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
        # Database mein level aur xp update ho raha hai
        db.users.update_one(
            {"username": session["user"]}, 
            {"$set": {
                "level": int(data.get('level', 1)), 
                "xp": int(data.get('xp', 0))
            }}
        )
        return jsonify({"status": "synced", "level": data.get('level')})
    return jsonify({"status": "error", "message": "Unauthorized"}), 401

# --- CONTENT ROUTES ---

@app.route("/notes")
def notes():
    items = list(db.notes.find())
    return render_template("notes.html", items=items)

@app.route("/pyq")
def pyq():
    items = list(db.pyq.find())
    # Grouping Logic: Folder ke naam se items ko ikatha karna
    folders = {}
    for item in items:
        f_name = item.get('folder', 'General Resources')
        if f_name not in folders:
            folders[f_name] = []
        folders[f_name].append(item)
    
    return render_template("pyq.html", folders=folders)

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
    # Leaderboard rank nikalne ke liye
    all_users = list(db.users.find().sort([("level", -1), ("xp", -1)]))
    rank = next((i + 1 for i, u in enumerate(all_users) if u["username"] == session["user"]), "N/A")
    
    return render_template("profile.html", user=user_data, rank=rank)

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
    # Double check security
    if session.get("role") != "admin": 
        return "<h1>403: ACCESS DENIED</h1><p>You do not have ROOT privileges.</p>", 403
    
    # Fetch data for admin to manage
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
        # Naya Folder Name field
        folder_name = request.form.get("folder_name", "General Resources")
        
        if file_url:
            db[doc_type].insert_one({
                "subject": subj, 
                "folder": folder_name, # Folder data database mein jayega
                "url": file_url,
                "created_at": datetime.utcnow()
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

@app.route("/bunk-meter")
def bunk_meter():
    return render_template("tools.html")

# Essential for Vercel
app = app