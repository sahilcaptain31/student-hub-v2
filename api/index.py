from flask import Flask, render_template, request, redirect, session, jsonify, Response
from pymongo import MongoClient
import os
from bson.objectid import ObjectId
import sqlite3

# Vercel structure: templates aur static folders root mein hain
app = Flask(__name__, template_folder='../templates', static_folder='../static')

# SECURITY: Secret key for session management
app.secret_key = os.getenv("SECRET_KEY", "dev_secret_key_123")


app.config.update(
    SESSION_COOKIE_NAME='session',
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=True,    # Vercel HTTPS use karta hai toh isse True rakho
    SESSION_COOKIE_HTTPONLY=True,
    PERMANENT_SESSION_LIFETIME=600 # 10 minutes tak session rahega
)

# MONGODB CONNECTION
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client.student_hub_db

# --- MAIN ROUTES ---

@app.route("/")
def home():
    # Leaderboard ke liye top 5 users
    leaders = list(db.users.find({}, {"_id": 0, "username": 1, "level": 1}).sort([("level", -1), ("xp", -1)]).limit(5))
    return render_template("index.html", leaders=leaders)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        u, p = request.form["username"], request.form["password"]
        secret_input = request.form.get("admin_secret", "")
        
        # Admin check via environment variable
        MASTER_ADMIN_CODE = os.getenv("ADMIN_CODE") 
        role = 'admin' if MASTER_ADMIN_CODE and secret_input == MASTER_ADMIN_CODE else 'user'
        
        if db.users.find_one({"username": u}):
            return "Username Already Exists!"
        
        db.users.insert_one({
            "username": u, 
            "password": p, 
            "role": role, 
            "level": 1, 
            "xp": 0
        })
        return redirect("/login")
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u, p = request.form["username"], request.form["password"]
        user = db.users.find_one({"username": u, "password": p})
        if user:
            session.permanent = True # <-- YE LINE ADD KARO
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

# --- DASHBOARD CONTENT ROUTES (Ye buttons ko activate karenge) ---

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
    # Isse CGPA, Bunk Meter, aur Focus Timer kaam karne lagenge
    return render_template("tools.html")

@app.route("/schedule")
def schedule():
    # Isse Study Planner aur Exam Countdown khulega
    return render_template("schedule.html")

@app.route("/profile")
def profile():
    if "user" not in session: return redirect("/login")
    user_data = db.users.find_one({"username": session["user"]})
    return render_template("profile.html", user=user_data)

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

# --- SEO & FOOTER PAGES ---

@app.route('/sitemap.xml')
def sitemap():
    pages = [
        "https://student-hub-v2.vercel.app/",
        "https://student-hub-v2.vercel.app/notes",
        "https://student-hub-v2.vercel.app/pyq",
        "https://student-hub-v2.vercel.app/about",
        "https://student-hub-v2.vercel.app/contact",
        "https://student-hub-v2.vercel.app/privacy"
    ]
    xml = '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    for page in pages:
        xml += f'<url><loc>{page}</loc><changefreq>daily</changefreq></url>'
    xml += '</urlset>'
    return Response(xml, mimetype='application/xml')

@app.route('/about')
def about(): return render_template('about.html')

@app.route('/privacy')
def privacy(): return render_template('privacy.html')

@app.route('/contact')
def contact(): return render_template('contact.html')




# --- PHASE 5: FORUM BACKEND (MONGODB) ---

@app.route('/forum')
def forum():
    # Database se saare posts nikaalo (Latest posts sabse upar)
    # yahan hum 'forum_posts' collection use kar rahe hain
    posts = list(db.forum_posts.find().sort("_id", -1))
    return render_template('forum.html', posts=posts)

@app.route('/post_doubt', methods=['POST'])
def post_doubt():
    user = session.get('user') # Safer way to get session
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    
    
    data = request.json
    if not data or 'content' not in data:
        return jsonify({"error": "Invalid Data"}), 400

    # User ka current data nikalna (Level ke liye)
    user_data = db.users.find_one({"username": session["user"]})
    
    # MongoDB mein entry daalna
    db.forum_posts.insert_one({
        "username": session["user"],
        "user_level": user_data.get('level', 1) if user_data else 1,
        "content": data['content'],
        "timestamp": ObjectId().get_generation_time() # Automatic time
    })
    
    # XP Update logic inside post_doubt route
    db.users.update_one(
        {"username": session["user"]},
        {"$inc": {"xp": 10}} # 10 XP increase karega database mein
    )
    
    return jsonify({"success": True})

# --- PHASE 4: PREDICTOR ROUTE ---
@app.route('/predictor')
def predictor():
    return render_template('predictor.html')


# Essential for Vercel deployment
app = app