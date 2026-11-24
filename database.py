"""
MailStorm - Multi-Tenant Database & SaaS Authentication Module (SQLite)
Gère le stockage multi-tenant (une base SQLite dédiée par club),
l'authentification, les licences payantes, et l'espace Super Admin.
"""

import os
import sqlite3
import hashlib
import secrets
import json
import time
import uuid

DB_FILE = os.path.join(os.path.dirname(__file__), "mailstorm.db")
TENANTS_DIR = os.path.join(os.path.dirname(__file__), "tenants")

def get_db():
    """Connexion à la base de données principale (Utilisateurs & Sessions)"""
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def get_tenant_db(user_id=1):
    """
    Connexion à la base SQLite isolée dédiée à un club spécifique (Multi-Tenant).
    Chaque club a son propre fichier : tenants/club_<user_id>.db
    """
    if not user_id:
        user_id = 1
    os.makedirs(TENANTS_DIR, exist_ok=True)
    db_path = os.path.join(TENANTS_DIR, f"club_{user_id}.db")
    is_new = not os.path.exists(db_path)
    
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    
    # Initialise les tables du tenant si elles n'existent pas
    init_tenant_schema(conn, user_id, is_new=is_new)
    return conn

def hash_password(password, salt=None):
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000).hex()
    return hashed, salt

def verify_password(password, stored_hash, salt):
    hashed, _ = hash_password(password, salt)
    return secrets.compare_digest(hashed, stored_hash)

def init_tenant_schema(conn, user_id, is_new=False):
    """Crée les tables isolées pour chaque club dans sa propre base SQLite"""
    c = conn.cursor()
    
    # 1. Configuration locale du Club
    c.execute("""
    CREATE TABLE IF NOT EXISTS config (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    # 2. Signatures du Club
    c.execute("""
    CREATE TABLE IF NOT EXISTS signatures (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        content TEXT NOT NULL,
        is_default INTEGER DEFAULT 0,
        created_at TEXT,
        updated_at TEXT
    )
    """)

    # 3. Modèles d'emails du Club
    c.execute("""
    CREATE TABLE IF NOT EXISTS templates (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        subject TEXT,
        content TEXT,
        category TEXT DEFAULT 'general',
        created_at TEXT,
        updated_at TEXT
    )
    """)

    # 4. Listes de contacts du Club
    c.execute("""
    CREATE TABLE IF NOT EXISTS contact_lists (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        count INTEGER DEFAULT 0,
        contacts_json TEXT,
        created_at TEXT,
        updated_at TEXT
    )
    """)

    # 5. Historique des campagnes du Club
    c.execute("""
    CREATE TABLE IF NOT EXISTS history (
        id TEXT PRIMARY KEY,
        date TEXT,
        subject TEXT,
        provider TEXT,
        total INTEGER,
        sent INTEGER,
        failed INTEGER,
        duration TEXT,
        logs_json TEXT,
        created_at TEXT
    )
    """)

    # 6. Tâches planifiées du Club
    c.execute("""
    CREATE TABLE IF NOT EXISTS scheduled_tasks (
        id TEXT PRIMARY KEY,
        title TEXT,
        scheduled_time TEXT,
        status TEXT,
        payload_json TEXT,
        created_at TEXT
    )
    """)

    # 7. Configuration Certificats du Club
    c.execute("""
    CREATE TABLE IF NOT EXISTS certificate_config (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)
    conn.commit()

    # Si nouvelle base de tenant pour un nouveau club, initialiser les modèles et config par défaut
    if is_new:
        seed_tenant_defaults(conn, user_id)

def seed_tenant_defaults(conn, user_id):
    """Initialise un nouveau club avec des données par défaut adaptées"""
    try:
        master_conn = get_db()
        m_cur = master_conn.cursor()
        m_cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        u = m_cur.fetchone()
        master_conn.close()
    except Exception:
        u = None

    club_name = u["club_name"] if u and u["club_name"] else (u["display_name"] if u and u["display_name"] else "Mon Club")
    sender_name = u["display_name"] if u and u["display_name"] else club_name
    sender_email = u["email"] if u and u["email"] else ""
    phone = u["phone"] if u and u["phone"] else "+216 00 000 000"

    c = conn.cursor()
    # 1. Config par défaut
    default_config = {
        "provider": "brevo",
        "sender_email": sender_email,
        "gmail_address": sender_email,
        "sender_name": sender_name,
        "default_delay": 2,
        "include_signature": True
    }
    for k, v in default_config.items():
        c.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (k, json.dumps(v, ensure_ascii=False)))

    # 2. Signature par défaut pour ce Club
    default_sig_content = f"""<div style="font-family: Arial, sans-serif; font-size: 13px; color: #334155; line-height: 1.5; border-top: 2px solid #6366f1; padding-top: 10px; margin-top: 15px;">
  <p style="margin: 0; font-size: 15px; font-weight: bold; color: #1e293b;">{sender_name}</p>
  <p style="margin: 2px 0 6px 0; color: #6366f1; font-weight: 600;">Bureau Exécutif | {club_name}</p>
  <p style="margin: 0; color: #64748b; font-size: 12px;">📞 {phone} | ✉️ {sender_email}</p>
  <p style="margin: 2px 0 0 0; color: #64748b; font-size: 12px;">📍 Tunisie</p>
</div>"""
    c.execute("""
    INSERT OR REPLACE INTO signatures (id, name, content, is_default, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        str(uuid.uuid4())[:8],
        "Signature Officielle Club",
        default_sig_content,
        1,
        time.strftime("%d/%m/%Y"),
        time.strftime("%d/%m/%Y")
    ))

    # 3. Certificat config par défaut
    default_cert = {
        "enabled": False,
        "template_type": "epik_leaders",
        "output_format": "pdf",
        "name_var": "",
        "event_title": "Session de Formation",
        "subtitle": "En reconnaissance de sa participation active et assidue à la session de formation :",
        "issuer_name": club_name,
        "date_str": time.strftime("%d %B %Y"),
        "font_color": "#110b07",
        "font_size": 38,
        "name_y_pct": 45.3,
        "filename_pattern": "Certificat_{Nom}.pdf"
    }
    for k, v in default_cert.items():
        c.execute("INSERT OR REPLACE INTO certificate_config (key, value) VALUES (?, ?)", (k, json.dumps(v, ensure_ascii=False)))

    conn.commit()

def init_db():
    """Initialise la base de données principale et gère les migrations de schéma"""
    os.makedirs(TENANTS_DIR, exist_ok=True)
    conn = get_db()
    c = conn.cursor()

    # 1. Users Table (Multi-tenant SaaS & Roles)
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        display_name TEXT,
        club_name TEXT,
        phone TEXT,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        role TEXT DEFAULT 'club',
        status TEXT DEFAULT 'pending',
        notes TEXT,
        created_at TEXT,
        last_login TEXT
    )
    """)

    # Migration de colonnes si table existante
    columns = [col[1] for col in c.execute("PRAGMA table_info(users)").fetchall()]
    if "club_name" not in columns:
        try: c.execute("ALTER TABLE users ADD COLUMN club_name TEXT")
        except Exception: pass
    if "phone" not in columns:
        try: c.execute("ALTER TABLE users ADD COLUMN phone TEXT")
        except Exception: pass
    if "status" not in columns:
        try: c.execute("ALTER TABLE users ADD COLUMN status TEXT DEFAULT 'pending'")
        except Exception: pass
    if "notes" not in columns:
        try: c.execute("ALTER TABLE users ADD COLUMN notes TEXT")
        except Exception: pass

    # 2. Sessions Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        created_at TEXT,
        expires_at INTEGER,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)
    conn.commit()

    # Initialiser / Mettre à jour le compte Super Admin
    c.execute("SELECT * FROM users WHERE username = 'admin' OR role = 'superadmin' LIMIT 1")
    admin_row = c.fetchone()
    if not admin_row:
        pwd_hash, salt = hash_password("admin123")
        c.execute("""
        INSERT INTO users (username, email, display_name, club_name, phone, password_hash, salt, role, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "admin", 
            "mrtmousdi@gmail.com", 
            "Mohamed Ali Mseddi", 
            "Club Scientifique EPIK Leaders",
            "+216 00 000 000",
            pwd_hash, 
            salt, 
            "superadmin", 
            "active", 
            time.strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()
    else:
        # S'assurer que le super admin a bien le statut actif et le rôle superadmin
        c.execute("""
        UPDATE users SET role = 'superadmin', status = 'active', email = COALESCE(email, 'mrtmousdi@gmail.com')
        WHERE id = ?
        """, (admin_row["id"],))
        conn.commit()

    # Initialiser / Restaurer le compte Club mseddi lassad (mss)
    c.execute("SELECT * FROM users WHERE username = 'mss' LIMIT 1")
    mss_row = c.fetchone()
    if not mss_row:
        pwd_hash, salt = hash_password("mss123")
        c.execute("""
        INSERT INTO users (username, email, display_name, club_name, phone, password_hash, salt, role, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "mss",
            "mss.mss.mousdi@gmail.com",
            "mseddi lassad",
            "Bureau Exécutif | mss",
            "+21623926721",
            pwd_hash,
            salt,
            "club",
            "active",
            time.strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()
        mss_id = c.lastrowid
        try:
            mss_tenant = get_tenant_db(mss_id)
            mss_cur = mss_tenant.cursor()
            sig_id = str(uuid.uuid4())[:8]
            sig_content = """<p style="margin: 0; font-size: 14px; font-weight: bold; color: #0f172a;">mseddi lassad</p>
<p style="margin: 0; font-size: 12px; color: #4f46e5; font-weight: 600;">Bureau Exécutif | mss</p>
<p style="margin: 4px 0 0 0; font-size: 11px; color: #64748b;">📞 +21623926721 &nbsp;|&nbsp; ✉️ mss.mss.mousdi@gmail.com</p>
<p style="margin: 2px 0 0 0; font-size: 11px; color: #64748b;">📍 Tunisie</p>"""
            mss_cur.execute("""
            INSERT OR REPLACE INTO signatures (id, name, content, is_default, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (sig_id, "Signature Officielle Club", sig_content, 1, time.strftime("%Y-%m-%d %H:%M:%S"), time.strftime("%Y-%m-%d %H:%M:%S")))
            mss_cur.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ("sender_name", json.dumps("mseddi lassad", ensure_ascii=False)))
            mss_cur.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ("sender_email", json.dumps("mss.mss.mousdi@gmail.com", ensure_ascii=False)))
            mss_cur.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ("email_signature", json.dumps(sig_content, ensure_ascii=False)))
            mss_cur.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ("include_signature", json.dumps(True)))
            mss_tenant.commit()
            mss_tenant.close()
        except Exception as e:
            print("Erreur initialisation tenant mss:", e)

    conn.close()

    # Migration des tables existantes vers tenants/club_1.db pour le super admin
    migrate_admin_tenant_data()

def migrate_admin_tenant_data():
    """Migre les données existantes de mailstorm.db vers tenants/club_1.db si nécessaire"""
    admin_tenant_db_path = os.path.join(TENANTS_DIR, "club_1.db")
    if os.path.exists(admin_tenant_db_path):
        return

    print("Migration des données de l'administrateur vers tenants/club_1.db...")
    master_conn = get_db()
    tenant_conn = get_tenant_db(1)
    m_cur = master_conn.cursor()
    t_cur = tenant_conn.cursor()

    tables = ["config", "signatures", "templates", "contact_lists", "history", "scheduled_tasks", "certificate_config"]
    for tbl in tables:
        try:
            m_cur.execute(f"SELECT * FROM {tbl}")
            rows = m_cur.fetchall()
            if rows:
                col_names = [col[0] for col in m_cur.description]
                placeholders = ",".join(["?"] * len(col_names))
                for r in rows:
                    t_cur.execute(f"INSERT OR REPLACE INTO {tbl} ({','.join(col_names)}) VALUES ({placeholders})", tuple(r))
                tenant_conn.commit()
        except Exception as e:
            # Table non présente dans l'ancienne version, c'est normal
            pass

    master_conn.close()
    tenant_conn.close()
    print("✓ Données administrateur migrées avec succès dans tenants/club_1.db")

# ==============================================================================
# AUTHENTICATION & USER MANAGEMENT
# ==============================================================================

def authenticate_user(username_or_email, password):
    """Vérifie les identifiants d'un utilisateur et met à jour son dernier accès"""
    conn = get_db()
    c = conn.cursor()
    c.execute("""
    SELECT * FROM users WHERE LOWER(username) = LOWER(?) OR LOWER(email) = LOWER(?)
    """, (username_or_email.strip(), username_or_email.strip()))
    user = c.fetchone()
    if not user:
        conn.close()
        return None
    
    if verify_password(password, user["password_hash"], user["salt"]):
        c.execute("UPDATE users SET last_login = ? WHERE id = ?", (time.strftime("%Y-%m-%d %H:%M:%S"), user["id"]))
        conn.commit()
        user_dict = dict(user)
        conn.close()
        return user_dict
    conn.close()
    return None

def create_user_session(user_id, duration_days=30):
    token = secrets.token_urlsafe(32)
    expires_at = int(time.time()) + (duration_days * 86400)
    conn = get_db()
    c = conn.cursor()
    c.execute("""
    INSERT INTO sessions (token, user_id, created_at, expires_at)
    VALUES (?, ?, ?, ?)
    """, (token, user_id, time.strftime("%Y-%m-%d %H:%M:%S"), expires_at))
    conn.commit()
    conn.close()
    return token

def get_user_by_session(token):
    if not token:
        return None
    conn = get_db()
    c = conn.cursor()
    now = int(time.time())
    c.execute("""
    SELECT u.id, u.username, u.email, u.display_name, u.club_name, u.phone, u.role, u.status
    FROM sessions s
    JOIN users u ON s.user_id = u.id
    WHERE s.token = ? AND s.expires_at > ?
    """, (token, now))
    user = c.fetchone()
    conn.close()
    return dict(user) if user else None

def delete_user_session(token):
    if not token:
        return
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()
    conn.close()

def change_user_password(user_id, new_password):
    pwd_hash, salt = hash_password(new_password)
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET password_hash = ?, salt = ? WHERE id = ?", (pwd_hash, salt, user_id))
    c.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def register_user(data):
    """
    Inscription d'un nouveau Club.
    Par défaut, status = 'pending' (en attente d'activation après paiement).
    """
    username = data.get("username", "").strip()
    email = data.get("email", "").strip().lower()
    display_name = data.get("display_name", "").strip()
    club_name = data.get("club_name", "").strip() or display_name
    phone = data.get("phone", "").strip()
    password = data.get("password", "")

    if not username or not email or not password:
        return False, "Veuillez renseigner tous les champs obligatoires."

    conn = get_db()
    c = conn.cursor()
    
    # Vérifier doublon username
    c.execute("SELECT id FROM users WHERE LOWER(username) = LOWER(?)", (username,))
    if c.fetchone():
        conn.close()
        return False, f"L'identifiant '{username}' est déjà utilisé. Veuillez en choisir un autre."

    # Vérifier doublon email
    c.execute("SELECT id FROM users WHERE LOWER(email) = LOWER(?)", (email,))
    if c.fetchone():
        conn.close()
        return False, f"L'adresse email '{email}' est déjà enregistrée."

    pwd_hash, salt = hash_password(password)
    c.execute("""
    INSERT INTO users (username, email, display_name, club_name, phone, password_hash, salt, role, status, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, 'club', 'pending', ?)
    """, (
        username,
        email,
        display_name,
        club_name,
        phone,
        pwd_hash,
        salt,
        time.strftime("%Y-%m-%d %H:%M:%S")
    ))
    new_user_id = c.lastrowid
    conn.commit()
    conn.close()

    # Initialise sa propre base SQLite isolée
    get_tenant_db(new_user_id)

    return True, "Votre compte club a été créé avec succès ! Il est actuellement en attente d'activation par l'administrateur (Mohamed Ali Mseddi). Dès confirmation de votre abonnement, votre accès sera validé."

# ==============================================================================
# SUPER ADMIN DASHBOARD & CLUBS MANAGEMENT
# ==============================================================================

def db_get_all_clubs():
    """
    Retourne la liste complète de tous les clubs pour le Super Admin,
    avec le calcul des statistiques en temps réel depuis chaque base de données club.
    """
    conn = get_db()
    c = conn.cursor()
    c.execute("""
    SELECT id, username, email, display_name, club_name, phone, role, status, notes, created_at, last_login
    FROM users
    ORDER BY role DESC, id ASC
    """)
    users = [dict(r) for r in c.fetchall()]
    conn.close()

    for u in users:
        u_id = u["id"]
        # Statistiques depuis la base tenant du club
        total_campaigns = 0
        total_sent = 0
        total_contacts = 0
        try:
            tenant_conn = get_tenant_db(u_id)
            t_cur = tenant_conn.cursor()
            
            # Total envois depuis l'historique
            t_cur.execute("SELECT COUNT(*) as count, COALESCE(SUM(sent), 0) as total_sent FROM history")
            h_stat = t_cur.fetchone()
            if h_stat:
                total_campaigns = h_stat["count"]
                total_sent = h_stat["total_sent"]

            # Total contacts enregistrés
            t_cur.execute("SELECT COALESCE(SUM(count), 0) as total_c FROM contact_lists")
            c_stat = t_cur.fetchone()
            if c_stat:
                total_contacts = c_stat["total_c"]

            tenant_conn.close()
        except Exception:
            pass

        u["total_campaigns"] = total_campaigns
        u["total_sent"] = total_sent
        u["total_contacts"] = total_contacts

    return users

def db_create_club_by_admin(data):
    """Création manuelle d'un compte Club par le Super Admin"""
    username = data.get("username", "").strip()
    email = data.get("email", "").strip().lower()
    display_name = data.get("display_name", "").strip()
    club_name = data.get("club_name", "").strip() or display_name
    phone = data.get("phone", "").strip()
    password = data.get("password", "") or "club123"
    status = data.get("status", "active")  # Par défaut actif si créé par le super admin
    notes = data.get("notes", "")

    if not username or not email:
        return False, "Nom d'utilisateur et email requis."

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE LOWER(username) = LOWER(?)", (username,))
    if c.fetchone():
        conn.close()
        return False, "Cet identifiant existe déjà."
    c.execute("SELECT id FROM users WHERE LOWER(email) = LOWER(?)", (email,))
    if c.fetchone():
        conn.close()
        return False, "Cette adresse email existe déjà."

    pwd_hash, salt = hash_password(password)
    c.execute("""
    INSERT INTO users (username, email, display_name, club_name, phone, password_hash, salt, role, status, notes, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, 'club', ?, ?, ?)
    """, (
        username, email, display_name, club_name, phone, pwd_hash, salt, status, notes, time.strftime("%Y-%m-%d %H:%M:%S")
    ))
    new_id = c.lastrowid
    conn.commit()
    conn.close()

    # Initialise la base de données isolée du club
    get_tenant_db(new_id)

    return True, "Club créé avec succès !"

def db_update_club_status(user_id, new_status):
    """Active, suspend ou met en attente un compte club"""
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET status = ? WHERE id = ?", (new_status, user_id))
    if new_status != "active":
        # Déconnecte le club immédiatement s'il est suspendu ou en attente
        c.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    return True

def db_admin_reset_password(user_id, new_password):
    """Réinitialisation de mot de passe d'un club par le Super Admin"""
    change_user_password(user_id, new_password)
    return True

def db_delete_club(user_id):
    """Supprime un compte club et sa base de données isolée"""
    if str(user_id) == "1":
        return False, "Impossible de supprimer le compte Super Admin principal."

    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id = ?", (user_id,))
    c.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

    # Suppression du fichier SQLite dédié
    tenant_file = os.path.join(TENANTS_DIR, f"club_{user_id}.db")
    if os.path.exists(tenant_file):
        try:
            os.remove(tenant_file)
        except Exception:
            pass

    return True, "Compte club et données supprimés avec succès."

# ==============================================================================
# MULTI-TENANT CRUD OPERATIONS (CHACUN DANS SA BASE DE DONNÉES)
# ==============================================================================

def db_load_config(user_id=1):
    """Charge la configuration du club depuis sa base dédiée, avec email verrouillé"""
    # 1. Récupère les données officielles de l'utilisateur depuis la base principale
    master_conn = get_db()
    c_m = master_conn.cursor()
    c_m.execute("SELECT email, display_name, club_name, role FROM users WHERE id = ?", (user_id,))
    u_row = c_m.fetchone()
    master_conn.close()

    official_email = u_row["email"] if u_row and u_row["email"] else ""
    official_name = (u_row["display_name"] or u_row["club_name"] or "") if u_row else ""
    user_role = u_row["role"] if u_row and u_row["role"] else "club"

    # 2. Récupère la config depuis sa base SQLite tenant
    conn = get_tenant_db(user_id)
    c = conn.cursor()
    c.execute("SELECT key, value FROM config")
    rows = c.fetchall()
    conn.close()

    res = {
        "provider": "brevo",
        "sender_email": official_email,
        "gmail_address": official_email,
        "app_password": "",
        "brevo_api_key": "",
        "sender_name": official_name,
        "default_delay": 2,
        "email_signature": "",
        "include_signature": True,
        "user_role": user_role
    }
    for r in rows:
        try:
            res[r["key"]] = json.loads(r["value"])
        except Exception:
            res[r["key"]] = r["value"]

    # 🔒 Règle stricte : L'adresse email d'envoi est TOUJOURS verrouillée à l'email du compte
    res["sender_email"] = official_email
    res["gmail_address"] = official_email
    if not res.get("sender_name"):
        res["sender_name"] = official_name

    return res

def db_save_config(data, user_id=1):
    """Enregistre la configuration dans la base du club, en garantissant la persistance"""
    current = db_load_config(user_id)
    current.update(data)

    # 🔒 Sécurité : Ne peut jamais modifier son adresse email d'expéditeur
    master_conn = get_db()
    c_m = master_conn.cursor()
    c_m.execute("SELECT email, display_name FROM users WHERE id = ?", (user_id,))
    u_row = c_m.fetchone()
    master_conn.close()

    if u_row and u_row["email"]:
        current["sender_email"] = u_row["email"]
        current["gmail_address"] = u_row["email"]

    conn = get_tenant_db(user_id)
    c = conn.cursor()
    for k, v in current.items():
        c.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (k, json.dumps(v, ensure_ascii=False)))
    conn.commit()
    conn.close()
    return current

def db_load_signatures(user_id=1):
    conn = get_tenant_db(user_id)
    c = conn.cursor()
    c.execute("SELECT * FROM signatures ORDER BY is_default DESC, created_at DESC")
    rows = c.fetchall()
    conn.close()
    if rows:
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "content": r["content"],
                "is_default": bool(r["is_default"]),
                "created_at": r["created_at"],
                "updated_at": r["updated_at"]
            }
            for r in rows
        ]
    return []

def db_save_signatures(sigs, user_id=1):
    conn = get_tenant_db(user_id)
    c = conn.cursor()
    c.execute("DELETE FROM signatures")
    for s in sigs:
        c.execute("""
        INSERT INTO signatures (id, name, content, is_default, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            s.get("id", str(uuid.uuid4())[:8]),
            s.get("name", "Signature"),
            s.get("content", ""),
            1 if s.get("is_default") else 0,
            s.get("created_at", time.strftime("%d/%m/%Y")),
            s.get("updated_at", time.strftime("%d/%m/%Y"))
        ))
    conn.commit()
    conn.close()

def db_load_history(user_id=1):
    conn = get_tenant_db(user_id)
    c = conn.cursor()
    c.execute("SELECT * FROM history ORDER BY rowid DESC LIMIT 50")
    rows = c.fetchall()
    conn.close()
    res = []
    for r in rows:
        try:
            logs = json.loads(r["logs_json"]) if r["logs_json"] else []
        except Exception:
            logs = []
        res.append({
            "id": r["id"],
            "date": r["date"],
            "subject": r["subject"],
            "provider": r["provider"],
            "total": r["total"],
            "sent": r["sent"],
            "failed": r["failed"],
            "duration": r["duration"],
            "logs": logs
        })
    return res

def db_save_campaign_to_history(entry, user_id=1):
    conn = get_tenant_db(user_id)
    c = conn.cursor()
    c.execute("""
    INSERT INTO history (id, date, subject, provider, total, sent, failed, duration, logs_json, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        str(entry.get("id", uuid.uuid4()))[:8],
        entry.get("date", time.strftime("%d/%m/%Y à %H:%M")),
        entry.get("subject", ""),
        entry.get("provider", "brevo"),
        int(entry.get("total", 0)),
        int(entry.get("sent", 0)),
        int(entry.get("failed", 0)),
        entry.get("duration", "0s"),
        json.dumps(entry.get("logs", []), ensure_ascii=False),
        time.strftime("%Y-%m-%d %H:%M:%S")
    ))
    conn.commit()
    conn.close()

def db_clear_history(user_id=1):
    conn = get_tenant_db(user_id)
    c = conn.cursor()
    c.execute("DELETE FROM history")
    conn.commit()
    conn.close()

def db_delete_history_item(camp_id, user_id=1):
    conn = get_tenant_db(user_id)
    c = conn.cursor()
    c.execute("DELETE FROM history WHERE id = ?", (str(camp_id),))
    conn.commit()
    conn.close()

def db_load_contact_lists(user_id=1):
    conn = get_tenant_db(user_id)
    c = conn.cursor()
    c.execute("SELECT * FROM contact_lists ORDER BY rowid DESC")
    rows = c.fetchall()
    conn.close()
    res = []
    for r in rows:
        try:
            contacts = json.loads(r["contacts_json"]) if r["contacts_json"] else []
        except Exception:
            contacts = []
        res.append({
            "id": r["id"],
            "name": r["name"],
            "count": r["count"],
            "contacts": contacts,
            "created_at": r["created_at"],
            "updated_at": r["updated_at"]
        })
    return res

def db_save_contact_lists(lists, user_id=1):
    conn = get_tenant_db(user_id)
    c = conn.cursor()
    c.execute("DELETE FROM contact_lists")
    for l in lists:
        contacts = l.get("contacts", [])
        c.execute("""
        INSERT INTO contact_lists (id, name, count, contacts_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            str(l.get("id", uuid.uuid4()))[:8],
            l.get("name", "Liste"),
            l.get("count", len(contacts)),
            json.dumps(contacts, ensure_ascii=False),
            l.get("created_at", time.strftime("%d/%m/%Y")),
            l.get("updated_at", time.strftime("%d/%m/%Y"))
        ))
    conn.commit()
    conn.close()

def db_load_custom_templates(user_id=1):
    conn = get_tenant_db(user_id)
    c = conn.cursor()
    c.execute("SELECT * FROM templates ORDER BY rowid DESC")
    rows = c.fetchall()
    conn.close()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "subject": r["subject"],
            "content": r["content"],
            "category": r["category"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"]
        }
        for r in rows
    ]

def db_save_custom_templates(templates, user_id=1):
    conn = get_tenant_db(user_id)
    c = conn.cursor()
    c.execute("DELETE FROM templates")
    for t in templates:
        c.execute("""
        INSERT INTO templates (id, name, subject, content, category, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            str(t.get("id", uuid.uuid4()))[:8],
            t.get("name", "Modèle"),
            t.get("subject", ""),
            t.get("content", ""),
            t.get("category", "general"),
            t.get("created_at", time.strftime("%d/%m/%Y")),
            t.get("updated_at", time.strftime("%d/%m/%Y"))
        ))
    conn.commit()
    conn.close()

def db_load_scheduled_tasks(user_id=1):
    conn = get_tenant_db(user_id)
    c = conn.cursor()
    c.execute("SELECT * FROM scheduled_tasks ORDER BY rowid DESC")
    rows = c.fetchall()
    conn.close()
    res = []
    for r in rows:
        try:
            payload = json.loads(r["payload_json"]) if r["payload_json"] else {}
        except Exception:
            payload = {}
        payload["id"] = r["id"]
        payload["title"] = r["title"]
        payload["scheduled_time"] = r["scheduled_time"]
        payload["status"] = r["status"]
        res.append(payload)
    return res

def db_save_scheduled_tasks(tasks, user_id=1):
    conn = get_tenant_db(user_id)
    c = conn.cursor()
    c.execute("DELETE FROM scheduled_tasks")
    for t in tasks:
        c.execute("""
        INSERT INTO scheduled_tasks (id, title, scheduled_time, status, payload_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            str(t.get("id", uuid.uuid4()))[:8],
            t.get("title", t.get("subject", "Campagne")),
            t.get("scheduled_time", ""),
            t.get("status", "pending"),
            json.dumps(t, ensure_ascii=False),
            t.get("created_at", time.strftime("%d/%m/%Y"))
        ))
    conn.commit()
    conn.close()

def db_load_certificate_config(user_id=1):
    conn = get_tenant_db(user_id)
    c = conn.cursor()
    c.execute("SELECT key, value FROM certificate_config")
    rows = c.fetchall()
    conn.close()
    default_cfg = {
        "enabled": False,
        "template_type": "epik_leaders",
        "output_format": "pdf",
        "name_var": "",
        "event_title": "Formation Création de Contenu",
        "subtitle": "En reconnaissance de sa participation active et assidue à la session de formation :",
        "issuer_name": "Club Scientifique EPIK Leaders & ISIMS",
        "date_str": "23 Novembre 2026",
        "font_color": "#110b07",
        "font_size": 38,
        "name_y_pct": 45.3,
        "custom_bg_base64": "",
        "filename_pattern": "Certificat_{Nom}.pdf"
    }
    if not rows:
        return default_cfg
    res = dict(default_cfg)
    for r in rows:
        try:
            res[r["key"]] = json.loads(r["value"])
        except Exception:
            res[r["key"]] = r["value"]
    return res

def db_save_certificate_config(cfg, user_id=1):
    conn = get_tenant_db(user_id)
    c = conn.cursor()
    for k, v in cfg.items():
        c.execute("INSERT OR REPLACE INTO certificate_config (key, value) VALUES (?, ?)", (k, json.dumps(v, ensure_ascii=False)))
    conn.commit()
    conn.close()
