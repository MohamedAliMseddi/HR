"""
MailStorm - Mode Ligne de Commande (CLI)
Permet d'envoyer rapidement des emails depuis le terminal sans interface web.
"""

import os
import sys
import json
import time
import getpass
import re
from app import load_config, save_config, send_single_email, verify_gmail_credentials

def extract_emails_from_string(text):
    regex = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    return list(dict.fromkeys(re.findall(regex, text)))

def main():
    print("=" * 60)
    print(" 🚀 MailStorm - Envoi groupé Gmail (Mode Terminal / CLI)")
    print("=" * 60)

    cfg = load_config()
    sender_email = cfg.get("gmail_address", "")
    app_password = cfg.get("app_password", "")
    sender_name = cfg.get("sender_name", "")

    if not sender_email or not app_password:
        print("\n⚠️  Configuration de votre compte Gmail requise :")
        sender_email = input("👉 Adresse Gmail : ").strip()
        print("ℹ️  Entrez votre mot de passe d'application Google (16 lettres) :")
        app_password = getpass.getpass("👉 Mot de passe d'application : ").strip()
        sender_name = input("👉 Nom d'expéditeur (laisser vide pour aucun) : ").strip()

        print("\n⏳ Vérification des identifiants avec Gmail...")
        ok, msg = verify_gmail_credentials(sender_email, app_password)
        if not ok:
            print(f"❌ {msg}")
            return
        print(f"✅ {msg}")

        save_choice = input("Voulez-vous mémoriser ces identifiants ? (o/n) : ").strip().lower()
        if save_choice in ["o", "oui", "y", "yes"]:
            save_config({
                "gmail_address": sender_email,
                "app_password": app_password,
                "sender_name": sender_name
            })
            print("💾 Identifiants enregistrés dans config.json !")
    else:
        print(f"👤 Expéditeur configuré : {sender_name or sender_email} <{sender_email}>")

    print("\n" + "-" * 60)
    print("📋 Étape 1 : Liste des destinataires")
    print("Options :")
    print("  1. Saisir le chemin d'un fichier (.txt, .csv)")
    print("  2. Coller directement des adresses email")
    choice = input("👉 Votre choix (1 ou 2) [défaut: 2] : ").strip()

    emails = []
    if choice == "1":
        filepath = input("👉 Chemin du fichier : ").strip().strip('"')
        if not os.path.exists(filepath):
            print(f"❌ Fichier introuvable : {filepath}")
            return
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            emails = extract_emails_from_string(f.read())
    else:
        print("👉 Collez vos emails (terminez par une ligne vide puis appuyez sur Entrée) :")
        lines = []
        while True:
            line = input()
            if not line:
                break
            lines.append(line)
        emails = extract_emails_from_string("\n".join(lines))

    if not emails:
        print("❌ Aucun email valide détecté. Annulation.")
        return

    print(f"✅ {len(emails)} destinataire(s) valide(s) détecté(s).")

    print("\n" + "-" * 60)
    print("✉️ Étape 2 : Contenu du message")
    subject = input("👉 Objet / Sujet de l'email : ").strip()
    if not subject:
        print("❌ Le sujet ne peut pas être vide.")
        return

    print("👉 Message (Entrez votre texte. Tapez 'FIN' sur une nouvelle ligne pour terminer) :")
    body_lines = []
    while True:
        line = input()
        if line.strip() == "FIN":
            break
        body_lines.append(line)
    
    content = "<br>".join(body_lines)
    if not content.strip():
        print("❌ Le message ne peut pas être vide.")
        return

    delay_input = input("👉 Délai anti-spam entre chaque email en secondes (défaut: 2) : ").strip()
    delay = float(delay_input) if delay_input else 2.0

    print("\n" + "=" * 60)
    print(f"📢 RÉSUMÉ :")
    print(f" - Destinataires : {len(emails)}")
    print(f" - Sujet         : {subject}")
    print(f" - Délai         : {delay}s par email")
    print("=" * 60)
    
    confirm = input("Voulez-vous lancer l'envoi maintenant ? (o/n) : ").strip().lower()
    if confirm not in ["o", "oui", "y", "yes"]:
        print("Opération annulée.")
        return

    print("\n🚀 Démarrage de l'envoi...")
    sent = 0
    failed = 0
    for idx, recipient in enumerate(emails, start=1):
        try:
            send_single_email(
                sender_email=sender_email,
                app_password=app_password,
                sender_name=sender_name,
                recipient=recipient,
                subject=subject,
                content_html=content,
                attachments=[]
            )
            sent += 1
            print(f" [{idx}/{len(emails)}] ✅ Envoyé à {recipient}")
        except Exception as e:
            failed += 1
            print(f" [{idx}/{len(emails)}] ❌ Échec pour {recipient} : {e}")

        if idx < len(emails):
            time.sleep(delay)

    print("\n" + "=" * 60)
    print(f"🎉 Terminé ! Envoyés : {sent} | Échoués : {failed}")
    print("=" * 60)

if __name__ == "__main__":
    main()
