import os
import json
import keyring
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from typing import Optional

# --- AJUSTEMENT DU CHEMIN ABSOLU ---
# Récupère le dossier où se trouve auth.py (src/services/)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Si ton fichier client_secret.json est à la racine du projet (recommandé) :
CLIENT_SECRET_FILE = os.path.join(BASE_DIR, "..", "..", "client_secret.json")

# Note : Si ton fichier client_secret.json se trouve directement dans le même 
# dossier que auth.py (src/services/), utilise plutôt cette ligne :
# CLIENT_SECRET_FILE = os.path.join(BASE_DIR, "client_secret.json")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly", 
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/contacts.readonly"
]
KEYRING_SERVICE = "flet-mail-mvp"

def run_console_flow(account_id: str) -> Credentials:
    # Utilise l'application installée avec redirection en local
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
    creds = flow.run_local_server(port=0)  # Plus fluide sur Fedora Workstation
    keyring.set_password(KEYRING_SERVICE, account_id, creds.to_json())
    return creds

def load_credentials(account_id: str) -> Optional[Credentials]:
    raw = keyring.get_password(KEYRING_SERVICE, account_id)
    if not raw:
        return None
    
    data = json.loads(raw)
    creds = Credentials.from_authorized_user_info(data, SCOPES)
    
    # Vérification des scopes : si le token n'a pas tous les scopes requis,
    # on le supprime pour forcer une ré-authentification avec les bons scopes
    if creds and creds.scopes:
        required = set(SCOPES)
        granted = set(creds.scopes)
        if not required.issubset(granted):
            missing = required - granted
            print(f"[Emailzen] Token pour '{account_id}' a des scopes insuffisants.")
            print(f"  Requis : {required}")
            print(f"  Accordés : {granted}")
            print(f"  Manquants : {missing}")
            print(f"  → Suppression du token. Reconnexion nécessaire.")
            delete_credentials(account_id)
            return None
    
    # Validation et rafraîchissement automatique du token expiré
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            keyring.set_password(KEYRING_SERVICE, account_id, creds.to_json())
        except Exception:
            print(f"[Emailzen] Échec du rafraîchissement du token pour '{account_id}'. Reconnexion nécessaire.")
            delete_credentials(account_id)
            return None
            
    return creds

def delete_credentials(account_id: str):
    try:
        keyring.delete_password(KEYRING_SERVICE, account_id)
    except Exception:
        pass