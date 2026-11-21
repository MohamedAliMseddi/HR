@echo off
title MailStorm - Bulk Email Sender
echo ========================================================
echo  🚀 Lancement de MailStorm (Gmail Bulk Email Sender)
echo ========================================================
echo Ouverture du serveur local et du navigateur...
python app.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Une erreur s'est produite lors de l'execution.
    pause
)
