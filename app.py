"""
MailStorm - Gmail Bulk Email Sender
Application Web locale développée en Python
"""

import os
import sys
import json
import time
import datetime
import ssl
import smtplib
import re
import threading
import webbrowser
import base64
import io
import uuid
import urllib.request
import urllib.error
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from email.utils import make_msgid, formatdate
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

PORT = int(os.environ.get("PORT", 5000))
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")
LOGS_FILE = os.path.join(os.path.dirname(__file__), "history.json")
LISTS_FILE = os.path.join(os.path.dirname(__file__), "contact_lists.json")
SCHEDULED_FILE = os.path.join(os.path.dirname(__file__), "scheduled_tasks.json")
TEMPLATES_FILE = os.path.join(os.path.dirname(__file__), "custom_templates.json")
SIGNATURES_FILE = os.path.join(os.path.dirname(__file__), "signatures.json")
CERTIFICATE_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "certificate_config.json")

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# État global de l'envoi en cours
campaign_state = {
    "is_running": False,
    "should_stop": False,
    "total": 0,
    "sent": 0,
    "failed": 0,
    "current_index": 0,
    "current_email": "",
    "logs": [],
    "start_time": None,
    "end_time": None
}
state_lock = threading.Lock()

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {
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

def save_config(data):
    current = load_config()
    current.update(data)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2, ensure_ascii=False)

def load_history():
    if os.path.exists(LOGS_FILE):
        try:
            with open(LOGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_campaign_to_history(entry):
    history = load_history()
    history.insert(0, entry)
    history = history[:50]  # Conserver les 50 dernières campagnes
    try:
        with open(LOGS_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Erreur sauvegarde historique: {e}")

def load_contact_lists():
    if os.path.exists(LISTS_FILE):
        try:
            with open(LISTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_contact_lists(lists):
    try:
        with open(LISTS_FILE, "w", encoding="utf-8") as f:
            json.dump(lists, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Erreur sauvegarde listes: {e}")

def load_scheduled_tasks():
    if os.path.exists(SCHEDULED_FILE):
        try:
            with open(SCHEDULED_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_scheduled_tasks(tasks):
    try:
        with open(SCHEDULED_FILE, "w", encoding="utf-8") as f:
            json.dump(tasks, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Erreur sauvegarde tâches programmées: {e}")

def load_custom_templates():
    if os.path.exists(TEMPLATES_FILE):
        try:
            with open(TEMPLATES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_custom_templates(templates):
    try:
        with open(TEMPLATES_FILE, "w", encoding="utf-8") as f:
            json.dump(templates, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Erreur sauvegarde modèles personnalisés: {e}")

def save_signatures(signatures):
    try:
        with open(SIGNATURES_FILE, "w", encoding="utf-8") as f:
            json.dump(signatures, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Erreur sauvegarde signatures: {e}")

def load_signatures():
    if os.path.exists(SIGNATURES_FILE):
        try:
            with open(SIGNATURES_FILE, "r", encoding="utf-8") as f:
                sigs = json.load(f)
                if isinstance(sigs, list) and len(sigs) > 0:
                    return sigs
        except Exception:
            pass

    # Migration from config.json or default presets initialization
    cfg = load_config()
    existing_sig = (cfg.get("email_signature") or "").strip()
    default_sigs = []

    if existing_sig:
        default_sigs.append({
            "id": "sig-migrated",
            "name": "Signature Actuelle",
            "content": existing_sig,
            "is_default": True,
            "created_at": time.strftime("%d/%m/%Y à %H:%M"),
            "updated_at": time.strftime("%d/%m/%Y à %H:%M")
        })
    else:
        default_sigs.append({
            "id": "sig-default",
            "name": "Signature Professionnelle",
            "content": """<div style="font-family: Arial, sans-serif; font-size: 13px; color: #334155; line-height: 1.5;">
  <p style="margin: 0; font-size: 15px; font-weight: bold; color: #1e293b;">Mohamed Ali Mseddi</p>
  <p style="margin: 2px 0 6px 0; color: #6366f1; font-weight: 600;">Responsable Partenariats & RH | EPIK Club</p>
  <p style="margin: 0; color: #64748b; font-size: 12px;">📞 +216 00 000 000 | ✉️ contact@epikclub.com</p>
  <p style="margin: 2px 0 0 0; color: #64748b; font-size: 12px;">🌐 <a href="https://epikclub.com" style="color: #6366f1; text-decoration: none; font-weight: 500;">epikclub.com</a> | 📍 Tunis, Tunisie</p>
</div>""",
            "is_default": True,
            "created_at": time.strftime("%d/%m/%Y à %H:%M"),
            "updated_at": time.strftime("%d/%m/%Y à %H:%M")
        })

    default_sigs.append({
        "id": "sig-minimal",
        "name": "Signature Personnelle / Courte",
        "content": """<p style="font-family: Arial, sans-serif; font-size: 13px; color: #475569; margin: 0;">
  Bien cordialement,<br>
  <strong>Mohamed Ali</strong><br>
  <span style="font-size: 11px; color: #94a3b8;">Envoyé via MailStorm</span>
</p>""",
        "is_default": False,
        "created_at": time.strftime("%d/%m/%Y à %H:%M"),
        "updated_at": time.strftime("%d/%m/%Y à %H:%M")
    })

    save_signatures(default_sigs)
    return default_sigs

def load_certificate_config():
    if os.path.exists(CERTIFICATE_CONFIG_FILE):
        try:
            with open(CERTIFICATE_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "enabled": False,
        "template_type": "prestige",
        "output_format": "pdf",
        "name_var": "",
        "event_title": "Formation Développement Web & IA 2026",
        "subtitle": "En reconnaissance de sa participation active et de son investissement remarquable.",
        "issuer_name": "EPIK ISIMS Club",
        "date_str": "",
        "font_color": "#0f172a",
        "font_size": 48,
        "name_y_pct": 48,
        "custom_bg_base64": "",
        "filename_pattern": "Certificat_{Nom}.pdf"
    }

def save_certificate_config(cfg):
    try:
        with open(CERTIFICATE_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Erreur sauvegarde config certificat: {e}")

def get_best_font(preferred_style="serif", size=36):
    if not HAS_PIL:
        return None
    serif_candidates = [
        "C:/Windows/Fonts/georgia.ttf",
        "C:/Windows/Fonts/times.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSerif.ttf"
    ]
    sans_candidates = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
    ]
    candidates = serif_candidates if preferred_style == "serif" else sans_candidates
    candidates = candidates + sans_candidates + serif_candidates

    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    try:
        return ImageFont.load_default()
    except Exception:
        return None

def extract_recipient_name(email, data=None, name_var=""):
    """
    Extrait intelligemment le nom du destinataire :
    1. Si l'utilisateur a spécifié une variable (ex: '{Prénom} {Nom}')
    2. Sinon, cherche dans les colonnes standard du fichier Excel/CSV
    3. En dernier recours, reconstruit un nom propre à partir du préfixe email (ex: 'ahmed.benali@gmail.com' -> 'Ahmed Benali')
    """
    if data and name_var:
        res = name_var
        for k, v in data.items():
            pattern = re.compile(re.escape("{" + str(k).strip() + "}"), re.IGNORECASE)
            res = pattern.sub(str(v or "").strip(), res)
        res = res.strip()
        if res:
            return res

    if data and isinstance(data, dict):
        for candidate_key in ["Nom_Complet", "Nom Complet", "Nom et Prénom", "Full Name", "FullName", "Participant", "Nom_Participant", "Name"]:
            for k in data.keys():
                if k.strip().lower() == candidate_key.lower():
                    val = str(data[k] or "").strip()
                    if val:
                        return val

        prenom = ""
        nom = ""
        for k in data.keys():
            kl = k.strip().lower()
            if kl in ("prenom", "prénom", "first name", "firstname"):
                prenom = str(data[k] or "").strip()
            elif kl in ("nom", "last name", "lastname"):
                nom = str(data[k] or "").strip()
        if prenom and nom:
            return f"{prenom} {nom}"
        elif nom:
            return nom
        elif prenom:
            return prenom

    prefix = email.split("@")[0] if "@" in email else email
    parts = re.split(r"[._\-+]+", prefix)
    words = []
    for p in parts:
        clean = re.sub(r"\d+", "", p).strip()
        if len(clean) >= 2:
            words.append(clean.capitalize())
    if words:
        return " ".join(words)
    return prefix.capitalize()

def generate_certificate_attachment(recipient_name, cert_config, recipient_data=None, recipient_email=""):
    """
    Génère un certificat personnalisé haute définition (PDF ou PNG)
    prêt à être envoyé comme pièce jointe.
    """
    if not HAS_PIL:
        raise RuntimeError("La bibliothèque Pillow (PIL) est requise pour générer des certificats.")

    width = 1200
    height = 850

    template_type = cert_config.get("template_type", "prestige")
    output_format = (cert_config.get("output_format") or "pdf").lower()
    event_title = cert_config.get("event_title") or "Formation Développement Web & IA 2026"
    subtitle = cert_config.get("subtitle") or "En reconnaissance de sa participation active et de son investissement remarquable."
    issuer_name = cert_config.get("issuer_name") or "EPIK ISIMS Club"
    date_str = cert_config.get("date_str") or time.strftime("%d/%m/%Y")
    font_color = cert_config.get("font_color") or "#0f172a"
    base_font_size = int(cert_config.get("font_size", 48))
    name_y_pct = float(cert_config.get("name_y_pct", 48))
    custom_bg_b64 = cert_config.get("custom_bg_base64", "")

    # Interpolate variables in text fields
    if recipient_data:
        for k, v in recipient_data.items():
            pattern = re.compile(re.escape("{" + str(k) + "}"), re.IGNORECASE)
            event_title = pattern.sub(str(v or ""), event_title)
            subtitle = pattern.sub(str(v or ""), subtitle)
            issuer_name = pattern.sub(str(v or ""), issuer_name)

    if template_type == "custom" and custom_bg_b64:
        try:
            clean_b64 = custom_bg_b64.split(",")[-1]
            raw_bg = base64.b64decode(clean_b64)
            img = Image.open(io.BytesIO(raw_bg)).convert("RGB")
            img = img.resize((width, height), Image.Resampling.LANCZOS)
        except Exception:
            img = Image.new("RGB", (width, height), "#ffffff")
    else:
        if template_type == "modern_tech":
            img = Image.new("RGB", (width, height), "#ffffff")
            draw = ImageDraw.Draw(img)
            draw.rectangle([0, 0, width, 16], fill="#4f46e5")
            draw.rectangle([0, 16, width, 22], fill="#818cf8")
            draw.rectangle([35, 45, width - 35, height - 45], outline="#e2e8f0", width=2)
            draw.rectangle([45, 55, width - 45, height - 55], outline="#6366f1", width=1)
            for cx, cy in [(45, 55), (width - 45, 55), (45, height - 55), (width - 45, height - 55)]:
                draw.rectangle([cx - 8, cy - 8, cx + 8, cy + 8], fill="#4f46e5")

            font_head = get_best_font("sans", 40)
            font_sub = get_best_font("sans", 16)
            font_desc = get_best_font("sans", 20)
            font_meta = get_best_font("sans", 16)

            draw.text((width//2, 130), "CERTIFICAT DE PARTICIPATION & RÉUSSITE", fill="#312e81", font=font_head, anchor="mm")
            draw.text((width//2, 175), "ATTESTATION OFFICIELLE DE FORMATION & HACKATHON", fill="#6366f1", font=font_sub, anchor="mm")
            draw.text((width//2, 245), "Le présent certificat est décerné avec distinction à :", fill="#64748b", font=font_desc, anchor="mm")

            draw.text((width//2, int(height * (name_y_pct / 100.0)) + 65), subtitle, fill="#475569", font=font_desc, anchor="mm")
            draw.text((width//2, int(height * (name_y_pct / 100.0)) + 105), event_title, fill="#312e81", font=font_head, anchor="mm")

            draw.line([(100, height - 105), (350, height - 105)], fill="#cbd5e1", width=1)
            draw.text((225, height - 85), f"Délivré le : {date_str}", fill="#64748b", font=font_meta, anchor="mm")

            draw.line([(width - 350, height - 105), (width - 100, height - 105)], fill="#cbd5e1", width=1)
            draw.text((width - 225, height - 85), f"Organisé par : {issuer_name}", fill="#312e81", font=font_meta, anchor="mm")

        elif template_type == "classic":
            img = Image.new("RGB", (width, height), "#fdfbf7")
            draw = ImageDraw.Draw(img)
            draw.rectangle([28, 28, width - 28, height - 28], outline="#78350f", width=5)
            draw.rectangle([40, 40, width - 40, height - 40], outline="#d97706", width=2)

            font_head = get_best_font("serif", 42)
            font_sub = get_best_font("serif", 17)
            font_desc = get_best_font("serif", 21)
            font_meta = get_best_font("serif", 16)

            draw.text((width//2, 140), "ATTESTATION DE RÉUSSITE", fill="#78350f", font=font_head, anchor="mm")
            draw.text((width//2, 185), "EN RECONNAISSANCE DE MÉRITE ET D'ENGAGEMENT", fill="#b45309", font=font_sub, anchor="mm")
            draw.text((width//2, 250), "Il est certifié par la présente que :", fill="#92400e", font=font_desc, anchor="mm")

            draw.text((width//2, int(height * (name_y_pct / 100.0)) + 65), subtitle, fill="#78350f", font=font_desc, anchor="mm")
            draw.text((width//2, int(height * (name_y_pct / 100.0)) + 105), event_title, fill="#451a03", font=font_head, anchor="mm")

            draw.line([(120, height - 105), (360, height - 105)], fill="#d97706", width=1)
            draw.text((240, height - 85), f"Fait le : {date_str}", fill="#92400e", font=font_meta, anchor="mm")

            draw.line([(width - 360, height - 105), (width - 120, height - 105)], fill="#d97706", width=1)
            draw.text((width - 240, height - 85), issuer_name, fill="#78350f", font=font_meta, anchor="mm")

        else:  # prestige (default)
            img = Image.new("RGB", (width, height), "#fcfbfa")
            draw = ImageDraw.Draw(img)

            draw.rectangle([25, 25, width - 25, height - 25], outline="#0f172a", width=6)
            draw.rectangle([38, 38, width - 38, height - 38], outline="#c59b27", width=3)
            for cx, cy in [(38, 38), (width - 38, 38), (38, height - 38), (width - 38, height - 38)]:
                draw.rectangle([cx - 8, cy - 8, cx + 8, cy + 8], fill="#c59b27")

            font_head = get_best_font("serif", 44)
            font_sub = get_best_font("serif", 16)
            font_desc = get_best_font("serif", 21)
            font_meta = get_best_font("serif", 16)

            draw.ellipse([width//2 - 40, 65, width//2 + 40, 145], fill="#0f172a", outline="#c59b27", width=3)
            draw.text((width//2, 105), "★", fill="#c59b27", font=font_head, anchor="mm")

            draw.text((width//2, 185), "CERTIFICAT D'EXCELLENCE", fill="#0f172a", font=font_head, anchor="mm")
            draw.text((width//2, 230), "CE CERTIFICAT EST FIÈREMENT DÉCERNÉ À :", fill="#64748b", font=font_sub, anchor="mm")

            draw.text((width//2, int(height * (name_y_pct / 100.0)) + 65), subtitle, fill="#475569", font=font_desc, anchor="mm")
            draw.text((width//2, int(height * (name_y_pct / 100.0)) + 105), event_title, fill="#0f172a", font=font_head, anchor="mm")

            draw.line([(120, height - 110), (380, height - 110)], fill="#94a3b8", width=1)
            draw.text((250, height - 90), f"Délivré le : {date_str}", fill="#64748b", font=font_meta, anchor="mm")

            draw.line([(width - 380, height - 110), (width - 120, height - 110)], fill="#94a3b8", width=1)
            draw.text((width - 250, height - 90), issuer_name, fill="#0f172a", font=font_meta, anchor="mm")

    # Draw Recipient Name with auto-scaling
    draw = ImageDraw.Draw(img)
    target_y = int(height * (name_y_pct / 100.0))
    target_x = int(width * 0.5)

    current_size = base_font_size
    name_font = get_best_font("serif" if template_type in ("prestige", "classic") else "sans", current_size)
    while current_size > 20:
        name_font = get_best_font("serif" if template_type in ("prestige", "classic") else "sans", current_size)
        bbox = draw.textbbox((target_x, target_y), recipient_name, font=name_font, anchor="mm")
        if (bbox[2] - bbox[0]) <= (width - 220):
            break
        current_size -= 4

    draw.text((target_x, target_y), recipient_name, fill=font_color, font=name_font, anchor="mm")

    if template_type in ("prestige", "modern_tech"):
        name_bbox = draw.textbbox((target_x, target_y), recipient_name, font=name_font, anchor="mm")
        under_y = name_bbox[3] + 8
        line_color = "#c59b27" if template_type == "prestige" else "#6366f1"
        line_half_w = min(max((name_bbox[2] - name_bbox[0]) // 2 + 30, 100), 300)
        draw.line([(target_x - line_half_w, under_y), (target_x + line_half_w, under_y)], fill=line_color, width=2)

    out_buf = io.BytesIO()
    if output_format == "png":
        img.save(out_buf, format="PNG")
        mime = "image/png"
        ext = "png"
    else:
        img.save(out_buf, format="PDF")
        mime = "application/pdf"
        ext = "pdf"

    raw_bytes = out_buf.getvalue()
    b64_str = base64.b64encode(raw_bytes).decode("utf-8")

    safe_name = re.sub(r"[^\w\s-]", "", recipient_name).strip().replace(" ", "_")
    if not safe_name:
        safe_name = "Participant"
    filename = f"Certificat_{safe_name}.{ext}"

    return {
        "name": filename,
        "data": f"data:{mime};base64,{b64_str}",
        "content_bytes": raw_bytes,
        "mime": mime
    }

def evaluate_spam_score(subject, content_html):
    subject = (subject or "").strip()
    content_html = (content_html or "").strip()
    clean_body = re.sub(r'<[^>]+>', ' ', content_html)
    clean_body_normalized = ' '.join(clean_body.split())
    
    score = 100
    penalties = []
    bonuses = []
    recommendations = []

    # 1. Subject checks
    if not subject:
        score -= 35
        penalties.append({"rule": "Sujet manquant", "penalty": 35, "desc": "L'objet de l'email est vide. Les filtres anti-spam rejettent systématiquement les emails sans objet."})
        recommendations.append("Ajoutez un objet précis et accrocheur décrivant clairement votre message.")
    else:
        subj_len = len(subject)
        if subj_len < 6:
            score -= 15
            penalties.append({"rule": "Sujet trop court", "penalty": 15, "desc": f"L'objet ne fait que {subj_len} caractères. Un objet trop court est suspect."})
            recommendations.append("Développez votre objet pour qu'il contienne au moins 15 à 20 caractères.")
        elif subj_len > 80:
            score -= 8
            penalties.append({"rule": "Sujet trop long", "penalty": 8, "desc": f"L'objet fait {subj_len} caractères. Il risque d'être tronqué sur smartphone."})
            recommendations.append("Raccourcissez l'objet sous 65 caractères pour un confort de lecture optimal.")
        else:
            bonuses.append({"rule": "Longueur d'objet idéale", "bonus": 5, "desc": f"Longueur parfaite ({subj_len} car.) pour smartphone et boîte de réception."})

        # All-caps check
        letters = [c for c in subject if c.isalpha()]
        if len(letters) >= 6:
            upper_count = sum(1 for c in letters if c.isupper())
            upper_ratio = upper_count / len(letters)
            if upper_ratio > 0.35:
                score -= 20
                penalties.append({"rule": "Trop de MAJUSCULES dans l'objet", "penalty": 20, "desc": f"{int(upper_ratio*100)}% de lettres en majuscules. Un signal de spam majeur pour Gmail."})
                recommendations.append("Écrivez votre objet en minuscules standard (gardez une seule majuscule au début).")

        # Punctuation check
        if re.search(r'[!?]{2,}', subject):
            score -= 15
            penalties.append({"rule": "Ponctuation excessive dans l'objet", "penalty": 15, "desc": "Présence de points consécutifs répétés (ex: !!, ??)."})
            recommendations.append("Supprimez les points d'exclamation ou d'interrogation multiples dans l'objet.")

        if any(sym in subject for sym in ["$$", "€€", "££", "💰"]):
            score -= 12
            penalties.append({"rule": "Symboles monétaires agressifs", "penalty": 12, "desc": "Présence de symboles de monnaie répétés ($$, €€) dans l'objet."})
            recommendations.append("Évitez les symboles d'argent dans l'objet de vos emails professionnels.")

    # 2. Body checks
    if not clean_body_normalized or len(clean_body_normalized) < 25:
        score -= 30
        penalties.append({"rule": "Corps du message quasi vide", "penalty": 30, "desc": "Le message contient moins de 25 caractères de texte."})
        recommendations.append("Ajoutez du contenu textuel informatif structuré en paragraphes.")
    else:
        if re.search(r'!{3,}', clean_body_normalized):
            score -= 10
            penalties.append({"rule": "Ponctuation agressive dans le corps", "penalty": 10, "desc": "Points d'exclamation répétés (!!!) dans le corps du texte."})
            recommendations.append("Utilisez une ponctuation simple et soignée dans le corps de votre email.")

    # 3. Spam trigger keywords
    SPAM_TRIGGER_LIST = [
        ("100% gratuit", "100% gratuit"),
        ("100% garanti", "100% garanti"),
        ("gratuit", "gratuit"),
        ("argent facile", "argent facile"),
        ("gagner de l'argent", "gagner de l'argent"),
        ("devenir riche", "devenir riche"),
        ("gagner", "gagner"),
        ("bénéfice immédiat", "bénéfice immédiat"),
        ("satisfait ou remboursé", "satisfait ou remboursé"),
        ("remboursement", "remboursement"),
        ("cliquez ici", "cliquez ici"),
        ("cliquez vite", "cliquez vite"),
        ("offre exceptionnelle", "offre exceptionnelle"),
        ("offre limitée", "offre limitée"),
        ("sans engagement", "sans engagement"),
        ("urgent", "urgent"),
        ("action immédiate", "action immédiate"),
        ("félicitations vous avez", "félicitations vous avez"),
        ("gains", "gains"),
        ("loterie", "loterie"),
        ("casino", "casino"),
        ("crypto gratuite", "crypto gratuite"),
        ("prêt rapide", "prêt rapide"),
        ("crédit sans justificatif", "crédit sans justificatif"),
        ("viagra", "viagra"),
        ("click here", "click here"),
        ("buy now", "buy now"),
        ("free money", "free money"),
        ("earn money", "earn money"),
        ("winner", "winner"),
        ("risk free", "risk free"),
        ("cash bonus", "cash bonus")
    ]

    full_text_lower = f"{subject.lower()} {clean_body_normalized.lower()}"
    detected_spam_words = []
    for word, label in SPAM_TRIGGER_LIST:
        if re.search(r'\b' + re.escape(word) + r'\b', full_text_lower, re.IGNORECASE):
            if label not in detected_spam_words:
                detected_spam_words.append(label)

    if detected_spam_words:
        spam_penalty = min(35, len(detected_spam_words) * 8)
        score -= spam_penalty
        penalties.append({
            "rule": f"Mots déclencheurs de spam ({len(detected_spam_words)})",
            "penalty": spam_penalty,
            "desc": f"Termes identifiés : {', '.join(detected_spam_words[:4])}{'...' if len(detected_spam_words) > 4 else ''}."
        })
        recommendations.append(f"Remplacez les termes suspects ({', '.join(detected_spam_words[:3])}) par des formulations plus professionnelles.")

    # 4. Bonuses
    # Personalization tags detected
    if re.search(r'\{(nom|prénom|prenom|email|club|poste|[a-zA-Z0-9_-]+)\}', f"{subject} {content_html}", re.IGNORECASE):
        bonuses.append({
            "rule": "Personnalisation dynamique activée",
            "bonus": 8,
            "desc": "L'email contient des variables ({Nom}, {Prénom}, etc.). Les serveurs de messagerie récompensent les emails personnalisés."
        })

    # Polite closing / signature detection
    polite_words = ["cordialement", "bonne journée", "sincères salutations", "l'équipe", "au plaisir", "chaleureusement", "restant à votre", "bien à vous", "merci"]
    if any(pw in clean_body_normalized.lower() for pw in polite_words) or ("<div" in content_html and "border-top" in content_html):
        bonuses.append({
            "rule": "Signature & politesse professionnelles",
            "bonus": 6,
            "desc": "Présence d'une formule de politesse ou d'une signature d'email soignée."
        })

    # Healthy HTML structure
    if "<p" in content_html or "<div" in content_html or "<h" in content_html:
        bonuses.append({
            "rule": "Structure HTML équilibrée",
            "bonus": 4,
            "desc": "Le message est bien aéré et structuré avec des balises HTML claires."
        })

    final_score = max(5, min(100, score))
    if final_score >= 85:
        verdict = "excellent"
        label = "🟢 Excellente délivrabilité (Boîte de réception garantie)"
        color = "emerald"
    elif final_score >= 65:
        verdict = "medium"
        label = "🟡 Délivrabilité modérée (Quelques optimisations conseillées)"
        color = "amber"
    else:
        verdict = "danger"
        label = "🔴 Risque de Spam important (À corriger impérativement)"
        color = "rose"

    return {
        "score": final_score,
        "verdict": verdict,
        "label": label,
        "color": color,
        "penalties": penalties,
        "bonuses": bonuses,
        "recommendations": recommendations,
        "stats": {
            "subject_length": len(subject),
            "body_length": len(clean_body_normalized),
            "spam_words_count": len(detected_spam_words)
        }
    }

def apply_template_variables(text, rec_email, rec_data=None):
    """
    Remplace les variables standards ({email}, {date}) ainsi que toutes les
    colonnes dynamiques issues d'un fichier Excel ({Nom}, {Prénom}, {Club}, etc.)
    """
    if not text:
        return ""
    result = text.replace("{email}", rec_email).replace("{EMAIL}", rec_email)
    result = result.replace("{date}", time.strftime("%d/%m/%Y")).replace("{DATE}", time.strftime("%d/%m/%Y"))
    
    if isinstance(rec_data, dict):
        for k, v in rec_data.items():
            k_str = str(k).strip()
            if k_str.lower() in ("email", "mail"):
                continue
            val_str = str(v) if v is not None else ""
            pattern = re.compile(re.escape("{" + k_str + "}"), re.IGNORECASE)
            result = pattern.sub(val_str, result)
    return result

def verify_brevo_credentials(api_key):
    """
    Vérifie la clé API Brevo via HTTPS (Port 443 - Ouvert partout dans le Cloud)
    """
    clean_key = api_key.strip().replace(" ", "").replace('"', '').replace("'", "")
    if not clean_key:
        return False, "Veuillez saisir votre clé API Brevo."

    if len(clean_key) < 80:
        return False, (
            f"Clé API incomplète ({len(clean_key)} car. au lieu de 89). "
            "Brevo masque la fin de la clé dans la liste ! "
            "Veuillez générer une NOUVELLE clé sur brevo.com et cliquer impérativement sur le bouton « Copier » 📋 dans le pop-up avant de le fermer."
        )

    endpoints = [
        "https://api.brevo.com/v3/smtp/statistics/reports",
        "https://api.brevo.com/v3/senders",
        "https://api.brevo.com/v3/smtp/templates",
        "https://api.brevo.com/v3/account"
    ]

    last_error = ""
    had_403 = False

    for ep in endpoints:
        req = urllib.request.Request(
            ep,
            headers={
                "accept": "application/json",
                "api-key": clean_key,
                "User-Agent": "MailStorm/1.0"
            },
            method="GET"
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                return True, "Connexion réussie à Brevo ! Clé API valide et Port 443 HTTPS prêt."
        except urllib.error.HTTPError as e:
            try:
                err_body = json.loads(e.read().decode("utf-8"))
                msg = err_body.get("message", str(e))
            except Exception:
                msg = str(e)
            
            if "unrecognised IP" in msg or "authorised_ips" in msg:
                return False, (
                    "Sécurité Brevo (IP Render détectée) : Brevo demande d'autoriser l'IP du serveur cloud Render. "
                    "Ouvrez ce lien : https://app.brevo.com/security/authorised_ips et cliquez sur « Désactiver le blocage » "
                    "(ou ouvrez le mail d'alerte reçu sur votre Gmail et cliquez sur « Autoriser cette IP »)."
                )
            
            last_error = f"{msg} (HTTP {e.code})"
            
            if e.code == 403:
                # 403 signifie que la clé existe et est authentifiée, mais a des permissions restreintes
                had_403 = True
                continue
            elif e.code == 401:
                continue
            else:
                return False, f"Erreur Brevo ({e.code}) : {msg}"
        except Exception as e:
            last_error = str(e)
            continue

    if had_403:
        # La clé a été reconnue et authentifiée par Brevo (code 403 au lieu de 401)
        return True, "Clé API Brevo reconnue avec succès ! Prête pour l'envoi d'emails."

    return False, f"Clé Brevo invalide ou non reconnue : {last_error}. Générez une nouvelle clé sur brevo.com."

def send_single_email_brevo(api_key, sender_email, sender_name, recipient, subject, content_html, attachments=None, recipient_data=None):
    """
    Envoie un email via l'API REST de Brevo (HTTPS Port 443) avec support des variables Excel
    """
    clean_key = api_key.strip()
    
    personalized_subject = apply_template_variables(subject, recipient, recipient_data)
    personalized_content = apply_template_variables(content_html, recipient, recipient_data)

    payload = {
        "sender": {
            "name": sender_name or sender_email,
            "email": sender_email
        },
        "replyTo": {
            "name": sender_name or sender_email,
            "email": sender_email
        },
        "to": [
            {"email": recipient}
        ],
        "subject": personalized_subject,
        "htmlContent": personalized_content
    }

    if attachments:
        att_list = []
        for att in attachments:
            name = att.get("name", "attachment")
            b64_data = att.get("data", "")
            if b64_data:
                clean_b64 = b64_data.split(",")[-1]
                att_list.append({
                    "name": name,
                    "content": clean_b64
                })
        if att_list:
            payload["attachment"] = att_list

    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=req_data,
        headers={
            "accept": "application/json",
            "content-type": "application/json",
            "api-key": clean_key,
            "User-Agent": "MailStorm/1.0"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status not in (200, 201, 202):
                raise Exception(f"Brevo API error: Code {resp.status}")
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
            err_msg = err_body.get("message", str(e))
        except Exception:
            err_msg = str(e)
        if "unrecognised IP" in err_msg or "authorised_ips" in err_msg:
            raise Exception("Sécurité Brevo : Adresse IP Render bloquée. Désactivez le blocage IP sur app.brevo.com/security/authorised_ips ou autorisez l'IP dans l'email reçu.")
        raise Exception(f"Brevo: {err_msg}")

def verify_gmail_credentials(email_address, app_password):
    """
    Vérifie la connexion SMTP avec Gmail (Port 587 + TLS)
    """
    clean_password = app_password.replace(" ", "")
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(email_address, clean_password)
            return True, "Connexion réussie avec succès à Gmail !"
    except smtplib.SMTPAuthenticationError:
        return False, "Erreur d'authentification (535) : Email ou Mot de passe d'application incorrect. Vérifiez que vous utilisez bien un mot de passe d'application Google de 16 lettres."
    except smtplib.SMTPConnectError:
        return False, "Impossible de se connecter au serveur SMTP de Gmail (smtp.gmail.com:587). Vérifiez votre connexion Internet."
    except Exception as e:
        return False, f"Erreur de connexion : {str(e)}"

def send_single_email(sender_email, app_password, sender_name, recipient, subject, content_html, attachments=None, recipient_data=None):
    """
    Envoie un seul email via Gmail SMTP avec support des variables Excel
    """
    clean_password = app_password.replace(" ", "")

    personalized_subject = apply_template_variables(subject, recipient, recipient_data)
    personalized_content = apply_template_variables(content_html, recipient, recipient_data)
    
    msg = MIMEMultipart("mixed")
    if sender_name:
        msg["From"] = f"{sender_name} <{sender_email}>"
    else:
        msg["From"] = sender_email
    msg["To"] = recipient
    msg["Subject"] = personalized_subject

    # En-têtes RFC standards pour chaque email
    domain = sender_email.split("@")[-1] if "@" in sender_email else "gmail.com"
    msg["Message-ID"] = make_msgid(domain=domain)
    msg["Date"] = formatdate(localtime=True)
    msg["X-Entity-Ref-ID"] = str(uuid.uuid4())

    # Corps de l'email (HTML + Alternative texte)
    alt_part = MIMEMultipart("alternative")
    
    # Texte brut de secours (enlever les balises HTML basiques)
    clean_text = re.sub(r'<[^>]+>', ' ', personalized_content)
    alt_part.attach(MIMEText(clean_text, "plain", "utf-8"))
    alt_part.attach(MIMEText(personalized_content, "html", "utf-8"))
    msg.attach(alt_part)

    # Pièces jointes si présentes
    if attachments:
        for att in attachments:
            name = att.get("name", "attachment")
            b64_data = att.get("data", "")
            if b64_data:
                try:
                    file_data = base64.b64decode(b64_data.split(",")[-1])
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(file_data)
                    encoders.encode_base64(part)
                    part.add_header("Content-Disposition", f'attachment; filename="{name}"')
                    msg.attach(part)
                except Exception as e:
                    print(f"Erreur pièce jointe {name}: {e}")

    # Connexion et envoi
    context = ssl.create_default_context()
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as server:
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        server.login(sender_email, clean_password)
        server.send_message(msg)

def worker_campaign(recipients, subject, content_html, provider, sender_email, sender_name, app_password, brevo_api_key, delay_seconds, attachments, cert_config=None):
    global campaign_state
    
    with state_lock:
        campaign_state["is_running"] = True
        campaign_state["should_stop"] = False
        campaign_state["total"] = len(recipients)
        campaign_state["sent"] = 0
        campaign_state["failed"] = 0
        campaign_state["current_index"] = 0
        campaign_state["logs"] = []
        campaign_state["start_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
        campaign_state["end_time"] = None

    for idx, item in enumerate(recipients):
        if isinstance(item, dict):
            recipient_email = (item.get("email") or item.get("Email") or item.get("mail") or item.get("Mail") or "").strip()
            recipient_data = item
        else:
            recipient_email = str(item).strip()
            recipient_data = {"email": recipient_email}

        if not recipient_email or "@" not in recipient_email:
            continue

        with state_lock:
            if campaign_state["should_stop"]:
                campaign_state["logs"].append({
                    "time": time.strftime("%H:%M:%S"),
                    "email": "CAMPAGNE INTERROMPUE",
                    "status": "warning",
                    "details": "L'envoi a été arrêté par l'utilisateur."
                })
                break
            campaign_state["current_index"] = idx + 1
            campaign_state["current_email"] = recipient_email

        # Prepare attachments: static attachments + dynamic personalized certificate if enabled
        current_attachments = list(attachments) if attachments else []
        cert_info_msg = ""
        if cert_config and cert_config.get("enabled"):
            try:
                rec_name = extract_recipient_name(recipient_email, recipient_data, cert_config.get("name_var", ""))
                cert_att = generate_certificate_attachment(rec_name, cert_config, recipient_data, recipient_email)
                if cert_att:
                    current_attachments.append({
                        "name": cert_att["name"],
                        "data": cert_att["data"]
                    })
                    cert_info_msg = f" (Certificat : {cert_att['name']})"
            except Exception as ce:
                print(f"Erreur certificat pour {recipient_email}: {ce}")

        success = False
        error_msg = ""
        try:
            if provider == "brevo":
                send_single_email_brevo(
                    api_key=brevo_api_key,
                    sender_email=sender_email,
                    sender_name=sender_name,
                    recipient=recipient_email,
                    subject=subject,
                    content_html=content_html,
                    attachments=current_attachments,
                    recipient_data=recipient_data
                )
            else:
                send_single_email(
                    sender_email=sender_email,
                    app_password=app_password,
                    sender_name=sender_name,
                    recipient=recipient_email,
                    subject=subject,
                    content_html=content_html,
                    attachments=current_attachments,
                    recipient_data=recipient_data
                )
            success = True
        except Exception as e:
            error_msg = str(e)

        with state_lock:
            if success:
                campaign_state["sent"] += 1
                campaign_state["logs"].append({
                    "time": time.strftime("%H:%M:%S"),
                    "email": recipient_email,
                    "status": "success",
                    "details": f"Envoyé avec succès{cert_info_msg}"
                })
            else:
                campaign_state["failed"] += 1
                campaign_state["logs"].append({
                    "time": time.strftime("%H:%M:%S"),
                    "email": recipient_email,
                    "status": "error",
                    "details": error_msg or "Échec d'envoi"
                })

        # Pause entre les emails pour éviter d'être bloqué par Gmail
        if idx < len(recipients) - 1 and not campaign_state["should_stop"]:
            time.sleep(delay_seconds)

    with state_lock:
        campaign_state["is_running"] = False
        campaign_state["current_email"] = ""
        campaign_state["end_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
        tot = campaign_state["total"]
        snt = campaign_state["sent"]
        fld = campaign_state["failed"]
        logs_snapshot = list(campaign_state["logs"])
        start_t = campaign_state["start_time"]
        end_t = campaign_state["end_time"]

    # Sauvegarder automatiquement cette campagne dans l'historique
    save_campaign_to_history({
        "id": str(uuid.uuid4())[:8],
        "start_time": start_t,
        "end_time": end_t,
        "date_formatted": time.strftime("%d/%m/%Y à %H:%M"),
        "subject": subject,
        "content_html": content_html,
        "provider": provider,
        "total": tot,
        "sent": snt,
        "failed": fld,
        "success_rate": round((snt / tot * 100), 1) if tot > 0 else 0,
        "logs": logs_snapshot
    })


def scheduler_daemon():
    """
    Vérifie toutes les 10 secondes si une campagne programmée doit être déclenchée
    """
    while True:
        try:
            time.sleep(10)
            now = time.time()
            tasks = load_scheduled_tasks()
            changed = False
            for task in tasks:
                if task.get("status") == "pending" and task.get("scheduled_timestamp", 0) <= now:
                    with state_lock:
                        if not campaign_state["is_running"]:
                            task["status"] = "executing"
                            changed = True
                            save_scheduled_tasks(tasks)
                            
                            cfg = load_config()
                            provider = task.get("provider") or cfg.get("provider", "brevo")
                            sender_email = task.get("sender_email") or cfg.get("sender_email") or cfg.get("gmail_address", "")
                            sender_name = task.get("sender_name") or cfg.get("sender_name", "")
                            pwd = cfg.get("app_password", "")
                            brevo_key = cfg.get("brevo_api_key", "")
                            task_id = task.get("id")

                            def run_scheduled_job(t=task, tid=task_id, p=provider, se=sender_email, sn=sender_name, pw=pwd, bk=brevo_key):
                                try:
                                    worker_campaign(
                                        recipients=t.get("recipients", []),
                                        subject=t.get("subject", ""),
                                        content_html=t.get("content_html", ""),
                                        provider=p,
                                        sender_email=se,
                                        sender_name=sn,
                                        app_password=pw,
                                        brevo_api_key=bk,
                                        delay_seconds=float(t.get("delay", 2)),
                                        attachments=t.get("attachments", []),
                                        cert_config=t.get("certificate", {})
                                    )
                                    all_t = load_scheduled_tasks()
                                    for item in all_t:
                                        if item.get("id") == tid:
                                            item["status"] = "completed"
                                            item["completed_at"] = time.strftime("%d/%m/%Y à %H:%M")
                                    save_scheduled_tasks(all_t)
                                except Exception as exc:
                                    print(f"[SCHEDULER] Erreur exécution tâche {tid}: {exc}")
                                    all_t = load_scheduled_tasks()
                                    for item in all_t:
                                        if item.get("id") == tid:
                                            item["status"] = "failed"
                                            item["error"] = str(exc)
                                    save_scheduled_tasks(all_t)

                            job_thread = threading.Thread(target=run_scheduled_job, daemon=True)
                            job_thread.start()
                            break
            if changed:
                save_scheduled_tasks(tasks)
        except Exception as e:
            print(f"[SCHEDULER] Exception dans la boucle: {e}")


class MailServerHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silence normal request logs in console to keep terminal clean
        return

    def send_json(self, data, status_code=200):
        response_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(response_bytes)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            template_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
            if os.path.exists(template_path):
                with open(template_path, "r", encoding="utf-8") as f:
                    content = f.read().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404, "Template index.html introuvable")
            return

        elif path == "/api/config":
            cfg = load_config()
            sigs = load_signatures()
            default_sig = next((s for s in sigs if s.get("is_default")), sigs[0] if sigs else None)
            default_sig_content = default_sig.get("content", "") if default_sig else cfg.get("email_signature", "")
            safe_cfg = {
                "provider": cfg.get("provider", "brevo"),
                "sender_email": cfg.get("sender_email") or cfg.get("gmail_address", ""),
                "gmail_address": cfg.get("gmail_address", ""),
                "has_password": bool(cfg.get("app_password")),
                "has_brevo_key": bool(cfg.get("brevo_api_key")),
                "sender_name": cfg.get("sender_name", ""),
                "default_delay": cfg.get("default_delay", 2),
                "email_signature": default_sig_content,
                "include_signature": cfg.get("include_signature", True),
                "signatures": sigs,
                "default_signature_id": default_sig.get("id", "") if default_sig else ""
            }
            self.send_json(safe_cfg)
            return

        elif path == "/api/status":
            with state_lock:
                copy_state = dict(campaign_state)
                copy_state["logs"] = list(campaign_state["logs"])
            self.send_json(copy_state)
            return

        elif path == "/api/export-logs":
            with state_lock:
                logs = list(campaign_state["logs"])
            csv_lines = ["Heure,Email,Statut,Détails"]
            for log in logs:
                details = log.get('details', '').replace('"', '""')
                csv_lines.append(f'"{log.get("time")}","{log.get("email")}","{log.get("status")}","{details}"')
            csv_content = "\n".join(csv_lines).encode("utf-8-sig")
            
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="rapport_envoi.csv"')
            self.send_header("Content-Length", str(len(csv_content)))
            self.end_headers()
            self.wfile.write(csv_content)
            return

        elif path == "/api/history":
            history = load_history()
            self.send_json({"success": True, "history": history})
            return

        elif path == "/api/history/export":
            query = parse_qs(parsed.query)
            camp_id = query.get("id", [""])[0]
            history = load_history()
            target_camp = next((c for c in history if str(c.get("id")) == str(camp_id)), None)
            
            if not target_camp:
                self.send_error(404, "Campagne introuvable")
                return

            logs = target_camp.get("logs", [])
            csv_lines = ["Heure,Email,Statut,Détails"]
            for log in logs:
                details = str(log.get('details', '')).replace('"', '""')
                email_val = str(log.get('email', '')).replace('"', '""')
                csv_lines.append(f'"{log.get("time")}","{email_val}","{log.get("status")}","{details}"')
            csv_content = "\n".join(csv_lines).encode("utf-8-sig")

            safe_filename = f"rapport_campagne_{camp_id}.csv"
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="{safe_filename}"')
            self.send_header("Content-Length", str(len(csv_content)))
            self.end_headers()
            self.wfile.write(csv_content)
            return

        elif path == "/api/lists":
            lists = load_contact_lists()
            self.send_json({"success": True, "lists": lists})
            return

        elif path == "/api/schedule/list":
            tasks = load_scheduled_tasks()
            self.send_json({"success": True, "tasks": tasks})
            return

        elif path == "/api/templates":
            templates = load_custom_templates()
            self.send_json({"success": True, "templates": templates})
            return

        elif path == "/api/signatures":
            signatures = load_signatures()
            self.send_json({"success": True, "signatures": signatures})
            return

        elif path == "/api/certificate/config":
            cfg = load_certificate_config()
            self.send_json({"success": True, "config": cfg, "has_pil": HAS_PIL})
            return

        self.send_error(404, "Page non trouvée")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        data = {}
        if body:
            try:
                data = json.loads(body.decode("utf-8"))
            except Exception:
                pass

        if path == "/api/config":
            save_config(data)
            if "email_signature" in data:
                sigs = load_signatures()
                if sigs:
                    def_sig = next((s for s in sigs if s.get("is_default")), sigs[0])
                    def_sig["content"] = data["email_signature"]
                    save_signatures(sigs)
            self.send_json({"success": True, "message": "Paramètres enregistrés avec succès !"})
            return

        elif path == "/api/test-connection":
            cfg = load_config()
            provider = data.get("provider") or cfg.get("provider", "brevo")
            
            if provider == "brevo":
                key = data.get("brevo_api_key") or cfg.get("brevo_api_key", "")
                if not key:
                    self.send_json({"success": False, "message": "Veuillez renseigner votre clé API Brevo."})
                    return
                ok, msg = verify_brevo_credentials(key)
                self.send_json({"success": ok, "message": msg})
                return
            else:
                gmail = data.get("gmail_address") or cfg.get("gmail_address", "")
                pwd = data.get("app_password") or cfg.get("app_password", "")
                if not gmail or not pwd:
                    self.send_json({"success": False, "message": "Veuillez renseigner votre email Gmail et votre mot de passe d'application."})
                    return
                ok, msg = verify_gmail_credentials(gmail, pwd)
                self.send_json({"success": ok, "message": msg})
                return

        elif path == "/api/test-send":
            cfg = load_config()
            provider = data.get("provider") or cfg.get("provider", "brevo")
            sender_email = data.get("sender_email") or data.get("gmail_address") or cfg.get("sender_email") or cfg.get("gmail_address", "")
            sender_name = data.get("sender_name") or cfg.get("sender_name", "")
            target = data.get("test_email", "")
            subject = data.get("subject", "Test MailStorm")
            content = data.get("content", "<p>Ceci est un email de test envoyé par <b>MailStorm</b>.</p>")
            
            include_sig = data.get("include_signature", cfg.get("include_signature", True))
            sig = data.get("email_signature") if "email_signature" in data else cfg.get("email_signature", "")
            if include_sig and sig:
                sig_html = sig if ("<" in sig and ">" in sig) else sig.replace("\n", "<br>")
                content = f"{content}<br><br><div style='border-top:1px solid #e2e8f0;padding-top:12px;margin-top:20px;color:#475569;'>{sig_html}</div>"

            if not target or "@" not in target:
                self.send_json({"success": False, "message": "Adresse email de test invalide."})
                return

            test_attachments = []
            cert_config = data.get("certificate")
            if cert_config and cert_config.get("enabled"):
                try:
                    rec_name = extract_recipient_name(target, {"email": target}, cert_config.get("name_var", ""))
                    cert_att = generate_certificate_attachment(rec_name, cert_config, {"email": target}, target)
                    if cert_att:
                        test_attachments.append({
                            "name": cert_att["name"],
                            "data": cert_att["data"]
                        })
                except Exception as ce:
                    print(f"Erreur certificat test-send: {ce}")

            try:
                if provider == "brevo":
                    key = data.get("brevo_api_key") or cfg.get("brevo_api_key", "")
                    if not key:
                        self.send_json({"success": False, "message": "Clé API Brevo manquante."})
                        return
                    if not sender_email:
                        self.send_json({"success": False, "message": "Adresse email de l'expéditeur manquante."})
                        return
                    send_single_email_brevo(
                        api_key=key,
                        sender_email=sender_email,
                        sender_name=sender_name,
                        recipient=target,
                        subject=f"[TEST] {subject}",
                        content_html=content,
                        attachments=test_attachments
                    )
                else:
                    pwd = data.get("app_password") or cfg.get("app_password", "")
                    if not sender_email or not pwd:
                        self.send_json({"success": False, "message": "Identifiants Gmail manquants."})
                        return
                    send_single_email(
                        sender_email=sender_email,
                        app_password=pwd,
                        sender_name=sender_name,
                        recipient=target,
                        subject=f"[TEST] {subject}",
                        content_html=content,
                        attachments=test_attachments
                    )
                self.send_json({"success": True, "message": f"Email de test envoyé avec succès à {target} !"})
            except Exception as e:
                self.send_json({"success": False, "message": f"Erreur lors du test : {str(e)}"})
            return

        elif path == "/api/start-campaign":
            with state_lock:
                if campaign_state["is_running"]:
                    self.send_json({"success": False, "message": "Une campagne est déjà en cours d'envoi."})
                    return

            cfg = load_config()
            provider = data.get("provider") or cfg.get("provider", "brevo")
            sender_email = data.get("sender_email") or data.get("gmail_address") or cfg.get("sender_email") or cfg.get("gmail_address", "")
            sender_name = data.get("sender_name") or cfg.get("sender_name", "")
            pwd = data.get("app_password") or cfg.get("app_password", "")
            brevo_key = data.get("brevo_api_key") or cfg.get("brevo_api_key", "")
            
            recipients = data.get("recipients", [])
            subject = data.get("subject", "")
            content = data.get("content", "")
            delay = float(data.get("delay", 2))
            attachments = data.get("attachments", [])

            include_sig = data.get("include_signature", cfg.get("include_signature", True))
            sig = data.get("email_signature") if "email_signature" in data else cfg.get("email_signature", "")
            if include_sig and sig:
                sig_html = sig if ("<" in sig and ">" in sig) else sig.replace("\n", "<br>")
                content = f"{content}<br><br><div style='border-top:1px solid #e2e8f0;padding-top:12px;margin-top:20px;color:#475569;'>{sig_html}</div>"

            if provider == "brevo" and (not brevo_key or not sender_email):
                self.send_json({"success": False, "message": "Veuillez configurer votre clé API Brevo et votre adresse email d'expéditeur."})
                return

            if provider == "gmail" and (not sender_email or not pwd):
                self.send_json({"success": False, "message": "Veuillez configurer votre compte Gmail avant de lancer l'envoi."})
                return

            if not recipients:
                self.send_json({"success": False, "message": "Aucun destinataire valide spécifié."})
                return

            if not subject:
                self.send_json({"success": False, "message": "Le sujet de l'email ne peut pas être vide."})
                return

            cert_config = data.get("certificate", {})

            # Lancer le thread de campagne
            thread = threading.Thread(
                target=worker_campaign,
                kwargs={
                    "recipients": recipients,
                    "subject": subject,
                    "content_html": content,
                    "provider": provider,
                    "sender_email": sender_email,
                    "sender_name": sender_name,
                    "app_password": pwd,
                    "brevo_api_key": brevo_key,
                    "delay_seconds": delay,
                    "attachments": attachments,
                    "cert_config": cert_config
                },
                daemon=True
            )
            thread.start()

            self.send_json({"success": True, "message": f"Campagne lancée pour {len(recipients)} destinataires via {provider.upper()} !"})
            return

        elif path == "/api/stop-campaign":
            with state_lock:
                if campaign_state["is_running"]:
                    campaign_state["should_stop"] = True
                    self.send_json({"success": True, "message": "Arrêt en cours..."})
                else:
                    self.send_json({"success": False, "message": "Aucune campagne n'est en cours."})
            return

        elif path == "/api/history/delete":
            camp_id = str(data.get("id", ""))
            history = load_history()
            new_history = [c for c in history if str(c.get("id")) != camp_id]
            try:
                with open(LOGS_FILE, "w", encoding="utf-8") as f:
                    json.dump(new_history, f, indent=2, ensure_ascii=False)
                self.send_json({"success": True, "message": "Campagne supprimée de l'historique."})
            except Exception as e:
                self.send_json({"success": False, "message": str(e)})
            return

        elif path == "/api/history/clear":
            try:
                with open(LOGS_FILE, "w", encoding="utf-8") as f:
                    json.dump([], f, indent=2)
                self.send_json({"success": True, "message": "Historique effacé avec succès."})
            except Exception as e:
                self.send_json({"success": False, "message": str(e)})
            return

        elif path == "/api/lists/save":
            name = (data.get("name") or "").strip()
            contacts = data.get("contacts") or []
            columns = data.get("columns") or []
            if not name:
                self.send_json({"success": False, "message": "Veuillez donner un nom à la liste."})
                return
            if not contacts:
                self.send_json({"success": False, "message": "La liste ne contient aucun contact valide."})
                return

            lists = load_contact_lists()
            list_id = data.get("id") or str(uuid.uuid4())[:8]
            existing = next((l for l in lists if str(l.get("id")) == str(list_id)), None)

            list_entry = {
                "id": list_id,
                "name": name,
                "count": len(contacts),
                "columns": columns,
                "updated_at": time.strftime("%d/%m/%Y à %H:%M"),
                "contacts": contacts
            }

            if existing:
                list_entry["created_at"] = existing.get("created_at", time.strftime("%d/%m/%Y à %H:%M"))
                lists = [list_entry if str(l.get("id")) == str(list_id) else l for l in lists]
            else:
                list_entry["created_at"] = time.strftime("%d/%m/%Y à %H:%M")
                lists.insert(0, list_entry)

            save_contact_lists(lists)
            self.send_json({
                "success": True, 
                "message": f"Liste « {name} » ({len(contacts)} contacts) enregistrée avec succès !", 
                "list": list_entry
            })
            return

        elif path == "/api/lists/delete":
            list_id = str(data.get("id", ""))
            lists = load_contact_lists()
            lists = [l for l in lists if str(l.get("id")) != list_id]
            save_contact_lists(lists)
            self.send_json({"success": True, "message": "Liste supprimée avec succès."})
            return

        elif path == "/api/spam-check":
            subject = data.get("subject", "")
            content = data.get("content", "")
            include_sig = data.get("include_signature", True)
            sig = data.get("email_signature", "")
            if include_sig and sig:
                sig_html = sig if ("<" in sig and ">" in sig) else sig.replace("\n", "<br>")
                content = f"{content}<br><br><div style='border-top:1px solid #e2e8f0;padding-top:12px;margin-top:20px;color:#475569;'>{sig_html}</div>"
            
            report = evaluate_spam_score(subject, content)
            self.send_json({"success": True, "report": report})
            return

        elif path == "/api/schedule/create":
            cfg = load_config()
            provider = data.get("provider") or cfg.get("provider", "brevo")
            sender_email = data.get("sender_email") or data.get("gmail_address") or cfg.get("sender_email") or cfg.get("gmail_address", "")
            sender_name = data.get("sender_name") or cfg.get("sender_name", "")
            pwd = data.get("app_password") or cfg.get("app_password", "")
            brevo_key = data.get("brevo_api_key") or cfg.get("brevo_api_key", "")
            
            recipients = data.get("recipients", [])
            subject = data.get("subject", "")
            content = data.get("content", "")
            delay = float(data.get("delay", 2))
            attachments = data.get("attachments", [])
            scheduled_str = data.get("scheduled_datetime", "").strip()

            if not recipients:
                self.send_json({"success": False, "message": "Aucun destinataire spécifié."})
                return
            if not subject:
                self.send_json({"success": False, "message": "Le sujet de l'email ne peut pas être vide."})
                return
            if not scheduled_str:
                self.send_json({"success": False, "message": "Veuillez choisir une date et heure de programmation."})
                return

            try:
                clean_dt = scheduled_str.replace("Z", "").split(".")[0]
                if "T" in clean_dt:
                    dt_obj = datetime.datetime.strptime(clean_dt, "%Y-%m-%dT%H:%M")
                else:
                    dt_obj = datetime.datetime.strptime(clean_dt, "%Y-%m-%d %H:%M")
                sched_ts = dt_obj.timestamp()
            except Exception as e:
                self.send_json({"success": False, "message": f"Format de date invalide ({scheduled_str}) : {str(e)}"})
                return

            if sched_ts <= time.time() + 30:
                self.send_json({"success": False, "message": "La date et l'heure programmées doivent être dans le futur (au moins 1 minute plus tard)."})
                return

            if provider == "brevo" and (not brevo_key or not sender_email):
                self.send_json({"success": False, "message": "Veuillez configurer votre clé API Brevo et adresse expéditeur dans Paramètres."})
                return
            if provider == "gmail" and (not sender_email or not pwd):
                self.send_json({"success": False, "message": "Veuillez configurer vos identifiants Gmail dans Paramètres."})
                return

            include_sig = data.get("include_signature", cfg.get("include_signature", True))
            sig = data.get("email_signature") if "email_signature" in data else cfg.get("email_signature", "")
            if include_sig and sig:
                sig_html = sig if ("<" in sig and ">" in sig) else sig.replace("\n", "<br>")
                content = f"{content}<br><br><div style='border-top:1px solid #e2e8f0;padding-top:12px;margin-top:20px;color:#475569;'>{sig_html}</div>"

            task_id = str(uuid.uuid4())[:8]
            formatted_target = dt_obj.strftime("%d/%m/%Y à %H:%M")
            task = {
                "id": task_id,
                "subject": subject,
                "content_html": content,
                "recipients": recipients,
                "provider": provider,
                "sender_email": sender_email,
                "sender_name": sender_name,
                "delay": delay,
                "attachments": attachments,
                "certificate": data.get("certificate", {}),
                "scheduled_datetime": scheduled_str,
                "scheduled_formatted": formatted_target,
                "scheduled_timestamp": sched_ts,
                "created_at": time.strftime("%d/%m/%Y à %H:%M"),
                "status": "pending"
            }

            tasks = load_scheduled_tasks()
            tasks.insert(0, task)
            save_scheduled_tasks(tasks)
            self.send_json({
                "success": True, 
                "message": f"Campagne programmée avec succès pour le {formatted_target} ({len(recipients)} destinataires) !", 
                "task": task
            })
            return

        elif path == "/api/schedule/cancel":
            task_id = str(data.get("id", ""))
            tasks = load_scheduled_tasks()
            found = False
            for t in tasks:
                if str(t.get("id")) == task_id and t.get("status") == "pending":
                    t["status"] = "cancelled"
                    t["cancelled_at"] = time.strftime("%d/%m/%Y à %H:%M")
                    found = True
            save_scheduled_tasks(tasks)
            if found:
                self.send_json({"success": True, "message": "Campagne programmée annulée avec succès."})
            else:
                self.send_json({"success": False, "message": "Tâche introuvable ou déjà traitée."})
            return

        elif path == "/api/schedule/delete":
            task_id = str(data.get("id", ""))
            tasks = load_scheduled_tasks()
            tasks = [t for t in tasks if str(t.get("id")) != task_id]
            save_scheduled_tasks(tasks)
            self.send_json({"success": True, "message": "Tâche supprimée."})
            return

        elif path == "/api/templates/save":
            name = (data.get("name") or "").strip()
            subject = (data.get("subject") or "").strip()
            body = (data.get("body") or "").strip()
            category = (data.get("category") or "Personnalisé").strip()
            icon = (data.get("icon") or "✨").strip()
            tpl_id = data.get("id") or str(uuid.uuid4())[:8]

            if not name:
                self.send_json({"success": False, "message": "Veuillez donner un nom au modèle."})
                return
            if not body and not subject:
                self.send_json({"success": False, "message": "Le modèle doit comporter un sujet ou un contenu."})
                return

            templates = load_custom_templates()
            existing = next((t for t in templates if str(t.get("id")) == str(tpl_id)), None)

            tpl_entry = {
                "id": tpl_id,
                "name": name,
                "subject": subject,
                "body": body,
                "category": category,
                "icon": icon,
                "updated_at": time.strftime("%d/%m/%Y à %H:%M")
            }

            if existing:
                tpl_entry["created_at"] = existing.get("created_at", time.strftime("%d/%m/%Y à %H:%M"))
                templates = [tpl_entry if str(t.get("id")) == str(tpl_id) else t for t in templates]
            else:
                tpl_entry["created_at"] = time.strftime("%d/%m/%Y à %H:%M")
                templates.insert(0, tpl_entry)

            save_custom_templates(templates)
            self.send_json({
                "success": True, 
                "message": f"Modèle « {name} » enregistré avec succès !", 
                "template": tpl_entry
            })
            return

        elif path == "/api/templates/delete":
            tpl_id = str(data.get("id", ""))
            templates = load_custom_templates()
            templates = [t for t in templates if str(t.get("id")) != tpl_id]
            save_custom_templates(templates)
            self.send_json({"success": True, "message": "Modèle supprimé avec succès."})
            return

        elif path == "/api/signatures/save":
            name = (data.get("name") or "").strip()
            content = (data.get("content") or "").strip()
            is_default = bool(data.get("is_default", False))
            sig_id = str(data.get("id") or uuid.uuid4().hex[:8])

            if not name:
                self.send_json({"success": False, "message": "Veuillez donner un nom à la signature."})
                return
            if not content:
                self.send_json({"success": False, "message": "Le contenu de la signature ne peut pas être vide."})
                return

            sigs = load_signatures()
            existing = next((s for s in sigs if str(s.get("id")) == str(sig_id)), None)

            if is_default or len(sigs) == 0:
                for s in sigs:
                    s["is_default"] = False
                is_default = True

            sig_entry = {
                "id": sig_id,
                "name": name,
                "content": content,
                "is_default": is_default,
                "updated_at": time.strftime("%d/%m/%Y à %H:%M")
            }

            if existing:
                sig_entry["created_at"] = existing.get("created_at", time.strftime("%d/%m/%Y à %H:%M"))
                if existing.get("is_default") and not is_default:
                    other_default = any(s.get("is_default") for s in sigs if str(s.get("id")) != str(sig_id))
                    if not other_default:
                        sig_entry["is_default"] = True
                sigs = [sig_entry if str(s.get("id")) == str(sig_id) else s for s in sigs]
            else:
                sig_entry["created_at"] = time.strftime("%d/%m/%Y à %H:%M")
                sigs.append(sig_entry)

            if not any(s.get("is_default") for s in sigs):
                sigs[0]["is_default"] = True

            save_signatures(sigs)

            # Sync default signature with config.json
            def_sig = next((s for s in sigs if s.get("is_default")), sigs[0])
            save_config({"email_signature": def_sig.get("content", "")})

            self.send_json({
                "success": True,
                "message": f"Signature « {name} » enregistrée avec succès !",
                "signature": sig_entry,
                "signatures": sigs
            })
            return

        elif path == "/api/signatures/set-default":
            sig_id = str(data.get("id", ""))
            sigs = load_signatures()
            target = next((s for s in sigs if str(s.get("id")) == sig_id), None)
            if not target:
                self.send_json({"success": False, "message": "Signature introuvable."})
                return

            for s in sigs:
                s["is_default"] = (str(s.get("id")) == sig_id)

            save_signatures(sigs)
            save_config({"email_signature": target.get("content", "")})

            self.send_json({
                "success": True,
                "message": f"« {target.get('name')} » est désormais la signature par défaut.",
                "signatures": sigs
            })
            return

        elif path == "/api/signatures/delete":
            sig_id = str(data.get("id", ""))
            sigs = load_signatures()
            target = next((s for s in sigs if str(s.get("id")) == sig_id), None)
            if not target:
                self.send_json({"success": False, "message": "Signature introuvable."})
                return

            if len(sigs) <= 1:
                self.send_json({"success": False, "message": "Impossible de supprimer la seule signature restante."})
                return

            was_default = target.get("is_default", False)
            sigs = [s for s in sigs if str(s.get("id")) != sig_id]
            if was_default and sigs:
                sigs[0]["is_default"] = True
                save_config({"email_signature": sigs[0].get("content", "")})

            save_signatures(sigs)
            self.send_json({
                "success": True,
                "message": f"Signature « {target.get('name')} » supprimée.",
                "signatures": sigs
            })
            return

        elif path == "/api/certificate/config":
            save_certificate_config(data)
            self.send_json({"success": True, "message": "Configuration du certificat enregistrée avec succès !"})
            return

        elif path == "/api/certificate/preview":
            sample_name = (data.get("sample_name") or "Mohamed Ali Mseddi").strip()
            cert_cfg = data.get("config", {})
            try:
                # Force PNG format for instant image preview in browser
                preview_cfg = dict(cert_cfg)
                preview_cfg["output_format"] = "png"
                att = generate_certificate_attachment(sample_name, preview_cfg)
                self.send_json({
                    "success": True,
                    "preview_image": att["data"],
                    "filename": att["name"],
                    "mime": att["mime"]
                })
            except Exception as e:
                self.send_json({"success": False, "message": f"Erreur génération aperçu : {str(e)}"})
            return

        elif path == "/api/certificate/download-sample":
            sample_name = (data.get("sample_name") or "Mohamed Ali Mseddi").strip()
            cert_cfg = data.get("config", {})
            try:
                att = generate_certificate_attachment(sample_name, cert_cfg)
                self.send_response(200)
                self.send_header("Content-Type", att["mime"])
                self.send_header("Content-Disposition", f'attachment; filename="{att["name"]}"')
                self.send_header("Content-Length", str(len(att["content_bytes"])))
                self.end_headers()
                self.wfile.write(att["content_bytes"])
            except Exception as e:
                self.send_error(500, f"Erreur téléchargement : {str(e)}")
            return

        self.send_error(404, "Endpoint non trouvé")


def run():
    server_address = ("0.0.0.0", PORT)
    httpd = HTTPServer(server_address, MailServerHandler)
    url = f"http://localhost:{PORT}"
    print("=" * 60)
    print(" 🚀 MailStorm - Bulk Email Sender")
    print(f" 🌐 Dashboard accessible sur : {url} (Port {PORT})")
    print("=" * 60)
    print(" Appuyez sur Ctrl+C pour arrêter le serveur.")
    
    # Lancement du planificateur en tâche de fond (daemon)
    sched_thread = threading.Thread(target=scheduler_daemon, daemon=True)
    sched_thread.start()

    # Ouvrir le navigateur uniquement en local (pas sur un serveur cloud comme Render)
    if "PORT" not in os.environ:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt du serveur...")
        httpd.server_close()

if __name__ == "__main__":
    run()
