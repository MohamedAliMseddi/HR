# 🚀 MailStorm - Gmail Bulk Email Sender

Application locale simple, rapide et moderne en **Python** pour envoyer des emails groupés via **Gmail** avec suivi en temps réel.

---

## 📌 Comment lancer l'application ?

### Méthode 1 (La plus simple) :
Double-cliquez directement sur le fichier **`start.bat`**.
L'application va se lancer et ouvrira automatiquement votre navigateur sur **http://localhost:5000**.

### Méthode 2 (Ligne de commande) :
Ouvrez votre terminal dans ce dossier et tapez :
```bash
python app.py
```

---

## 🔑 Configuration Gmail (Important : Mot de passe d'application)

Google n'autorise plus l'utilisation directe de votre mot de passe habituel pour des raisons de sécurité. Vous devez générer un **mot de passe d'application (16 caractères)** :

1. **Activez la validation en deux étapes** sur votre compte Google si ce n'est pas déjà fait :
   👉 [myaccount.google.com/security](https://myaccount.google.com/security)
2. **Accédez aux mots de passe d'application** :
   👉 [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Donnez un nom (ex: `MailStorm`) puis cliquez sur **Créer**.
4. Copiez les **16 lettres** (ex: `abcd efgh ijkl mnop`).
5. Ouvrez l'application, allez dans l'onglet **Paramètres Gmail**, collez le code et cliquez sur **Tester la connexion**.

---

## ✨ Fonctionnalités incluses

- **Import de destinataires :**
  - Copier/coller direct (1 par ligne ou séparés par virgules).
  - Import direct de fichiers **CSV**, **TXT**, ou **Excel (.xlsx, .xls)**.
  - Bouton **Nettoyer & dédoublonner** avec confirmation visuelle immédiate et statistiques.
- **Édition du message :**
  - Sujet propre avec personnalisation dynamique : `{email}`, `{date}`.
  - Message en texte brut ou en **HTML stylisé**.
  - **Aperçu en direct (Live Preview)** avant l'envoi.
  - Support des **pièces jointes** (PDF, images, documents...).
- **Sécurité anti-blocage (Anti-Spam) :**
  - Curseur de délai réglable (ex: 2 secondes entre chaque envoi) pour protéger votre réputation Gmail.
  - Bouton de **test préalable** (pour envoyer un test à votre propre boîte).
- **Suivi en temps réel :**
  - Barre de progression animée.
  - Compteurs : Total, Envoyés, Échoués, Restants.
  - Journal d'activité détaillé en direct.
  - Bouton d'interruption immédiate (*Arrêter l'envoi*).
  - **Export du rapport final en CSV**.

---

## 🇹🇳 Bel Derja (فكرة عامة)
- Hel el dossier w ekbes direct 3la **`start.bat`**.
- El navigateur mte3ek bech yet7al wahdou fi **http://localhost:5000**.
- A3mel configuration mte3 Gmail mte3ek (Gmail + App Password mte3 16 7rouf).
- 7ot les emails (coller wela upload fichier Excel/CSV/TXT), kteb el sujet wel contenu, w ekbes **Lancer la campagne** !
