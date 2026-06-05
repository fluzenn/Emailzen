# Emailzen Premium MVP

Emailzen est un client de messagerie ultra-rapide et léger développé avec **Flet** (Python). Il centralise vos comptes Gmail (via l'API Google sécurisée et protocole OAuth2) ainsi que vos comptes IMAP/SMTP traditionnels (Outlook, Yahoo, etc.) dans une interface moderne et fluide.

## Fonctionnalités

* **Multi-comptes synchrone :** Basculez instantanément entre Gmail, Outlook et Yahoo.
* **Performance optimisée :** Batching des requêtes Gmail et mise en cache locale SQLite (`mail_cache.db`).
* **Sécurité maximale :** Stockage sécurisé des jetons d'authentification et mots de passe via le trousseau de clés du système (`keyring`).
* **Rendu sécurisé :** Protection contre les contenus d'emails trop lourds.

## Prérequis & Installation (Développement)

Le projet tourne idéalement sur **Linux (Fedora Workstation)**, **Windows** et **macOS**.

1. **Cloner le dépôt :**
   ```bash
   git clone [https://github.com/VOTRE_NOM_UTILISATEUR/Emailzen.git](https://github.com/VOTRE_NOM_UTILISATEUR/Emailzen.git)
   cd Emailzen

    Installer les dépendances :
    Bash

    pip install -r requirements.txt

    Lancer l'application :
    Bash

    flet run main.py

    Note : Pour faire fonctionner la connexion Gmail, vous devez placer votre fichier client_secret.json (généré depuis la Google Cloud Console) à la racine du projet.

Licence

Ce projet est sous licence MIT. Voir le fichier LICENSE pour plus de détails.
