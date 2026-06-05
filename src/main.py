import flet as ft
import asyncio
import sys
import os
import re
import json
import imaplib
import keyring

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services import auth, gmail, imap_smtp
from src.storage import local_db
from src.utils.safe_render import render_text

def main(page: ft.Page):
    page.title = "Emailzen Premium MVP"
    page.window.width = 1200
    page.window.height = 800
    local_db.init_db()

    url_launcher = ft.UrlLauncher()

    # --- ÉTATS DE L'APPLICATION ---
    accounts = local_db.fetch_accounts()
    active_account = "primary"
    active_account_type = "gmail"
    active_account_email = None
    
    def update_active_account_details(acc_id):
        nonlocal active_account, active_account_type, active_account_email
        active_account = acc_id
        for acc in accounts:
            if acc["id"] == acc_id:
                active_account_type = acc["type"]
                active_account_email = acc["email"]
                break

    if accounts:
        update_active_account_details(accounts[0]["id"])
    else:
        accounts = [{"id": "primary", "type": "gmail", "email": None}]
        update_active_account_details("primary")
        
    current_folder_query = "label:INBOX"  
    current_page_token = None
    search_text_query = ""
    show_images_state = False
    cached_contacts = set()  # Stocke les adresses emails uniques nettoyées
    
    # Détails du message actif
    current_opened_msg_id = None
    current_sender = ""
    current_to = ""
    current_cc = ""
    current_subject = ""
    current_date = ""
    current_body = ""
    current_labels = []
    
    pending_download = None
    attached_files = []

    # --- COMPOSANTS AVATAR ET UX ---
    def get_avatar_color(sender_name: str):
        colors = [
            ft.Colors.RED_400, ft.Colors.BLUE_400, ft.Colors.GREEN_400, 
            ft.Colors.ORANGE_400, ft.Colors.PURPLE_400, ft.Colors.PINK_400, 
            ft.Colors.TEAL_400, ft.Colors.AMBER_400, ft.Colors.DEEP_ORANGE_400,
            ft.Colors.INDIGO_400, ft.Colors.CYAN_400
        ]
        hash_val = sum(ord(c) for c in sender_name)
        return colors[hash_val % len(colors)]

    def get_sender_avatar(sender_string: str, is_unread: bool) -> ft.Control:
        name = sender_string
        email_addr = ""
        match = re.search(r'([^<]*)\s*<([^>]*)>', sender_string)
        if match:
            name = match.group(1).strip().replace('"', '')
            email_addr = match.group(2).strip().lower()
        else:
            if "@" in sender_string:
                email_addr = sender_string.strip().lower()
                name = email_addr.split("@")[0]
                
        domain = email_addr.split("@")[-1] if "@" in email_addr else ""
        name_clean = name if name else (email_addr if email_addr else "?")
        first_letter = name_clean[0].upper() if name_clean else "?"

        icon_map = {
            # Jeux & Divertissement
            "chess.com": (ft.Icons.CASTLE, ft.Colors.GREEN_700),
            "netflix": (ft.Icons.MOVIE, ft.Colors.RED_700),
            "spotify": (ft.Icons.MUSIC_NOTE, ft.Colors.GREEN_500),
            "steam": (ft.Icons.GAMES, ft.Colors.BLUE_GREY_800),
            "twitch": (ft.Icons.LIVE_TV, ft.Colors.PURPLE_500),
            "discord": (ft.Icons.CHAT, ft.Colors.INDIGO_400),
            "epicgames": (ft.Icons.GAMEPAD, ft.Colors.GREY_900),
            "playstation": (ft.Icons.SPORTS_ESPORTS, ft.Colors.BLUE_800),
            "xbox": (ft.Icons.SPORTS_ESPORTS, ft.Colors.GREEN_600),
            "nintendo": (ft.Icons.SPORTS_ESPORTS, ft.Colors.RED_500),
            # Réseaux sociaux
            "facebook": (ft.Icons.FACEBOOK, ft.Colors.BLUE_800),
            "twitter": (ft.Icons.TAG, ft.Colors.BLUE_400),
            "x.com": (ft.Icons.TAG, ft.Colors.GREY_900),
            "linkedin": (ft.Icons.WORK, ft.Colors.BLUE_900),
            "instagram": (ft.Icons.CAMERA_ALT, ft.Colors.PINK_600),
            "youtube": (ft.Icons.PLAY_ARROW, ft.Colors.RED_600),
            "tiktok": (ft.Icons.MUSIC_VIDEO, ft.Colors.BLACK),
            "reddit": (ft.Icons.FORUM, ft.Colors.DEEP_ORANGE_500),
            "pinterest": (ft.Icons.PUSH_PIN, ft.Colors.RED_600),
            "snapchat": (ft.Icons.PHOTO_CAMERA, ft.Colors.YELLOW_600),
            # Messagerie
            "whatsapp": (ft.Icons.CHAT_BUBBLE, ft.Colors.GREEN_600),
            "telegram": (ft.Icons.SEND, ft.Colors.BLUE_400),
            "signal": (ft.Icons.SECURITY, ft.Colors.BLUE_600),
            "slack": (ft.Icons.TAG, ft.Colors.PURPLE_700),
            # Tech
            "github": (ft.Icons.CODE, ft.Colors.GREY_900),
            "gitlab": (ft.Icons.CODE, ft.Colors.ORANGE_600),
            "google": (ft.Icons.LANGUAGE, ft.Colors.RED_400),
            "microsoft": (ft.Icons.WINDOW, ft.Colors.BLUE_500),
            "outlook": (ft.Icons.MAIL, ft.Colors.BLUE_600),
            "yahoo": (ft.Icons.MAIL, ft.Colors.PURPLE_600),
            "apple": (ft.Icons.PHONE_IPHONE, ft.Colors.GREY_800),
            # E-commerce
            "amazon": (ft.Icons.SHOPPING_CART, ft.Colors.AMBER_800),
            "galaxus": (ft.Icons.SHOPPING_BAG, ft.Colors.ORANGE_700),
            "digitec": (ft.Icons.COMPASS_CALIBRATION, ft.Colors.BLUE_700),
            "ebay": (ft.Icons.GAVEL, ft.Colors.BLUE_600),
            "aliexpress": (ft.Icons.SHOPPING_BAG, ft.Colors.RED_600),
            "zalando": (ft.Icons.CHECKROOM, ft.Colors.ORANGE_500),
            "etsy": (ft.Icons.STOREFRONT, ft.Colors.ORANGE_700),
            # Finance & Paiement
            "paypal": (ft.Icons.PAYMENT, ft.Colors.BLUE_700),
            "stripe": (ft.Icons.CREDIT_CARD, ft.Colors.INDIGO_500),
            "revolut": (ft.Icons.ACCOUNT_BALANCE, ft.Colors.BLUE_GREY_700),
            # Transport & Voyage
            "uber": (ft.Icons.LOCAL_TAXI, ft.Colors.BLACK),
            "airbnb": (ft.Icons.HOTEL, ft.Colors.RED_400),
            "booking": (ft.Icons.BED, ft.Colors.BLUE_800),
            "sncf": (ft.Icons.TRAIN, ft.Colors.RED_700),
            "sbb": (ft.Icons.TRAIN, ft.Colors.RED_600),
            # Livraison
            "dhl": (ft.Icons.LOCAL_SHIPPING, ft.Colors.YELLOW_700),
            "fedex": (ft.Icons.LOCAL_SHIPPING, ft.Colors.PURPLE_600),
            "laposte": (ft.Icons.LOCAL_POST_OFFICE, ft.Colors.YELLOW_800),
            "ups": (ft.Icons.LOCAL_SHIPPING, ft.Colors.BROWN_700),
            # Divers
            "dropbox": (ft.Icons.CLOUD, ft.Colors.BLUE_500),
            "notion": (ft.Icons.EDIT_NOTE, ft.Colors.GREY_900),
            "trello": (ft.Icons.DASHBOARD, ft.Colors.BLUE_500),
        }
        
        # Charger les icônes personnalisées depuis icon_config.json
        try:
            config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon_config.json")
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    user_config = json.load(f)
                for key, val in user_config.get("custom_icons", {}).items():
                    icon_name = val.get("icon", "EMAIL")
                    color_name = val.get("color", "BLUE_400")
                    icon_val = getattr(ft.Icons, icon_name, ft.Icons.EMAIL)
                    color_val = getattr(ft.Colors, color_name, ft.Colors.BLUE_400)
                    icon_map[key] = (icon_val, color_val)
        except Exception:
            pass  # Silencieux si le fichier est absent ou malformé

        selected_icon = None
        bg_color = None

        for key, val in icon_map.items():
            if key in domain or key in name.lower():
                selected_icon, bg_color = val
                break

        if selected_icon:
            avatar_content = ft.Icon(selected_icon, color=ft.Colors.WHITE, size=20)
        else:
            bg_color = get_avatar_color(name_clean)
            avatar_content = ft.Text(first_letter, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD)

        avatar = ft.CircleAvatar(
            content=avatar_content,
            bgcolor=bg_color,
            radius=20
        )

        unread_indicator = ft.Container(
            width=10,
            height=10,
            bgcolor=ft.Colors.BLUE_400 if is_unread else ft.Colors.TRANSPARENT,
            border_radius=5,
            border=ft.Border.all(1.5, ft.Colors.SURFACE),
            right=0,
            top=0
        )

        return ft.Stack([
            avatar,
            unread_indicator
        ], width=40, height=40)

    # --- COMPOSANTS GRAPHIQUES ---
    status_text = ft.Text("Déconnecté", color=ft.Colors.RED_400, weight=ft.FontWeight.BOLD)
    inbox_lv = ft.ListView(expand=1, spacing=6)
    
    mail_header_sender_avatar = ft.CircleAvatar(radius=18, bgcolor=ft.Colors.BLUE_400)
    mail_header_sender_name = ft.Text("", weight=ft.FontWeight.BOLD, size=14)
    mail_header_sender_email = ft.Text("", color=ft.Colors.ON_SURFACE_VARIANT, size=12)
    mail_header_subject = ft.Text("", size=16, weight=ft.FontWeight.W_600)
    mail_header_date = ft.Text("", color=ft.Colors.ON_SURFACE_VARIANT, size=12)
    attachments_container = ft.Row(wrap=True, spacing=10)
    
    mail_header_container = ft.Column([
        mail_header_subject,
        ft.Row([
            ft.Row([
                mail_header_sender_avatar,
                ft.Column([
                    mail_header_sender_name,
                    mail_header_sender_email
                ], spacing=2)
            ], alignment=ft.MainAxisAlignment.START),
            mail_header_date
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        attachments_container,
        ft.Divider()
    ], visible=False)

    message_area = ft.Markdown(
        value="*Sélectionnez un message pour l'afficher*",
        selectable=True,
        extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
        on_tap_link=lambda e: asyncio.create_task(url_launcher.launch_url(e.data))
    )
    
    # Gestion de la navigation cohérente avec la touche TAB
    def on_field_tab(e: ft.KeyboardEvent, next_control):
        if e.key == "Tab":
            next_control.focus()
            page.update()

    # Auto-complétion optimisée
    to_autocomplete = ft.AutoComplete(
        suggestions=[],
        on_select=lambda e: print(f"Sélectionné: {e.selection.value}")
    )
    to_autocomplete.on_key_down = lambda e: on_field_tab(e, cc_input if cc_input.visible else subject_input)
    
    cc_input = ft.TextField(label="Cc (Copie)", dense=True, visible=False)
    cc_input.on_key_down = lambda e: on_field_tab(e, subject_input)

    subject_input = ft.TextField(label="Objet", dense=True)
    subject_input.on_key_down = lambda e: on_field_tab(e, body_input)

    # Le multiline intercepte désormais Tab pour descendre sur le bouton Envoyer au lieu d'ajouter des espaces
    body_input = ft.TextField(label="Écrire le message...", multiline=True, min_lines=4, max_lines=8)
    body_input.on_key_down = lambda e: on_field_tab(e, send_btn)

    # --- ENVOI DE PIÈCES JOINTES UI ---
    attached_files_row = ft.Row(wrap=True, spacing=5)

    def update_attached_files_ui():
        attached_files_row.controls.clear()
        for path in attached_files:
            filename = os.path.basename(path)
            attached_files_row.controls.append(
                ft.Chip(
                    leading=ft.Icon(ft.Icons.ATTACH_FILE, size=16),
                    label=ft.Text(filename),
                    on_delete=lambda e, p=path: remove_attached_file(p)
                )
            )
        page.update()

    def remove_attached_file(path):
        if path in attached_files:
            attached_files.remove(path)
        update_attached_files_ui()

    # --- GESTION DES PIÈCES JOINTES EN RÉCEPTION ET ENVOI ---
    file_picker = ft.FilePicker()
    attachment_picker = ft.FilePicker()

    async def pick_attachments(e):
        try:
            files = await attachment_picker.pick_files(allow_multiple=True)
            if files:
                for f in files:
                    if f.path and f.path not in attached_files:
                        attached_files.append(f.path)
                update_attached_files_ui()
        except Exception as ex:
            status_text.value = f"Erreur sélection : {ex}"
            status_text.color = ft.Colors.RED_400
            page.update()

    async def trigger_download(att):
        status_text.value = "Téléchargement..."
        status_text.color = ft.Colors.ORANGE_400
        page.update()
        try:
            path = await file_picker.save_file(file_name=att["filename"])
            if path:
                if active_account_type == "gmail":
                    creds = auth.load_credentials(active_account)
                    if creds:
                        svc = gmail.build_service(creds)
                        data = gmail.download_attachment(svc, current_opened_msg_id, att["attachmentId"])
                    else:
                        data = None
                else:
                    data = imap_smtp.download_attachment(
                        active_account, active_account_type, active_account_email,
                        current_folder_query, current_opened_msg_id, att["attachmentId"]
                    )
                
                if data:
                    with open(path, "wb") as f:
                        f.write(data)
                    status_text.value = "Téléchargé !"
                    status_text.color = ft.Colors.GREEN_400
                else:
                    status_text.value = "Échec téléchargement"
                    status_text.color = ft.Colors.RED_400
            else:
                status_text.value = "Annulé"
                status_text.color = ft.Colors.ON_SURFACE_VARIANT
        except Exception as ex:
            status_text.value = f"Erreur : {ex}"
            status_text.color = ft.Colors.RED_400
        page.update()

    # --- ACTIONS RAPIDES SUR L'EMAIL ---
    async def handle_gmail_403(action_name: str):
        """Gère les erreurs 403 en proposant une re-connexion."""
        status_text.value = f"⚠ Permission insuffisante pour '{action_name}'. Reconnexion nécessaire."
        status_text.color = ft.Colors.RED_400
        page.update()
        # Supprimer les credentials obsolètes pour forcer le re-login
        auth.delete_credentials(active_account)

    async def delete_current_msg():
        nonlocal current_opened_msg_id
        if not current_opened_msg_id: return
        status_text.value = "Suppression..."
        status_text.color = ft.Colors.ORANGE_400
        page.update()
        
        success = False
        if active_account_type == "gmail":
            creds = auth.load_credentials(active_account)
            if not creds:
                await handle_gmail_403("supprimer")
                return
            svc = gmail.build_service(creds)
            success = gmail.trash_message(svc, current_opened_msg_id)
        else:
            success = imap_smtp.trash_message(
                active_account, active_account_type, active_account_email,
                current_folder_query, current_opened_msg_id
            )
            
        if success:
            status_text.value = "Déplacé vers Corbeille"
            status_text.color = ft.Colors.GREEN_400
            current_opened_msg_id = None
            mail_header_container.visible = False
            message_area.value = "*Sélectionnez un message pour l'afficher*"
            attachments_container.controls.clear()
            hide_actions()
            await refresh_inbox(clear_list=True)
        else:
            status_text.value = "Erreur de suppression — vérifiez vos permissions"
            status_text.color = ft.Colors.RED_400
        page.update()

    async def toggle_unread_current_msg():
        nonlocal current_opened_msg_id, current_labels
        if not current_opened_msg_id: return
        is_currently_unread = "UNREAD" in current_labels
        status_text.value = "Mise à jour..."
        status_text.color = ft.Colors.ORANGE_400
        page.update()
        
        success = False
        if active_account_type == "gmail":
            creds = auth.load_credentials(active_account)
            if not creds:
                await handle_gmail_403("marquer lu/non lu")
                return
            svc = gmail.build_service(creds)
            success = gmail.mark_message_unread(svc, current_opened_msg_id, unread=not is_currently_unread)
        else:
            success = imap_smtp.mark_message_unread(
                active_account, active_account_type, active_account_email,
                current_folder_query, current_opened_msg_id, unread=not is_currently_unread
            )
            
        if success:
            if is_currently_unread:
                current_labels.remove("UNREAD")
                status_text.value = "Marqué comme lu"
            else:
                current_labels.append("UNREAD")
                status_text.value = "Marqué comme non lu"
            status_text.color = ft.Colors.GREEN_400
            update_unread_button_state()
            await refresh_inbox(clear_list=True)
        else:
            status_text.value = "Erreur — vérifiez vos permissions"
            status_text.color = ft.Colors.RED_400
        page.update()

    async def archive_current_msg():
        nonlocal current_opened_msg_id
        if not current_opened_msg_id: return
        status_text.value = "Archivage..."
        status_text.color = ft.Colors.ORANGE_400
        page.update()
        
        success = False
        if active_account_type == "gmail":
            creds = auth.load_credentials(active_account)
            if not creds:
                await handle_gmail_403("archiver")
                return
            svc = gmail.build_service(creds)
            success = gmail.archive_message(svc, current_opened_msg_id)
        else:
            success = imap_smtp.archive_message(
                active_account, active_account_type, active_account_email,
                current_folder_query, current_opened_msg_id
            )
            
        if success:
            status_text.value = "Archivé !"
            status_text.color = ft.Colors.GREEN_400
            current_opened_msg_id = None
            mail_header_container.visible = False
            message_area.value = "*Sélectionnez un message pour l'afficher*"
            attachments_container.controls.clear()
            hide_actions()
            await refresh_inbox(clear_list=True)
        else:
            status_text.value = "Erreur d'archivage — vérifiez vos permissions"
            status_text.color = ft.Colors.RED_400
        page.update()

    def reply_current_msg(mode="reply"):
        nonlocal current_sender, current_to, current_cc, current_subject, current_date, current_body
        
        match_from = re.search(r'<([^>]+)>', current_sender)
        from_email = match_from.group(1) if match_from else current_sender
        
        if mode == "reply":
            to_autocomplete.value = from_email
            cc_input.visible = False
            toggle_btn.text = "+ Ajouter Cc"
        elif mode == "reply_all":
            to_autocomplete.value = from_email
            all_cc_emails = []
            if current_to:
                to_emails = re.findall(r'[\w\.-]+@[\w\.-]+', current_to)
                for email_addr in to_emails:
                    all_cc_emails.append(email_addr)
            if current_cc:
                cc_emails = re.findall(r'[\w\.-]+@[\w\.-]+', current_cc)
                for email_addr in cc_emails:
                    all_cc_emails.append(email_addr)
            
            all_cc_emails = list(set(all_cc_emails))
            if all_cc_emails:
                cc_input.visible = True
                cc_input.value = ", ".join(all_cc_emails)
                toggle_btn.text = "- Supprimer Cc"
            else:
                cc_input.visible = False
                toggle_btn.text = "+ Ajouter Cc"
        elif mode == "forward":
            to_autocomplete.value = ""
            cc_input.visible = False
            toggle_btn.text = "+ Ajouter Cc"

        prefix = "Fwd: " if mode == "forward" else "Re: "
        subj = current_subject
        if not subj.lower().startswith(prefix.lower()):
            subj = f"{prefix}{subj}"
        subject_input.value = subj

        formatted_orig_body = f"\n\n--- Message d'origine ---\nDe: {current_sender}\nDate: {current_date}\nObjet: {current_subject}\n\n{current_body}"
        body_input.value = formatted_orig_body
        
        if cc_input.visible:
            to_autocomplete.on_key_down = lambda evt: on_field_tab(evt, cc_input)
        else:
            to_autocomplete.on_key_down = lambda evt: on_field_tab(evt, subject_input)

        if mode == "forward":
            to_autocomplete.focus()
        else:
            body_input.focus()
        page.update()

    # --- BOUTONS D'ACTION (COMPOSANTS) ---
    delete_btn = ft.IconButton(
        icon=ft.Icons.DELETE_OUTLINE, 
        tooltip="Supprimer (Déplacer vers la Corbeille)", 
        icon_color=ft.Colors.RED_400,
        on_click=lambda e: asyncio.create_task(delete_current_msg()),
        visible=False
    )
    unread_btn = ft.IconButton(
        icon=ft.Icons.MARK_EMAIL_UNREAD_OUTLINED, 
        tooltip="Marquer comme non lu", 
        icon_color=ft.Colors.BLUE_400,
        on_click=lambda e: asyncio.create_task(toggle_unread_current_msg()),
        visible=False
    )
    archive_btn = ft.IconButton(
        icon=ft.Icons.ARCHIVE_OUTLINED, 
        tooltip="Archiver (Enlever de la Boîte de réception)", 
        icon_color=ft.Colors.GREEN_400,
        on_click=lambda e: asyncio.create_task(archive_current_msg()),
        visible=False
    )
    
    reply_btn = ft.IconButton(
        icon=ft.Icons.REPLY,
        tooltip="Répondre",
        icon_color=ft.Colors.ORANGE_400,
        on_click=lambda e: reply_current_msg(mode="reply"),
        visible=False
    )
    reply_all_btn = ft.IconButton(
        icon=ft.Icons.REPLY_ALL,
        tooltip="Répondre à tous",
        icon_color=ft.Colors.ORANGE_600,
        on_click=lambda e: reply_current_msg(mode="reply_all"),
        visible=False
    )
    forward_btn = ft.IconButton(
        icon=ft.Icons.FORWARD,
        tooltip="Transférer",
        icon_color=ft.Colors.PURPLE_400,
        on_click=lambda e: reply_current_msg(mode="forward"),
        visible=False
    )

    def hide_actions():
        delete_btn.visible = False
        unread_btn.visible = False
        archive_btn.visible = False
        reply_btn.visible = False
        reply_all_btn.visible = False
        forward_btn.visible = False
        page.update()

    def show_actions():
        delete_btn.visible = True
        unread_btn.visible = True
        archive_btn.visible = True
        reply_btn.visible = True
        reply_all_btn.visible = True
        forward_btn.visible = True
        page.update()

    def update_unread_button_state():
        is_currently_unread = "UNREAD" in current_labels
        if is_currently_unread:
            unread_btn.icon = ft.Icons.MARK_EMAIL_READ_OUTLINED
            unread_btn.tooltip = "Marquer comme lu"
        else:
            unread_btn.icon = ft.Icons.MARK_EMAIL_UNREAD_OUTLINED
            unread_btn.tooltip = "Marquer comme non lu"
        page.update()

    # --- LOGIQUE INDÉPENDANTE ---
    
    def toggle_cc(e=None):
        cc_input.visible = not cc_input.visible
        toggle_btn.text = "- Supprimer Cc" if cc_input.visible else "+ Ajouter Cc"
        if cc_input.visible:
            to_autocomplete.on_key_down = lambda evt: on_field_tab(evt, cc_input)
        else:
            to_autocomplete.on_key_down = lambda evt: on_field_tab(evt, subject_input)
        page.update()

    toggle_btn = ft.TextButton("+ Ajouter Cc", on_click=toggle_cc)
    send_btn = ft.Button(
        "Envoyer", 
        icon=ft.Icons.SEND, 
        on_click=lambda e: asyncio.create_task(send_mail_click()), 
        bgcolor=ft.Colors.BLUE_700, 
        color=ft.Colors.WHITE
    )

    account_dropdown = ft.Dropdown(
        label="Compte actif",
        value=active_account,
        options=[ft.DropdownOption(key=acc["id"], text=acc["email"] if acc["email"] else acc["id"]) for acc in accounts],
        width=180,
        dense=True,
        on_select=lambda e: asyncio.create_task(change_account(e.control.value))
    )

    async def send_mail_click():
        to_value = to_autocomplete.value if hasattr(to_autocomplete, 'value') else ""
        if not to_value: return
        status_text.value = "Envoi..."
        status_text.color = ft.Colors.ORANGE_400
        page.update()
        
        success = False
        if active_account_type == "gmail":
            creds = auth.load_credentials(active_account)
            if creds:
                svc = gmail.build_service(creds)
                success = gmail.send_email(
                    svc, 
                    to=to_value, 
                    subject=subject_input.value, 
                    body=body_input.value, 
                    cc=cc_input.value if cc_input.visible else None,
                    attachment_paths=attached_files
                )
        else:
            success = imap_smtp.send_email(
                active_account, active_account_type, active_account_email,
                to=to_value, subject=subject_input.value, body=body_input.value,
                cc=cc_input.value if cc_input.visible else None, attachment_paths=attached_files
            )
            
        if success:
            status_text.value = "Envoyé !"
            status_text.color = ft.Colors.GREEN_400
            subject_input.value = ""
            body_input.value = ""
            attached_files.clear()
            update_attached_files_ui()
        else:
            status_text.value = "Erreur d'envoi"
            status_text.color = ft.Colors.RED_400
        page.update()

    async def show_message(msg_id):
        nonlocal current_opened_msg_id, current_sender, current_to, current_cc, current_subject, current_date, current_body, current_labels
        current_opened_msg_id = msg_id
        
        if active_account_type == "gmail":
            creds = auth.load_credentials(active_account)
            if not creds: return
            svc = gmail.build_service(creds)
            
            meta = svc.users().messages().get(userId="me", id=msg_id, format="metadata", metadataHeaders=["From","To","Cc","Subject","Date"]).execute()
            headers = {h["name"]: h["value"] for h in meta.get("payload", {}).get("headers", [])}
            
            current_sender = headers.get('From', '(Inconnu)')
            current_to = headers.get('To', '')
            current_cc = headers.get('Cc', '')
            current_subject = headers.get('Subject', '(Sans objet)')
            current_date = headers.get('Date', '')
            current_labels = meta.get('labelIds', [])
            
            body, attachments = gmail.get_message_details(svc, msg_id, show_images=show_images_state)
            current_body = body
        else:
            body, attachments, headers, label_ids = imap_smtp.get_message_details(
                active_account, active_account_type, active_account_email,
                current_folder_query, msg_id
            )
            current_sender = headers.get('From', '(Inconnu)')
            current_to = headers.get('To', '')
            current_cc = headers.get('Cc', '')
            current_subject = headers.get('Subject', '(Sans objet)')
            current_date = headers.get('Date', '')
            current_labels = label_ids
            current_body = body
        
        # Découpe et rendu élégant de l'expéditeur
        match_sender = re.search(r'([^<]*)\s*<([^>]*)>', current_sender)
        if match_sender:
            sender_name = match_sender.group(1).strip().replace('"', '')
            sender_email = match_sender.group(2).strip()
        else:
            if "@" in current_sender:
                sender_email = current_sender.strip()
                sender_name = sender_email.split("@")[0]
            else:
                sender_name = current_sender
                sender_email = ""

        mail_header_sender_name.value = sender_name
        mail_header_sender_email.value = f"<{sender_email}>" if sender_email else ""
        mail_header_date.value = current_date
        mail_header_subject.value = current_subject
        
        # Applique le CircleAvatar
        avatar_control = get_sender_avatar(current_sender, is_unread=False)
        mail_header_sender_avatar.content = avatar_control.controls[0].content
        mail_header_sender_avatar.bgcolor = avatar_control.controls[0].bgcolor
        
        mail_header_container.visible = True

        rendered_body = render_text(current_body)
        if show_images_state:
            rendered_body = re.sub(r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>', r'![](\1)', rendered_body)

        message_area.value = rendered_body

        # Chips pour les pièces jointes
        attachments_container.controls.clear()
        for att in attachments:
            attachments_container.controls.append(
                ft.Chip(
                    leading=ft.Icon(ft.Icons.ATTACH_FILE, size=16),
                    label=ft.Text(f"{att['filename']} ({att['size'] // 1024} Ko)"),
                    on_click=lambda e, a=att: asyncio.create_task(trigger_download(a))
                )
            )

        show_actions()
        update_unread_button_state()
        page.update()

    async def refresh_inbox(page_token=None, clear_list=True):
        status_text.value = "Synchro..."
        status_text.color = ft.Colors.ORANGE_400
        page.update()
        
        mails = []
        next_token = None
        
        if active_account_type == "gmail":
            creds = auth.load_credentials(active_account)
            if not creds: 
                status_text.value = "Reconnexion requise"
                status_text.color = ft.Colors.RED_400
                page.update()
                return
                
            svc = gmail.build_service(creds)
            
            # Récupération et auto-remplissage de l'email si absent
            nonlocal active_account_email
            if not active_account_email:
                try:
                    profile = svc.users().getProfile(userId="me").execute()
                    active_account_email = profile.get("emailAddress")
                    local_db.add_account(active_account, acc_type="gmail", email=active_account_email)
                    for acc in accounts:
                        if acc["id"] == active_account:
                            acc["email"] = active_account_email
                            break
                    account_dropdown.options.clear()
                    for acc in accounts:
                        account_dropdown.options.append(ft.DropdownOption(key=acc["id"], text=acc["email"] if acc["email"] else acc["id"]))
                except Exception:
                    pass
            
            full_query = current_folder_query
            if search_text_query:
                full_query += f" {search_text_query}"

            mails, next_token = gmail.list_messages_headers(svc, max_results=25, page_token=page_token, query_string=full_query)
        else:
            # imap
            mails, next_token = imap_smtp.list_messages_headers(
                active_account, active_account_type, active_account_email, 
                current_folder_query, max_results=25, page_token=page_token
            )
            
        nonlocal current_page_token
        current_page_token = next_token
        
        if clear_list:
            inbox_lv.controls.clear()
            
        if inbox_lv.controls and isinstance(inbox_lv.controls[-1], ft.TextButton):
            inbox_lv.controls.pop()

        for m in mails:
            headers = m.get("headers", {})
            raw_sender = headers.get("From", "")
            
            if raw_sender:
                match = re.search(r'([^<]*)\s*<([^>]*)>', raw_sender)
                if match:
                    clean_name = match.group(1).strip().replace('"', '')
                    clean_email = match.group(2).strip()
                    if clean_email:
                        cached_contacts.add(f"{clean_name} <{clean_email}>" if clean_name else clean_email)
                else:
                    cached_contacts.add(raw_sender.strip())

            # Extraction propre du nom d'expéditeur
            sender_display_name = raw_sender
            match_name = re.search(r'([^<]*)\s*<([^>]*)>', raw_sender)
            if match_name:
                sender_display_name = match_name.group(1).strip().replace('"', '') or match_name.group(2).split("@")[0]
            elif "@" in raw_sender:
                sender_display_name = raw_sender.strip().split("@")[0]
            
            # Extraction de la date courte
            raw_date = headers.get("Date", "")
            short_date = raw_date
            # Tenter d'extraire juste "06 Jun" ou "HH:MM" 
            date_match = re.search(r'(\d{1,2}\s+\w{3}\s+\d{4})', raw_date)
            if date_match:
                short_date = date_match.group(1)
            else:
                time_match = re.search(r'(\d{1,2}:\d{2})', raw_date)
                if time_match:
                    short_date = time_match.group(1)

            # Détection de l'état UNREAD pour point bleu & sujet en gras
            labels = m.get("labelIds", [])
            is_unread = "UNREAD" in labels

            inbox_lv.controls.append(
                ft.ListTile(
                    leading=get_sender_avatar(raw_sender, is_unread),
                    title=ft.Row([
                        ft.Text(
                            sender_display_name, 
                            max_lines=1, 
                            overflow=ft.TextOverflow.ELLIPSIS, 
                            weight=ft.FontWeight.BOLD if is_unread else ft.FontWeight.W_500,
                            expand=True
                        ),
                        ft.Text(
                            short_date,
                            size=11,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            no_wrap=True
                        )
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    subtitle=ft.Column([
                        ft.Text(
                            headers.get("Subject", "(Sans objet)"), 
                            max_lines=1, 
                            overflow=ft.TextOverflow.ELLIPSIS, 
                            weight=ft.FontWeight.W_500 if is_unread else ft.FontWeight.NORMAL,
                            size=13
                        ),
                        ft.Text(
                            m.get('snippet', ''), 
                            max_lines=1, 
                            overflow=ft.TextOverflow.ELLIPSIS, 
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            size=12
                        )
                    ], spacing=2),
                    is_three_line=True,
                    data=m["id"],
                    on_click=lambda e: asyncio.create_task(show_message(e.control.data))
                )
            )
            
        if current_page_token:
            inbox_lv.controls.append(
                ft.TextButton("Charger plus...", icon=ft.Icons.ARROW_DOWNWARD, on_click=lambda e: asyncio.create_task(refresh_inbox(page_token=current_page_token, clear_list=False)))
            )
            
        to_autocomplete.suggestions = [ft.AutoCompleteSuggestion(key=c, value=c) for c in cached_contacts]
        status_text.value = "À jour"
        status_text.color = ft.Colors.GREEN_400
        page.update()

    async def change_account(acc_id):
        nonlocal active_account
        update_active_account_details(acc_id)
        await refresh_inbox(clear_list=True)

    async def change_folder(folder_query):
        nonlocal current_folder_query
        current_folder_query = folder_query
        await refresh_inbox(clear_list=True)

    # --- FLUX DE CONNEXION GOOGLE OAUTH ---
    async def add_account_flow(e):
        status_text.value = "Authentification..."
        status_text.color = ft.Colors.ORANGE_400
        page.update()
        
        is_relogin = (active_account_type == "gmail" and not auth.load_credentials(active_account))
        new_id = active_account if is_relogin else f"user_{len(accounts) + 1}"
        
        try:
            creds = auth.run_console_flow(new_id) 
            if creds:
                svc = gmail.build_service(creds)
                try:
                    profile = svc.users().getProfile(userId="me").execute()
                    user_email = profile.get("emailAddress")
                except Exception:
                    user_email = None
                
                local_db.add_account(new_id, acc_type="gmail", email=user_email)
                
                if not any(a["id"] == new_id for a in accounts):
                    accounts.append({"id": new_id, "type": "gmail", "email": user_email})
                    account_dropdown.options.append(ft.DropdownOption(key=new_id, text=user_email if user_email else new_id))
                else:
                    for acc in accounts:
                        if acc["id"] == new_id:
                            acc["email"] = user_email
                            break
                    account_dropdown.options.clear()
                    for acc in accounts:
                        account_dropdown.options.append(ft.DropdownOption(key=acc["id"], text=acc["email"] if acc["email"] else acc["id"]))
                
                account_dropdown.value = new_id
                update_active_account_details(new_id)
                status_text.value = f"Compte {user_email or new_id} connecté !"
                status_text.color = ft.Colors.GREEN_400
                await refresh_inbox(clear_list=True)
            else:
                status_text.value = "Échec authentification"
                status_text.color = ft.Colors.RED_400
        except Exception as ex:
            status_text.value = "Erreur d'authentification"
            status_text.color = ft.Colors.RED_400
            print(f"Erreur lors du flux OAuth: {ex}")
        page.update()

    # --- POPUP ET FORMULAIRES DE CONNEXION MULTI-COMPTES (OUTLOOK / YAHOO) ---
    provider_selected = "gmail"
    email_field = ft.TextField(label="Adresse email", dense=True)
    password_field = ft.TextField(label="Mot de passe (ou mdp d'application)", dense=True, password=True, can_reveal_password=True)
    login_error_text = ft.Text("", color=ft.Colors.RED_400, weight=ft.FontWeight.BOLD)

    def close_dlg(e):
        add_account_dlg.open = False
        page.update()

    async def test_and_add_imap_account(e):
        email_val = email_field.value.strip()
        pwd_val = password_field.value.strip()
        if not email_val or not pwd_val:
            login_error_text.value = "Veuillez remplir tous les champs."
            page.update()
            return
        
        login_error_text.value = "Connexion..."
        page.update()
        
        new_id = f"imap_{len(accounts) + 1}"
        config = imap_smtp.SERVERS.get(provider_selected)
        
        try:
            def test_conn():
                imap = imaplib.IMAP4_SSL(config["imap_host"], config["imap_port"])
                imap.login(email_val, pwd_val)
                imap.logout()
            
            await asyncio.get_event_loop().run_in_executor(None, test_conn)
            
            keyring.set_password(imap_smtp.KEYRING_SERVICE, new_id, pwd_val)
            local_db.add_account(new_id, acc_type=provider_selected, email=email_val)
            
            accounts.append({"id": new_id, "type": provider_selected, "email": email_val})
            
            account_dropdown.options.clear()
            for acc in accounts:
                account_dropdown.options.append(ft.DropdownOption(key=acc["id"], text=acc["email"] if acc["email"] else acc["id"]))
            account_dropdown.value = new_id
            
            update_active_account_details(new_id)
            
            status_text.value = f"Compte {email_val} connecté !"
            status_text.color = ft.Colors.GREEN_400
            
            add_account_dlg.open = False
            page.update()
            await refresh_inbox(clear_list=True)
            
        except Exception as ex:
            login_error_text.value = f"Erreur : Vérifiez votre mot de passe d'application"
            page.update()

    def select_provider(provider):
        nonlocal provider_selected
        provider_selected = provider
        login_error_text.value = ""
        email_field.value = ""
        password_field.value = ""
        
        if provider == "gmail":
            add_account_dlg.open = False
            page.update()
            asyncio.create_task(add_account_flow(None))
        else:
            # Instructions spécifiques par fournisseur
            if provider == "outlook":
                help_text = ft.Container(
                    content=ft.Column([
                        ft.Text("💡 Instructions :", weight=ft.FontWeight.BOLD, size=12, color=ft.Colors.BLUE_400),
                        ft.Text("1. Allez sur account.microsoft.com → Sécurité", size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                        ft.Text("2. Activez la vérification en 2 étapes", size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                        ft.Text("3. Créez un 'Mot de passe d'application'", size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                        ft.Text("4. Utilisez ce mot de passe ci-dessous", size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                        ft.Text("⚠ Comptes d'organisation : IMAP doit être activé par votre admin", size=11, color=ft.Colors.ORANGE_400),
                    ], spacing=2),
                    padding=ft.Padding(10, 8, 10, 8),
                    bgcolor=ft.Colors.ON_PRIMARY,
                    border_radius=8
                )
            else:  # yahoo
                help_text = ft.Container(
                    content=ft.Column([
                        ft.Text("💡 Instructions :", weight=ft.FontWeight.BOLD, size=12, color=ft.Colors.PURPLE_400),
                        ft.Text("1. Allez sur login.yahoo.com → Sécurité du compte", size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                        ft.Text("2. Activez la vérification en 2 étapes", size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                        ft.Text("3. Générez un 'Mot de passe d'application'", size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                        ft.Text("4. Choisissez 'Autre application' et utilisez le mot de passe généré", size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                    ], spacing=2),
                    padding=ft.Padding(10, 8, 10, 8),
                    bgcolor=ft.Colors.ON_PRIMARY,
                    border_radius=8
                )
            
            dialog_content.controls = [
                ft.Text(f"Connexion Compte {provider.capitalize()}", weight=ft.FontWeight.BOLD, size=16),
                help_text,
                email_field,
                password_field,
                login_error_text,
                ft.Row([
                    ft.TextButton("Annuler", on_click=close_dlg),
                    ft.ElevatedButton("Se connecter", on_click=lambda evt: asyncio.create_task(test_and_add_imap_account(evt)))
                ], alignment=ft.MainAxisAlignment.END)
            ]
            page.update()

    dialog_content = ft.Column([
        ft.Text("Choisir votre fournisseur email", size=16, weight=ft.FontWeight.BOLD),
        ft.ListTile(
            leading=ft.Icon(ft.Icons.LANGUAGE, color=ft.Colors.RED_400),
            title=ft.Text("Google / Gmail"),
            on_click=lambda e: select_provider("gmail")
        ),
        ft.ListTile(
            leading=ft.Icon(ft.Icons.WINDOW, color=ft.Colors.BLUE_400),
            title=ft.Text("Outlook / Office 365"),
            on_click=lambda e: select_provider("outlook")
        ),
        ft.ListTile(
            leading=ft.Icon(ft.Icons.EMOJI_EMOTIONS, color=ft.Colors.PURPLE_400),
            title=ft.Text("Yahoo Mail"),
            on_click=lambda e: select_provider("yahoo")
        ),
        ft.Row([
            ft.TextButton("Fermer", on_click=close_dlg)
        ], alignment=ft.MainAxisAlignment.END)
    ], tight=True, spacing=10, width=400)

    add_account_dlg = ft.AlertDialog(
        content=dialog_content,
        modal=True
    )
    page.overlay.append(add_account_dlg)

    def open_add_account_dialog(e):
        dialog_content.controls = [
            ft.Text("Choisir votre fournisseur email", size=16, weight=ft.FontWeight.BOLD),
            ft.ListTile(
                leading=ft.Icon(ft.Icons.LANGUAGE, color=ft.Colors.RED_400),
                title=ft.Text("Google / Gmail"),
                on_click=lambda e: select_provider("gmail")
            ),
            ft.ListTile(
                leading=ft.Icon(ft.Icons.WINDOW, color=ft.Colors.BLUE_400),
                title=ft.Text("Outlook / Office 365"),
                on_click=lambda e: select_provider("outlook")
            ),
            ft.ListTile(
                leading=ft.Icon(ft.Icons.EMOJI_FOOD_BEVERAGE, color=ft.Colors.PURPLE_400),
                title=ft.Text("Yahoo Mail"),
                on_click=lambda e: select_provider("yahoo")
            ),
            ft.Row([
                ft.TextButton("Fermer", on_click=close_dlg)
            ], alignment=ft.MainAxisAlignment.END)
        ]
        add_account_dlg.open = True
        page.update()

    # --- BARRE DE RECHERCHE ET MISE EN PAGE ---
    async def trigger_search(e):
        nonlocal search_text_query
        search_text_query = e.control.value
        await refresh_inbox(clear_list=True)
    
    async def toggle_images(e):
        nonlocal show_images_state
        show_images_state = not show_images_state
        img_toggle_btn.icon = ft.Icons.IMAGE if show_images_state else ft.Icons.IMAGE_NOT_SUPPORTED
        if current_opened_msg_id: await show_message(current_opened_msg_id)

    img_toggle_btn = ft.IconButton(icon=ft.Icons.IMAGE_NOT_SUPPORTED, on_click=lambda e: asyncio.create_task(toggle_images(e)))

    search_bar = ft.TextField(
        hint_text="Rechercher (ex: from:tiktok, subject:commande)...",
        prefix_icon=ft.Icons.SEARCH,
        dense=True,
        expand=True,
        on_submit=lambda e: asyncio.create_task(trigger_search(e))
    )

    to_container = ft.Column([
        ft.Text("À (Destinataire)", size=12, weight="bold"), 
        to_autocomplete
    ], expand=True)

    compose_form = ft.Column([
        ft.Divider(),
        ft.Row([to_container, toggle_btn], vertical_alignment=ft.CrossAxisAlignment.END),
        cc_input, subject_input, body_input,
        attached_files_row,
        ft.Row([
            ft.IconButton(
                icon=ft.Icons.ATTACHMENT_OUTLINED, 
                tooltip="Joindre des fichiers", 
                on_click=lambda e: asyncio.create_task(pick_attachments(e))
            ),
            send_btn
        ], alignment=ft.MainAxisAlignment.END)
    ])

    folders_menu = ft.NavigationRail(
        selected_index=0,
        label_type=ft.NavigationRailLabelType.ALL,
        min_width=100,
        width=110,
        destinations=[
            ft.NavigationRailDestination(icon=ft.Icons.INBOX, label="Boîte de réc."),
            ft.NavigationRailDestination(icon=ft.Icons.SEND_AND_ARCHIVE, label="Envoyés"),
            ft.NavigationRailDestination(icon=ft.Icons.REPORT, label="Spam"),
            ft.NavigationRailDestination(icon=ft.Icons.DELETE, label="Corbeille"),
        ],
        on_change=lambda e: asyncio.create_task(change_folder([
            "label:INBOX", "label:SENT", "label:SPAM", "label:TRASH"
        ][e.control.selected_index]))
    )

    page.add(
        ft.Row([
            account_dropdown,
            ft.IconButton(icon=ft.Icons.ADD_LINK, tooltip="Ajouter un compte", on_click=open_add_account_dialog),
            search_bar,
            status_text
        ]),
        ft.Row([
            folders_menu, 
            ft.Column([
                ft.Container(content=inbox_lv, border=ft.Border.all(1, ft.Colors.OUTLINE), border_radius=8, padding=5, expand=True)
            ], expand=4),
            ft.Column([
                ft.Row([
                    ft.Text("Lecture", size=16, weight="bold"), 
                    ft.Row([
                        reply_btn, reply_all_btn, forward_btn,
                        archive_btn, unread_btn, delete_btn
                    ], spacing=5),
                    img_toggle_btn
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Container(
                    content=ft.Column(controls=[mail_header_container, message_area], scroll=ft.ScrollMode.ALWAYS, expand=True),
                    border=ft.Border.all(1, ft.Colors.OUTLINE), border_radius=8, padding=15, expand=True,
                ),
                compose_form
            ], expand=6)
        ], expand=True)
    )
    
    asyncio.create_task(refresh_inbox(clear_list=True))
    page.update()

if __name__ == "__main__":
    ft.run(main)