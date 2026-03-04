from flask import Flask, render_template, request, redirect, session, jsonify, Response
from pymongo import MongoClient
import os
from bson.objectid import ObjectId

# Vercel structure
app = Flask(__name__, template_folder='../templates', static_folder='../static')

# SECURITY
app.secret_key = os.getenv("SECRET_KEY", "dev_secret_key_123")

# MONGODB CONNECTION
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client.student_hub_db

# --- ROUTES ---

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
        db.users.insert_one({"username": u, "password": p, "role": role, "level": 1, "xp": 0})
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

# --- CONTENT ROUTES ---

@app.route("/notes")
def notes():
    items = list(db.notes.find())
    return render_template("notes.html", items=items)

@app.route("/pyq")
def pyq():
    items = list(db.pyq.find())
    return render_template("pyq.html", items=items)

# --- ADMIN & UPLOAD (UPDATED FOR URL) ---

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
        file_url = request.form["file_url"] # Direct link from Drive/Cloudinary
        
        if file_url:
            db[doc_type].insert_one({
                "subject": subj, 
                "url": file_url # Filename ki jagah URL save ho raha hai
            })
    return redirect("/admin")

@app.route("/delete/<doc_type>/<id>")
def delete_item(doc_type, id):
    if session.get("role") == "admin":
        db[doc_type].delete_one({"_id": ObjectId(id)})
    return redirect("/admin")

# --- SEO & PAGES ---

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

app = app