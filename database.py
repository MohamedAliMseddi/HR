"""
MailStorm - Database & Authentication Module (SQLite)
Gère le stockage persistant et l'authentification sécurisée des utilisateurs.
"""

import os
import sqlite3
import hashlib
import secrets
import json
import time
import uuid

DB_FILE = os.path.join(os.path.dirname(__file__), "mailstorm.db")

def get_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password, salt=None):
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000).hex()
    return hashed, salt

def verify_password(password, stored_hash, salt):
    hashed, _ = hash_password(password, salt)
    return secrets.compare_digest(hashed, stored_hash)

def init_db():
    conn = get_db()
    c = conn.cursor()

    # 1. Users Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE,
        display_name TEXT,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        role TEXT DEFAULT 'admin',
        created_at TEXT,
        last_login TEXT
    )
    """)

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

    # 3. Settings / Config Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS config (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    # 4. Signatures Table
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

    # 5. Templates Table
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

    # 6. Contact Lists Table
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

    # 7. Campaign History Table
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

    # 8. Scheduled Tasks Table
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

    # 9. Certificate Configuration Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS certificate_config (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    conn.commit()

    # Initialize default admin user if none exists
    c.execute("SELECT COUNT(*) as count FROM users")
    if c.fetchone()["count"] == 0:
        pwd_hash, salt = hash_password("admin123")
        c.execute("""
        INSERT INTO users (username, email, display_name, password_hash, salt, role, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("admin", "admin@mailstorm.local", "Mohamed Ali Mseddi", pwd_hash, salt, "admin", time.strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        print("✓ Compte administrateur par défaut initialisé : Identifiant: 'admin' / Mot de passe: 'admin123'")

    conn.close()

    # Run migrations from legacy JSON files
    migrate_from_json_files()

def migrate_from_json_files():
    base_dir = os.path.dirname(__file__)
    conn = get_db()
    c = conn.cursor()

    # 1. Config migration
    config_file = os.path.join(base_dir, "config.json")
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            for k, v in cfg.items():
                c.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (k, json.dumps(v, ensure_ascii=False)))
            conn.commit()
        except Exception as e:
            print(f"Erreur migration config.json: {e}")

    # 2. Signatures migration
    sig_file = os.path.join(base_dir, "signatures.json")
    if os.path.exists(sig_file):
        try:
            with open(sig_file, "r", encoding="utf-8") as f:
                sigs = json.load(f)
            for s in sigs:
                c.execute("""
                INSERT OR REPLACE INTO signatures (id, name, content, is_default, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    s.get("id", str(uuid.uuid4())),
                    s.get("name", "Signature"),
                    s.get("content", ""),
                    1 if s.get("is_default") else 0,
                    s.get("created_at", time.strftime("%d/%m/%Y")),
                    s.get("updated_at", time.strftime("%d/%m/%Y"))
                ))
            conn.commit()
        except Exception as e:
            print(f"Erreur migration signatures.json: {e}")

    # 3. Custom Templates migration
    tpl_file = os.path.join(base_dir, "custom_templates.json")
    if os.path.exists(tpl_file):
        try:
            with open(tpl_file, "r", encoding="utf-8") as f:
                tpls = json.load(f)
            for t in tpls:
                c.execute("""
                INSERT OR REPLACE INTO templates (id, name, subject, content, category, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    t.get("id", str(uuid.uuid4())),
                    t.get("name", "Modèle"),
                    t.get("subject", ""),
                    t.get("content", ""),
                    t.get("category", "general"),
                    t.get("created_at", time.strftime("%d/%m/%Y")),
                    t.get("updated_at", time.strftime("%d/%m/%Y"))
                ))
            conn.commit()
        except Exception as e:
            print(f"Erreur migration custom_templates.json: {e}")

    # 4. Contact Lists migration
    lists_file = os.path.join(base_dir, "contact_lists.json")
    if os.path.exists(lists_file):
        try:
            with open(lists_file, "r", encoding="utf-8") as f:
                lists = json.load(f)
            for l in lists:
                contacts = l.get("contacts", [])
                c.execute("""
                INSERT OR REPLACE INTO contact_lists (id, name, count, contacts_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    l.get("id", str(uuid.uuid4())),
                    l.get("name", "Liste"),
                    l.get("count", len(contacts)),
                    json.dumps(contacts, ensure_ascii=False),
                    l.get("created_at", time.strftime("%d/%m/%Y")),
                    l.get("updated_at", time.strftime("%d/%m/%Y"))
                ))
            conn.commit()
        except Exception as e:
            print(f"Erreur migration contact_lists.json: {e}")

    # 5. History migration
    hist_file = os.path.join(base_dir, "history.json")
    if os.path.exists(hist_file):
        try:
            with open(hist_file, "r", encoding="utf-8") as f:
                hist = json.load(f)
            for h in hist:
                c.execute("""
                INSERT OR REPLACE INTO history (id, date, subject, provider, total, sent, failed, duration, logs_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(h.get("id", uuid.uuid4())),
                    h.get("date", time.strftime("%d/%m/%Y à %H:%M")),
                    h.get("subject", ""),
                    h.get("provider", "brevo"),
                    int(h.get("total", 0)),
                    int(h.get("sent", 0)),
                    int(h.get("failed", 0)),
                    h.get("duration", "0s"),
                    json.dumps(h.get("logs", []), ensure_ascii=False),
                    h.get("date", "")
                ))
            conn.commit()
        except Exception as e:
            print(f"Erreur migration history.json: {e}")

    # 6. Scheduled Tasks migration
    sched_file = os.path.join(base_dir, "scheduled_tasks.json")
    if os.path.exists(sched_file):
        try:
            with open(sched_file, "r", encoding="utf-8") as f:
                scheds = json.load(f)
            for s in scheds:
                c.execute("""
                INSERT OR REPLACE INTO scheduled_tasks (id, title, scheduled_time, status, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    str(s.get("id", uuid.uuid4())),
                    s.get("title", "Tâche"),
                    s.get("scheduled_time", ""),
                    s.get("status", "pending"),
                    json.dumps(s, ensure_ascii=False),
                    s.get("created_at", time.strftime("%d/%m/%Y"))
                ))
            conn.commit()
        except Exception as e:
            print(f"Erreur migration scheduled_tasks.json: {e}")

    # 7. Certificate Config migration
    cert_file = os.path.join(base_dir, "certificate_config.json")
    if os.path.exists(cert_file):
        try:
            with open(cert_file, "r", encoding="utf-8") as f:
                cert_cfg = json.load(f)
            for k, v in cert_cfg.items():
                c.execute("INSERT OR REPLACE INTO certificate_config (key, value) VALUES (?, ?)", (k, json.dumps(v, ensure_ascii=False)))
            conn.commit()
        except Exception as e:
            print(f"Erreur migration certificate_config.json: {e}")

    conn.close()

# User & Auth Helper Functions
def authenticate_user(username_or_email, password):
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
        # Update last login
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
    SELECT u.id, u.username, u.email, u.display_name, u.role
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
    # Revoke other sessions
    c.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

# Database CRUD Operations for MailStorm
def db_load_config():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT key, value FROM config")
    rows = c.fetchall()
    conn.close()
    res = {
        "provider": "brevo",
        "sender_email": "",
        "gmail_address": "",
        "app_password": "",
        "brevo_api_key": "",
        "sender_name": "",
        "default_delay": 2,
        "email_signature": "",
        "include_signature": True
    }
    for r in rows:
        try:
            res[r["key"]] = json.loads(r["value"])
        except Exception:
            res[r["key"]] = r["value"]
    return res

def db_save_config(data):
    current = db_load_config()
    current.update(data)
    conn = get_db()
    c = conn.cursor()
    for k, v in current.items():
        c.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (k, json.dumps(v, ensure_ascii=False)))
    conn.commit()
    conn.close()
    return current

def db_load_signatures():
    conn = get_db()
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

def db_save_signatures(sigs):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM signatures")
    for s in sigs:
        c.execute("""
        INSERT INTO signatures (id, name, content, is_default, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            s.get("id", str(uuid.uuid4())),
            s.get("name", "Signature"),
            s.get("content", ""),
            1 if s.get("is_default") else 0,
            s.get("created_at", time.strftime("%d/%m/%Y")),
            s.get("updated_at", time.strftime("%d/%m/%Y"))
        ))
    conn.commit()
    conn.close()

def db_load_history():
    conn = get_db()
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

def db_save_campaign_to_history(entry):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
    INSERT INTO history (id, date, subject, provider, total, sent, failed, duration, logs_json, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        str(entry.get("id", uuid.uuid4())),
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

def db_clear_history():
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM history")
    conn.commit()
    conn.close()

def db_delete_history_item(camp_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM history WHERE id = ?", (str(camp_id),))
    conn.commit()
    conn.close()

def db_load_contact_lists():
    conn = get_db()
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

def db_save_contact_lists(lists):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM contact_lists")
    for l in lists:
        contacts = l.get("contacts", [])
        c.execute("""
        INSERT INTO contact_lists (id, name, count, contacts_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            str(l.get("id", uuid.uuid4())),
            l.get("name", "Liste"),
            l.get("count", len(contacts)),
            json.dumps(contacts, ensure_ascii=False),
            l.get("created_at", time.strftime("%d/%m/%Y")),
            l.get("updated_at", time.strftime("%d/%m/%Y"))
        ))
    conn.commit()
    conn.close()

def db_load_custom_templates():
    conn = get_db()
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

def db_save_custom_templates(templates):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM templates")
    for t in templates:
        c.execute("""
        INSERT INTO templates (id, name, subject, content, category, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            str(t.get("id", uuid.uuid4())),
            t.get("name", "Modèle"),
            t.get("subject", ""),
            t.get("content", ""),
            t.get("category", "general"),
            t.get("created_at", time.strftime("%d/%m/%Y")),
            t.get("updated_at", time.strftime("%d/%m/%Y"))
        ))
    conn.commit()
    conn.close()

def db_load_scheduled_tasks():
    conn = get_db()
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

def db_save_scheduled_tasks(tasks):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM scheduled_tasks")
    for t in tasks:
        c.execute("""
        INSERT INTO scheduled_tasks (id, title, scheduled_time, status, payload_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            str(t.get("id", uuid.uuid4())),
            t.get("title", t.get("subject", "Campagne")),
            t.get("scheduled_time", ""),
            t.get("status", "pending"),
            json.dumps(t, ensure_ascii=False),
            t.get("created_at", time.strftime("%d/%m/%Y"))
        ))
    conn.commit()
    conn.close()

def db_load_certificate_config():
    conn = get_db()
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

def db_save_certificate_config(cfg):
    conn = get_db()
    c = conn.cursor()
    for k, v in cfg.items():
        c.execute("INSERT OR REPLACE INTO certificate_config (key, value) VALUES (?, ?)", (k, json.dumps(v, ensure_ascii=False)))
    conn.commit()
    conn.close()
