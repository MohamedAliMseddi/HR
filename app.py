"""
MailStorm - Gmail Bulk Email Sender
Application Web locale développée en Python
"""

import os
import sys
import json
import time
import ssl
import smtplib
import re
import threading
import webbrowser
import base64
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
        "default_delay": 2
    }

def save_config(data):
    current = load_config()
    current.update(data)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2, ensure_ascii=False)

def verify_brevo_credentials(api_key):
    """
    Vérifie la clé API Brevo via HTTPS (Port 443 - Ouvert partout dans le Cloud)
    """
    clean_key = api_key.strip()
    req = urllib.request.Request(
        "https://api.brevo.com/v3/account",
        headers={
            "accept": "application/json",
            "api-key": clean_key,
            "User-Agent": "MailStorm/1.0"
        },
        method="GET"
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            email = data.get("email", "")
            return True, f"Connexion réussie à Brevo ({email}) ! Port 443 HTTPS validé."
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
            msg = err_body.get("message", str(e))
        except Exception:
            msg = str(e)
        return False, f"Erreur Brevo ({e.code}) : {msg}"
    except Exception as e:
        return False, f"Erreur de connexion Brevo : {str(e)}"

def send_single_email_brevo(api_key, sender_email, sender_name, recipient, subject, content_html, attachments=None):
    """
    Envoie un email via l'API REST de Brevo (HTTPS Port 443)
    """
    clean_key = api_key.strip()
    
    personalized_subject = subject.replace("{email}", recipient)
    personalized_content = content_html.replace("{email}", recipient)
    personalized_content = personalized_content.replace("{date}", time.strftime("%d/%m/%Y"))

    payload = {
        "sender": {
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

def send_single_email(sender_email, app_password, sender_name, recipient, subject, content_html, attachments=None):
    """
    Envoie un seul email via Gmail SMTP avec sujet propre et en-têtes RFC standards
    """
    clean_password = app_password.replace(" ", "")

    # Remplacement des variables personnalisées (Sujet 100% propre, sans aucun ajout)
    personalized_subject = subject.replace("{email}", recipient)
    personalized_content = content_html.replace("{email}", recipient)
    personalized_content = personalized_content.replace("{date}", time.strftime("%d/%m/%Y"))
    
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

def worker_campaign(recipients, subject, content_html, provider, sender_email, sender_name, app_password, brevo_api_key, delay_seconds, attachments):
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

    for idx, recipient in enumerate(recipients):
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
            campaign_state["current_email"] = recipient

        success = False
        error_msg = ""
        try:
            if provider == "brevo":
                send_single_email_brevo(
                    api_key=brevo_api_key,
                    sender_email=sender_email,
                    sender_name=sender_name,
                    recipient=recipient,
                    subject=subject,
                    content_html=content_html,
                    attachments=attachments
                )
            else:
                send_single_email(
                    sender_email=sender_email,
                    app_password=app_password,
                    sender_name=sender_name,
                    recipient=recipient,
                    subject=subject,
                    content_html=content_html,
                    attachments=attachments
                )
            success = True
        except Exception as e:
            error_msg = str(e)

        with state_lock:
            if success:
                campaign_state["sent"] += 1
                campaign_state["logs"].append({
                    "time": time.strftime("%H:%M:%S"),
                    "email": recipient,
                    "status": "success",
                    "details": "Envoyé avec succès"
                })
            else:
                campaign_state["failed"] += 1
                campaign_state["logs"].append({
                    "time": time.strftime("%H:%M:%S"),
                    "email": recipient,
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
            safe_cfg = {
                "provider": cfg.get("provider", "brevo"),
                "sender_email": cfg.get("sender_email") or cfg.get("gmail_address", ""),
                "gmail_address": cfg.get("gmail_address", ""),
                "has_password": bool(cfg.get("app_password")),
                "has_brevo_key": bool(cfg.get("brevo_api_key")),
                "sender_name": cfg.get("sender_name", ""),
                "default_delay": cfg.get("default_delay", 2)
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

            if not target or "@" not in target:
                self.send_json({"success": False, "message": "Adresse email de test invalide."})
                return

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
                        attachments=[]
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
                        attachments=[]
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
                    "attachments": attachments
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
