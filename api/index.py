from flask import Flask, render_template, request, redirect, session, jsonify
from pymongo import MongoClient
import os

# Vercel structure: templates aur static folders root mein hain
app = Flask(__name__, template_folder='../templates', static_folder='../static')

# SECURITY: Vercel Settings se secret key uthayega
app.secret_key = os.getenv("SECRET_KEY", "dev_secret_key_123")

# MONGODB CONNECTION
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client.student_hub_db

# --- ROUTES ---

@app.route("/")
def home():
    # Leaderboard ke liye top 5 users (level aur xp ke base par)
    leaders = list(db.users.find({}, {"_id": 0, "username": 1, "level": 1}).sort([("level", -1), ("xp", -1)]).limit(5))
    return render_template("index.html", leaders=leaders)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        u, p = request.form["username"], request.form["password"]
        secret_input = request.form.get("admin_secret", "")
        
        # Admin check
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
            session["user"] = user["username"]
            session["role"] = user["role"]
            return redirect("/")
        return "Wrong ID or Password!"
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/profile")
def profile():
    if "user" not in session: return redirect("/login")
    user_data = db.users.find_one({"username": session["user"]})
    return render_template("profile.html", user=user_data)

@app.route("/update_xp", methods=["POST"])
def update_xp():
    if "user" in session:
        data = request.json
        db.users.update_one(
            {"username": session["user"]}, 
            {"$set": {"level": data['level'], "xp": data['xp']}}
        )
    return jsonify({"status": "ok"})

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
        doc_type = request.form["type"] # 'notes' ya 'pyq'
        file = request.files["file"]
        
        if file:
            # MongoDB mein record save kar rahe hain
            # Note: Vercel files delete kar deta hai, isliye baad mein 
            # hum yahan Direct Link (Gdrive/Cloudinary) ka option daalenge.
            db[doc_type].insert_one({
                "subject": subj, 
                "filename": file.filename
            })
    return redirect("/admin")

# Required for Vercel
app = app