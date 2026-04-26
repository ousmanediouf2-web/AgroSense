"""
AgroSense — Backend Flask
Version cloud (Render + MongoDB Atlas)
"""
from flask import Flask, jsonify, request, send_from_directory, session, redirect
from flask_cors import CORS
from pymongo import MongoClient, ASCENDING, DESCENDING
from bson import ObjectId
from datetime import datetime, timedelta
from functools import wraps
import random, threading, time, os, hashlib, secrets

app = Flask(__name__, static_folder="static")
app.secret_key = os.getenv("SECRET_KEY", "agrosense_secret_2025_iot_secure")

# Config session pour HTTPS (Render)
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="None",
)

CORS(app, supports_credentials=True, origins="*")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")

# ── Connexion MongoDB lazy (ne bloque pas le démarrage) ──────
print(f"🔗 Connexion à MongoDB...")
client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=8000)
db            = client["agro_iot"]
users_col     = db["utilisateurs"]
parcelles_col = db["parcelles"]
capteurs_col  = db["capteurs"]
mesures_col   = db["mesures"]
print("✅ MongoDB client créé")

# ── AUTH ─────────────────────────────────────────────────────
def hash_pw(pw):
    return hashlib.sha256(f"agrosense_sel_2025_{pw}".encode()).hexdigest()

def login_required(f):
    @wraps(f)
    def dec(*args, **kwargs):
        if not session.get("user"):
            if request.path.startswith("/api/"): return jsonify({"error":"Non autorisé"}),401
            return redirect("/login")
        return f(*args, **kwargs)
    return dec

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def dec(*args, **kwargs):
            u = session.get("user")
            if not u:
                if request.path.startswith("/api/"): return jsonify({"error":"Non autorisé"}),401
                return redirect("/login")
            if u.get("role") not in roles:
                if request.path.startswith("/api/"): return jsonify({"error":"Accès refusé"}),403
                return redirect("/login")
            return f(*args, **kwargs)
        return dec
    return decorator

# ── INIT DB ──────────────────────────────────────────────────
def init_db():
    try:
        users_col.create_index("username", unique=True)
        parcelles_col.create_index([("agriculteur_id", ASCENDING)])
        capteurs_col.create_index([("parcelle_id", ASCENDING)])
        mesures_col.create_index([("capteur_id", ASCENDING), ("timestamp", DESCENDING)])
        mesures_col.create_index([("timestamp", DESCENDING)])

        ADMIN_PWD = "admin2025"
        admin_hash = hash_pw(ADMIN_PWD)
        if not users_col.find_one({"role": "admin"}):
            users_col.insert_one({"username":"admin","password":admin_hash,"role":"admin","nom":"Super Administrateur","statut":"actif","created_at":datetime.utcnow()})
            print(f"👑 Admin créé : admin / {ADMIN_PWD}")
        else:
            users_col.update_one({"role":"admin"}, {"$set":{"password":admin_hash,"statut":"actif"}})
            print(f"👑 Admin sync : admin / {ADMIN_PWD}")

        for ag in [{"username":"diallo","nom":"Mamadou Diallo","password":hash_pw("diallo123")},{"username":"sow","nom":"Fatoumata Sow","password":hash_pw("sow123")}]:
            if not users_col.find_one({"username": ag["username"]}):
                users_col.insert_one({**ag,"role":"agriculteur","statut":"actif","created_at":datetime.utcnow()})

        if not users_col.find_one({"username":"invite1"}):
            users_col.insert_one({"username":"invite1","nom":"Visiteur Test","password":hash_pw("invite"),"role":"invite","statut":"actif","created_at":datetime.utcnow()})

        _seed_demo()
        print("✅ Base initialisée.")
    except Exception as e:
        print(f"⚠️ init_db erreur : {e}")

def _seed_demo():
    for ag_username, parcelles_names in [("diallo",["Parcelle Nord","Parcelle Sud"]),("sow",["Champ Est"])]:
        ag = users_col.find_one({"username": ag_username})
        if not ag: continue
        ag_id = str(ag["_id"])
        if parcelles_col.count_documents({"agriculteur_id": ag_id}) > 0: continue
        for pname in parcelles_names:
            p = parcelles_col.insert_one({"nom":pname,"agriculteur_id":ag_id,"agriculteur_nom":ag["nom"],"superficie":round(random.uniform(1.5,5.0),1),"culture":random.choice(["Maïs","Arachide","Mil","Niébé"]),"created_at":datetime.utcnow()})
            pid = str(p.inserted_id)
            types = [{"type":"température","unite":"°C"},{"type":"humidité","unite":"%"},{"type":"pH sol","unite":"pH"},{"type":"pluviométrie","unite":"mm"},{"type":"vitesse vent","unite":"km/h"},{"type":"luminosité","unite":"lux"},{"type":"pression","unite":"hPa"}]
            for tc in types:
                cid = f"CAP-{ag_username[:3].upper()}-{pname[:3].upper()}-{tc['type'][:4].upper()}"
                capteurs_col.insert_one({"capteur_id":cid,"parcelle_id":pid,"parcelle_nom":pname,"agriculteur_id":ag_id,"type":tc["type"],"unite":tc["unite"],"actif":True,"created_at":datetime.utcnow()})
                now = datetime.utcnow()
                batch = [{"capteur_id":cid,"parcelle_id":pid,"parcelle_nom":pname,"agriculteur_id":ag_id,"type":tc["type"],"valeur":round(_gen(tc["type"],now-timedelta(hours=h,minutes=m)),2),"unite":tc["unite"],"timestamp":now-timedelta(hours=h,minutes=m)} for h in range(48,0,-1) for m in [0,30]]
                mesures_col.insert_many(batch)
    print("🌱 Données démo OK")

def _gen(t, ts):
    h = ts.hour
    if t == "température": return 24+8*(1-abs(h-14)/14)+random.gauss(0,1.5)
    if t == "humidité":
        v = 55-20*(1-abs(h-14)/14)+random.gauss(0,5)
        if random.random()<0.10: v=random.uniform(15,28)
        return max(10,min(100,v))
    if t == "pH sol": return random.gauss(6.5,0.4)
    if t == "pluviométrie": return max(0, (2.5 if h<8 or h>20 else 0.2)+random.gauss(0,0.8))
    if t == "vitesse vent": return max(0, random.gauss(12,5))
    if t == "luminosité": return max(0, 0 if h<6 or h>20 else 50000*(1-abs(h-13)/8)+random.gauss(0,5000))
    if t == "pression": return random.gauss(1013,3)
    return 0.0

def insertion_continue():
    print("🔄 Insertion auto toutes les 60s...")
    while True:
        time.sleep(60)
        try:
            now  = datetime.utcnow()
            caps = list(capteurs_col.find({"actif":True}))
            if caps:
                mesures_col.insert_many([{"capteur_id":c["capteur_id"],"parcelle_id":c["parcelle_id"],"parcelle_nom":c.get("parcelle_nom",""),"agriculteur_id":c.get("agriculteur_id",""),"type":c["type"],"valeur":round(_gen(c["type"],now),2),"unite":c["unite"],"timestamp":now} for c in caps])
        except Exception as e:
            print(f"⚠️ Insertion erreur : {e}")


# ── HEALTH CHECK (test que le serveur répond) ────────────────
@app.route("/health")
def health():
    return jsonify({"status": "ok", "time": datetime.utcnow().isoformat()}), 200

@app.route("/api/ping")
def ping():
    try:
        client.admin.command("ping")
        return jsonify({"status": "ok", "mongodb": "connected"}), 200
    except Exception as e:
        return jsonify({"status": "error", "mongodb": str(e)}), 500

# ── PAGES ────────────────────────────────────────────────────
@app.route("/login")
def login_page():
    if session.get("user"): return _redir()
    return send_from_directory("static","login.html")

@app.route("/admin/login")
def admin_login_page():
    if session.get("user") and session["user"].get("role")=="admin": return redirect("/admin")
    return send_from_directory("static","admin_login.html")

@app.route("/register")
def register_page():
    return send_from_directory("static","register.html")

@app.route("/admin")
@role_required("admin")
def admin_page():
    return send_from_directory("static","admin.html")

@app.route("/")
@login_required
def index():
    r = session["user"].get("role")
    if r=="admin":  return redirect("/admin")
    if r=="invite": return send_from_directory("static","invite.html")
    return send_from_directory("static","index.html")

def _redir():
    r = session.get("user",{}).get("role")
    return redirect("/admin" if r=="admin" else "/invite" if r=="invite" else "/")

# ── AUTH API ─────────────────────────────────────────────────
@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    d = request.get_json() or {}
    username = d.get("username","").strip().lower()
    password = d.get("password","")
    is_admin = d.get("admin_route", False)
    if not username or not password: return jsonify({"error":"Champs manquants"}),400
    user = users_col.find_one({"username":username})
    if not user or user["password"]!=hash_pw(password): return jsonify({"error":"Identifiant ou mot de passe incorrect"}),401
    if is_admin and user["role"]!="admin": return jsonify({"error":"Page réservée à l'administrateur"}),403
    if not is_admin and user["role"]=="admin": return jsonify({"error":"Utilisez la page admin","redirect":"/admin/login"}),403
    if user["statut"]=="en_attente": return jsonify({"error":"Compte en attente de validation"}),403
    if user["statut"]=="rejeté":     return jsonify({"error":"Inscription refusée"}),403
    if user["statut"]!="actif":      return jsonify({"error":"Compte inactif"}),403
    session["user"] = {"id":str(user["_id"]),"username":user["username"],"nom":user.get("nom",username),"role":user["role"]}
    users_col.update_one({"_id":user["_id"]},{"$set":{"last_login":datetime.utcnow()}})
    rmap = {"admin":"/admin","invite":"/invite","agriculteur":"/"}
    return jsonify({"message":"Connexion réussie","user":session["user"],"redirect":rmap.get(user["role"],"/")}),200

@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    session.clear()
    return jsonify({"message":"Déconnexion réussie"}),200

@app.route("/api/auth/me")
def auth_me():
    u = session.get("user")
    return (jsonify(u),200) if u else (jsonify({"error":"Non connecté"}),401)

@app.route("/api/auth/register", methods=["POST"])
def auth_register():
    d = request.get_json() or {}
    username = d.get("username","").strip().lower()
    password = d.get("password","")
    nom      = d.get("nom","").strip()
    role     = d.get("role","agriculteur")
    if role=="admin": return jsonify({"error":"Impossible de créer un admin"}),403
    if not username or not password or not nom: return jsonify({"error":"Tous les champs sont obligatoires"}),400
    if len(password)<6: return jsonify({"error":"Mot de passe minimum 6 caractères"}),400
    if users_col.find_one({"username":username}): return jsonify({"error":"Nom d'utilisateur déjà pris"}),409
    users_col.insert_one({"username":username,"password":hash_pw(password),"nom":nom,"role":role,"statut":"en_attente","created_at":datetime.utcnow()})
    return jsonify({"message":"Inscription envoyée. En attente de validation."}),201

# ── ADMIN API ────────────────────────────────────────────────
@app.route("/api/admin/stats")
@role_required("admin")
def admin_stats():
    return jsonify({"total_agriculteurs":users_col.count_documents({"role":"agriculteur","statut":"actif"}),"total_invites":users_col.count_documents({"role":"invite","statut":"actif"}),"en_attente":users_col.count_documents({"statut":"en_attente"}),"total_parcelles":parcelles_col.count_documents({}),"total_capteurs":capteurs_col.count_documents({"actif":True}),"total_mesures_24h":mesures_col.count_documents({"timestamp":{"$gte":datetime.utcnow()-timedelta(hours=24)}})})

@app.route("/api/admin/users")
@role_required("admin")
def admin_get_users():
    users = list(users_col.find({"role":{"$ne":"admin"}},{"_id":1,"username":1,"nom":1,"role":1,"statut":1,"created_at":1,"last_login":1}))
    for u in users:
        u["id"]=str(u.pop("_id"))
        for k in ["created_at","last_login"]:
            if k in u: u[k]=u[k].isoformat()
    return jsonify(users)

@app.route("/api/admin/connected")
@role_required("admin")
def admin_connected():
    users = list(users_col.find({"role":"agriculteur","last_login":{"$gte":datetime.utcnow()-timedelta(hours=24)}},{"_id":1,"username":1,"nom":1,"last_login":1}))
    for u in users:
        u["id"]=str(u.pop("_id"))
        u["last_login"]=u["last_login"].isoformat()
    return jsonify(users)

@app.route("/api/admin/users/<uid>/valider", methods=["POST"])
@role_required("admin")
def admin_valider(uid):
    r = users_col.update_one({"_id":ObjectId(uid)},{"$set":{"statut":"actif","validated_at":datetime.utcnow()}})
    return (jsonify({"message":"Validé"}),200) if r.matched_count else (jsonify({"error":"Introuvable"}),404)

@app.route("/api/admin/users/<uid>/rejeter", methods=["POST"])
@role_required("admin")
def admin_rejeter(uid):
    r = users_col.update_one({"_id":ObjectId(uid)},{"$set":{"statut":"rejeté"}})
    return (jsonify({"message":"Rejeté"}),200) if r.matched_count else (jsonify({"error":"Introuvable"}),404)

@app.route("/api/admin/users/<uid>/desactiver", methods=["POST"])
@role_required("admin")
def admin_desactiver(uid):
    r = users_col.update_one({"_id":ObjectId(uid)},{"$set":{"statut":"inactif"}})
    return (jsonify({"message":"Désactivé"}),200) if r.matched_count else (jsonify({"error":"Introuvable"}),404)

@app.route("/api/admin/users/<uid>/activer", methods=["POST"])
@role_required("admin")
def admin_activer(uid):
    r = users_col.update_one({"_id":ObjectId(uid)},{"$set":{"statut":"actif"}})
    return (jsonify({"message":"Activé"}),200) if r.matched_count else (jsonify({"error":"Introuvable"}),404)

@app.route("/api/admin/agriculteur/<ag_id>/stats")
@role_required("admin")
def admin_ag_stats(ag_id):
    now = datetime.utcnow()
    depuis_24h = now - timedelta(hours=24)
    depuis_7j  = now - timedelta(days=7)
    ag = users_col.find_one({"_id":ObjectId(ag_id)},{"_id":0,"username":1,"nom":1,"last_login":1,"created_at":1,"statut":1})
    if not ag: return jsonify({"error":"Introuvable"}),404
    for k in ["last_login","created_at"]:
        if k in ag and ag[k]: ag[k]=ag[k].isoformat()
    parcelles = list(parcelles_col.find({"agriculteur_id":ag_id},{"_id":1,"nom":1,"superficie":1,"culture":1}))
    for p in parcelles: p["id"]=str(p.pop("_id"))
    derniers = {}
    for t in ["température","humidité","pH sol","vitesse vent","pluviométrie","luminosité","pression"]:
        m = mesures_col.find_one({"agriculteur_id":ag_id,"type":t,"timestamp":{"$gte":depuis_24h}},{"_id":0},sort=[("timestamp",DESCENDING)])
        if m: m["timestamp"]=m["timestamp"].isoformat(); derniers[t]=m
    pipeline = [{"$match":{"agriculteur_id":ag_id,"type":"température","timestamp":{"$gte":depuis_24h}}},{"$group":{"_id":"$parcelle_nom","moyenne":{"$avg":"$valeur"},"min":{"$min":"$valeur"},"max":{"$max":"$valeur"}}},{"$sort":{"_id":1}}]
    stats_temp = list(mesures_col.aggregate(pipeline))
    for r in stats_temp:
        r["parcelle"]=r.pop("_id")
        for k in ["moyenne","min","max"]: r[k]=round(r[k],2)
    return jsonify({"agriculteur":ag,"parcelles":parcelles,"nb_capteurs":capteurs_col.count_documents({"agriculteur_id":ag_id,"actif":True}),"nb_mesures_24h":mesures_col.count_documents({"agriculteur_id":ag_id,"timestamp":{"$gte":depuis_24h}}),"nb_mesures_7j":mesures_col.count_documents({"agriculteur_id":ag_id,"timestamp":{"$gte":depuis_7j}}),"nb_alertes":mesures_col.count_documents({"agriculteur_id":ag_id,"timestamp":{"$gte":depuis_24h},"$or":[{"type":"humidité","valeur":{"$lt":30}},{"type":"température","valeur":{"$gt":38}}]}),"derniers":derniers,"stats_temp":stats_temp})

@app.route("/api/admin/agriculteur/<ag_id>/mesures")
@role_required("admin")
def admin_ag_mesures(ag_id):
    heures = int(request.args.get("heures",24))
    limit  = int(request.args.get("limit",200))
    typ    = request.args.get("type")
    filtre = {"agriculteur_id":ag_id,"timestamp":{"$gte":datetime.utcnow()-timedelta(hours=heures)}}
    if typ and typ!="Tous": filtre["type"]=typ
    data = list(mesures_col.find(filtre,{"_id":0}).sort("timestamp",DESCENDING).limit(limit))
    for d in data: d["timestamp"]=d["timestamp"].isoformat()
    return jsonify(data)

@app.route("/api/admin/global_alertes")
@role_required("admin")
def admin_global_alertes():
    depuis = datetime.utcnow()-timedelta(hours=24)
    alertes=[]
    base={"timestamp":{"$gte":depuis}}
    for m in mesures_col.find({**base,"type":"humidité","valeur":{"$lt":30}},{"_id":0}).sort("timestamp",DESCENDING).limit(100):
        m["timestamp"]=m["timestamp"].isoformat(); m["niveau"]="critique" if m["valeur"]<20 else "avertissement"; m["message"]=f"Humidité : {m['valeur']}%"; alertes.append(m)
    for m in mesures_col.find({**base,"type":"température","valeur":{"$gt":38}},{"_id":0}).sort("timestamp",DESCENDING).limit(100):
        m["timestamp"]=m["timestamp"].isoformat(); m["niveau"]="critique"; m["message"]=f"Température : {m['valeur']}°C"; alertes.append(m)
    alertes.sort(key=lambda x:x["timestamp"],reverse=True)
    return jsonify(alertes[:150])

@app.route("/api/admin/rapport_global")
@role_required("admin")
def admin_rapport_global():
    ags=list(users_col.find({"role":"agriculteur","statut":"actif"},{"_id":1,"nom":1,"username":1}))
    depuis_24h=datetime.utcnow()-timedelta(hours=24)
    rapport=[]
    for ag in ags:
        ag_id=str(ag["_id"])
        rapport.append({"id":ag_id,"nom":ag["nom"],"username":ag["username"],"nb_parcelles":parcelles_col.count_documents({"agriculteur_id":ag_id}),"nb_capteurs":capteurs_col.count_documents({"agriculteur_id":ag_id,"actif":True}),"nb_mesures":mesures_col.count_documents({"agriculteur_id":ag_id,"timestamp":{"$gte":depuis_24h}}),"nb_alertes":mesures_col.count_documents({"agriculteur_id":ag_id,"timestamp":{"$gte":depuis_24h},"$or":[{"type":"humidité","valeur":{"$lt":30}},{"type":"température","valeur":{"$gt":38}}]})})
    return jsonify(rapport)

# ── PARCELLES ────────────────────────────────────────────────
@app.route("/api/parcelles", methods=["GET"])
@login_required
def get_parcelles():
    u=session["user"]; ag_id=request.args.get("agriculteur_id")
    if u["role"]=="agriculteur": filtre={"agriculteur_id":u["id"]}
    elif u["role"]=="invite":    filtre={"agriculteur_id":ag_id} if ag_id else {}
    else:                        filtre={}
    ps=list(parcelles_col.find(filtre,{"_id":1,"nom":1,"superficie":1,"culture":1,"agriculteur_id":1,"agriculteur_nom":1,"created_at":1}))
    for p in ps:
        p["id"]=str(p.pop("_id"))
        if "created_at" in p: p["created_at"]=p["created_at"].isoformat()
    return jsonify(ps)

@app.route("/api/parcelles", methods=["POST"])
@role_required("agriculteur")
def add_parcelle():
    d=request.get_json() or {}; nom=d.get("nom","").strip()
    if not nom: return jsonify({"error":"Nom requis"}),400
    u=session["user"]
    r=parcelles_col.insert_one({"nom":nom,"superficie":d.get("superficie",0),"culture":d.get("culture",""),"agriculteur_id":u["id"],"agriculteur_nom":u["nom"],"created_at":datetime.utcnow()})
    return jsonify({"message":"Parcelle ajoutée","id":str(r.inserted_id)}),201

@app.route("/api/parcelles/<pid>", methods=["DELETE"])
@role_required("agriculteur")
def delete_parcelle(pid):
    u=session["user"]
    r=parcelles_col.delete_one({"_id":ObjectId(pid),"agriculteur_id":u["id"]})
    if not r.deleted_count: return jsonify({"error":"Introuvable"}),404
    capteurs_col.delete_many({"parcelle_id":pid})
    return jsonify({"message":"Supprimée"}),200

# ── CAPTEURS ─────────────────────────────────────────────────
@app.route("/api/capteurs", methods=["GET"])
@login_required
def get_capteurs():
    u=session["user"]; ag_id=request.args.get("agriculteur_id"); pid=request.args.get("parcelle_id")
    if u["role"]=="agriculteur": filtre={"agriculteur_id":u["id"]}
    elif u["role"]=="invite":    filtre={"agriculteur_id":ag_id} if ag_id else {}
    else:                        filtre={}
    if pid: filtre["parcelle_id"]=pid
    cs=list(capteurs_col.find(filtre,{"_id":1,"capteur_id":1,"type":1,"unite":1,"parcelle_id":1,"parcelle_nom":1,"actif":1}))
    for c in cs: c["id"]=str(c.pop("_id"))
    return jsonify(cs)

@app.route("/api/capteurs", methods=["POST"])
@role_required("agriculteur")
def add_capteur():
    d=request.get_json() or {}; pid=d.get("parcelle_id",""); typ=d.get("type","")
    if not pid or not typ: return jsonify({"error":"parcelle_id et type requis"}),400
    u=session["user"]; p=parcelles_col.find_one({"_id":ObjectId(pid),"agriculteur_id":u["id"]})
    if not p: return jsonify({"error":"Parcelle introuvable"}),404
    unites={"température":"°C","humidité":"%","pH sol":"pH","pluviométrie":"mm","vitesse vent":"km/h","luminosité":"lux","pression":"hPa"}
    cid=f"CAP-{u['username'][:3].upper()}-{pid[-4:].upper()}-{typ[:4].upper()}-{secrets.token_hex(2).upper()}"
    capteurs_col.insert_one({"capteur_id":cid,"parcelle_id":pid,"parcelle_nom":p.get("nom",""),"agriculteur_id":u["id"],"type":typ,"unite":unites.get(typ,"?"),"actif":True,"created_at":datetime.utcnow()})
    return jsonify({"message":"Capteur ajouté","capteur_id":cid}),201

@app.route("/api/capteurs/<cid>", methods=["DELETE"])
@role_required("agriculteur")
def delete_capteur(cid):
    u=session["user"]
    r=capteurs_col.delete_one({"_id":ObjectId(cid),"agriculteur_id":u["id"]})
    return (jsonify({"message":"Supprimé"}),200) if r.deleted_count else (jsonify({"error":"Introuvable"}),404)

# ── MESURES ──────────────────────────────────────────────────
def _filtre_base(heures=24):
    u=session["user"]; ag_id=request.args.get("agriculteur_id")
    f={"timestamp":{"$gte":datetime.utcnow()-timedelta(hours=heures)}}
    if u["role"]=="agriculteur": f["agriculteur_id"]=u["id"]
    elif u["role"]=="invite" and ag_id: f["agriculteur_id"]=ag_id
    return f

@app.route("/api/mesures")
@login_required
def get_mesures():
    heures=int(request.args.get("heures",24)); limit=int(request.args.get("limit",200))
    typ=request.args.get("type"); pid=request.args.get("parcelle_id")
    f=_filtre_base(heures)
    if pid: f["parcelle_id"]=pid
    if typ and typ!="Tous": f["type"]=typ
    data=list(mesures_col.find(f,{"_id":0}).sort("timestamp",DESCENDING).limit(limit))
    for d in data: d["timestamp"]=d["timestamp"].isoformat()
    return jsonify(data)

@app.route("/api/alertes")
@login_required
def get_alertes():
    sh=float(request.args.get("seuil_hum",30)); st=float(request.args.get("seuil_temp",38))
    f=_filtre_base(24); alertes=[]
    for m in mesures_col.find({**f,"type":"humidité","valeur":{"$lt":sh}},{"_id":0}).sort("timestamp",DESCENDING).limit(50):
        m["timestamp"]=m["timestamp"].isoformat(); m["niveau"]="critique" if m["valeur"]<20 else "avertissement"; m["message"]=f"Humidité : {m['valeur']}%"; alertes.append(m)
    for m in mesures_col.find({**f,"type":"température","valeur":{"$gt":st}},{"_id":0}).sort("timestamp",DESCENDING).limit(50):
        m["timestamp"]=m["timestamp"].isoformat(); m["niveau"]="critique"; m["message"]=f"Température : {m['valeur']}°C"; alertes.append(m)
    for m in mesures_col.find({**f,"type":"pH sol","$or":[{"valeur":{"$lt":5.5}},{"valeur":{"$gt":7.5}}]},{"_id":0}).sort("timestamp",DESCENDING).limit(50):
        m["timestamp"]=m["timestamp"].isoformat(); m["niveau"]="avertissement"; m["message"]=f"pH : {m['valeur']}"; alertes.append(m)
    alertes.sort(key=lambda x:x["timestamp"],reverse=True)
    return jsonify(alertes[:100])

@app.route("/api/dashboard")
@login_required
def dashboard():
    u=session["user"]; ag_id=request.args.get("agriculteur_id"); now=datetime.utcnow()
    f=_filtre_base(24)
    pf={"agriculteur_id":u["id"]} if u["role"]=="agriculteur" else ({"agriculteur_id":ag_id} if ag_id else {})
    derniers={}
    for t in ["température","humidité","pH sol"]:
        m=mesures_col.find_one({**f,"type":t},{"_id":0},sort=[("timestamp",DESCENDING)])
        if m: m["timestamp"]=m["timestamp"].isoformat(); derniers[t]=m
    return jsonify({"total_mesures":mesures_col.count_documents(f),"nb_alertes":mesures_col.count_documents({**f,"$or":[{"type":"humidité","valeur":{"$lt":30}},{"type":"température","valeur":{"$gt":38}}]}),"nb_capteurs":capteurs_col.count_documents({**pf,"actif":True}),"nb_parcelles":parcelles_col.count_documents(pf),"derniers":derniers,"heure_serveur":now.isoformat()})

@app.route("/api/stats/moyenne_temperature")
@login_required
def moyenne_temperature():
    f=_filtre_base(24); f["type"]="température"
    pipeline=[{"$match":f},{"$group":{"_id":"$parcelle_nom","moyenne":{"$avg":"$valeur"},"min":{"$min":"$valeur"},"max":{"$max":"$valeur"},"nb":{"$sum":1}}},{"$sort":{"_id":1}}]
    result=list(mesures_col.aggregate(pipeline))
    for r in result:
        r["parcelle"]=r.pop("_id")
        for k in ["moyenne","min","max"]: r[k]=round(r[k],2)
    return jsonify(result)

@app.route("/api/evolution_horaire/<capteur_id>")
@login_required
def evolution_horaire(capteur_id):
    pipeline=[{"$match":{"capteur_id":capteur_id,"timestamp":{"$gte":datetime.utcnow()-timedelta(hours=24)}}},{"$group":{"_id":{"$hour":"$timestamp"},"moyenne":{"$avg":"$valeur"},"min":{"$min":"$valeur"},"max":{"$max":"$valeur"}}},{"$sort":{"_id":1}}]
    result=list(mesures_col.aggregate(pipeline))
    for r in result:
        r["heure"]=r.pop("_id")
        for k in ["moyenne","min","max"]: r[k]=round(r[k],2)
    return jsonify(result)

@app.route("/api/agriculteurs")
@login_required
def get_agriculteurs():
    ags=list(users_col.find({"role":"agriculteur","statut":"actif"},{"_id":1,"nom":1,"username":1}))
    for a in ags: a["id"]=str(a.pop("_id"))
    return jsonify(ags)

# ── DÉMARRAGE ────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    threading.Thread(target=insertion_continue, daemon=True).start()
    port = int(os.getenv("PORT", 5000))
    print(f"🌱 AgroSense démarré sur port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)

# Pour Gunicorn (Render) — init au premier démarrage
try:
    init_db()
    threading.Thread(target=insertion_continue, daemon=True).start()
    print("🌱 AgroSense prêt (Gunicorn)")
except Exception as e:
    print(f"⚠️ Init erreur : {e}")
