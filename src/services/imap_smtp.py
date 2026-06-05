import keyring
import imaplib
import smtplib
import email
from email.header import decode_header
import base64
import os
import mimetypes
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from html import unescape
from typing import Tuple, List, Dict, Optional

KEYRING_SERVICE = "flet-mail-mvp"

SERVERS = {
    "outlook": {
        "imap_host": "outlook.office365.com",
        "imap_port": 993,
        "smtp_host": "smtp.office365.com",
        "smtp_port": 587,
        "use_starttls": True
    },
    "yahoo": {
        "imap_host": "imap.mail.yahoo.com",
        "imap_port": 993,
        "smtp_host": "smtp.mail.yahoo.com",
        "smtp_port": 465,
        "use_starttls": False
    }
}

def connect_imap(account_id: str, account_type: str, email_addr: str):
    password = keyring.get_password(KEYRING_SERVICE, account_id)
    if not password:
        raise ValueError("Mot de passe introuvable dans le trousseau de clés.")
    
    config = SERVERS.get(account_type)
    if not config:
        raise ValueError(f"Type de compte inconnu: {account_type}")
    
    imap = imaplib.IMAP4_SSL(config["imap_host"], config["imap_port"])
    imap.login(email_addr, password)
    return imap

def get_imap_folder(account_type: str, folder_query: str) -> str:
    if "label:SENT" in folder_query:
        return "Sent Items" if account_type == "outlook" else "Sent"
    elif "label:SPAM" in folder_query:
        return "Junk Email" if account_type == "outlook" else "Bulk Mail"
    elif "label:TRASH" in folder_query:
        return "Deleted Items" if account_type == "outlook" else "Trash"
    return "INBOX"

def list_messages_headers(account_id: str, account_type: str, email_addr: str, folder_query: str, max_results=25, page_token=None) -> Tuple[List[Dict], Optional[str]]:
    try:
        imap = connect_imap(account_id, account_type, email_addr)
        folder = get_imap_folder(account_type, folder_query)
        imap.select(folder, readonly=True)
        
        status, messages = imap.search(None, "ALL")
        if status != "OK":
            return [], None
        
        msg_ids = messages[0].split()
        if not msg_ids:
            return [], None
        
        msg_ids.reverse()
        
        start_idx = 0
        if page_token:
            try:
                start_idx = int(page_token)
            except ValueError:
                pass
        
        end_idx = start_idx + max_results
        slice_ids = msg_ids[start_idx:end_idx]
        
        out = []
        for msg_uid in slice_ids:
            res, data = imap.fetch(msg_uid, "(BODY.PEEK[HEADER.FIELDS (FROM TO CC SUBJECT DATE)])")
            if res != "OK" or not data:
                continue
            
            msg = email.message_from_bytes(data[0][1])
            
            def decode_mime_header(h):
                if not h: return ""
                decoded = decode_header(h)
                parts = []
                for val, char in decoded:
                    if isinstance(val, bytes):
                        parts.append(val.decode(char or "utf-8", errors="replace"))
                    else:
                        parts.append(val)
                return "".join(parts)
            
            subject = decode_mime_header(msg.get("Subject"))
            sender = decode_mime_header(msg.get("From"))
            date_str = decode_mime_header(msg.get("Date"))
            
            res_flags, flags_data = imap.fetch(msg_uid, "(FLAGS)")
            is_unread = True
            if res_flags == "OK" and flags_data:
                try:
                    flags_str = flags_data[0].decode("utf-8")
                    if "\\Seen" in flags_str:
                        is_unread = False
                except Exception:
                    pass
            
            out.append({
                "id": msg_uid.decode("utf-8"),
                "snippet": "",
                "headers": {
                    "From": sender,
                    "Subject": subject,
                    "Date": date_str,
                    "To": decode_mime_header(msg.get("To")),
                    "Cc": decode_mime_header(msg.get("Cc"))
                },
                "labelIds": ["UNREAD"] if is_unread else []
            })
        
        next_token = str(end_idx) if end_idx < len(msg_ids) else None
        imap.logout()
        return out, next_token
    except Exception as e:
        print(f"Erreur listage IMAP: {e}")
        return [], None

def get_message_details(account_id: str, account_type: str, email_addr: str, folder_query: str, msg_id: str) -> Tuple[str, List[Dict], Dict, List[str]]:
    try:
        imap = connect_imap(account_id, account_type, email_addr)
        folder = get_imap_folder(account_type, folder_query)
        imap.select(folder, readonly=False)
        
        res, data = imap.fetch(msg_id.encode("utf-8"), "(RFC822)")
        if res != "OK" or not data:
            return "", [], {}, []
            
        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)
        
        def decode_mime_header(h):
            if not h: return ""
            decoded = decode_header(h)
            parts = []
            for val, char in decoded:
                if isinstance(val, bytes):
                    parts.append(val.decode(char or "utf-8", errors="replace"))
                else:
                    parts.append(val)
            return "".join(parts)

        headers = {
            "From": decode_mime_header(msg.get("From")),
            "To": decode_mime_header(msg.get("To")),
            "Cc": decode_mime_header(msg.get("Cc")),
            "Subject": decode_mime_header(msg.get("Subject")),
            "Date": decode_mime_header(msg.get("Date"))
        }
        
        res_flags, flags_data = imap.fetch(msg_id.encode("utf-8"), "(FLAGS)")
        label_ids = []
        if res_flags == "OK" and flags_data:
            try:
                flags_str = flags_data[0].decode("utf-8")
                if "\\Seen" not in flags_str:
                    label_ids.append("UNREAD")
            except Exception:
                pass
        
        # Marquer comme lu
        imap.store(msg_id.encode("utf-8"), "+FLAGS", "\\Seen")
        
        html_parts = []
        plain_parts = []
        attachments = []
        
        part_counter = 0
        for part in msg.walk():
            part_counter += 1
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            filename = part.get_filename()
            
            if filename:
                filename = decode_mime_header(filename)
            
            if filename or "attachment" in content_disposition:
                if not filename:
                    filename = f"piece_jointe_{part_counter}"
                attachments.append({
                    "filename": filename,
                    "mimeType": content_type,
                    "attachmentId": str(part_counter),
                    "size": len(part.get_payload(decode=True) or b"")
                })
                continue
            
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    plain_parts.append(payload.decode(part.get_content_charset() or "utf-8", errors="replace"))
            elif content_type == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    html_parts.append(payload.decode(part.get_content_charset() or "utf-8", errors="replace"))
                    
        body_text = ""
        if html_parts:
            from src.services.gmail import EmailMarkdownParser
            parser = EmailMarkdownParser(allow_images=False)
            parser.feed("\n".join(html_parts))
            body_text = parser.get_markdown()
            
        if not body_text:
            body_text = "\n\n".join(plain_parts) if plain_parts else ""
            
        imap.logout()
        return body_text, attachments, headers, label_ids
    except Exception as e:
        print(f"Erreur détails IMAP message: {e}")
        return "", [], {}, []

def download_attachment(account_id: str, account_type: str, email_addr: str, folder_query: str, msg_id: str, attachment_id: str) -> bytes:
    try:
        imap = connect_imap(account_id, account_type, email_addr)
        folder = get_imap_folder(account_type, folder_query)
        imap.select(folder, readonly=True)
        
        res, data = imap.fetch(msg_id.encode("utf-8"), "(RFC822)")
        if res != "OK" or not data:
            return b""
            
        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)
        
        part_counter = 0
        for part in msg.walk():
            part_counter += 1
            if str(part_counter) == attachment_id:
                payload = part.get_payload(decode=True)
                imap.logout()
                return payload if payload else b""
        
        imap.logout()
        return b""
    except Exception as e:
        print(f"Erreur téléchargement IMAP: {e}")
        return b""

def send_email(account_id: str, account_type: str, email_addr: str, to: str, subject: str, body: str, cc: str = None, attachment_paths: list = None) -> bool:
    try:
        password = keyring.get_password(KEYRING_SERVICE, account_id)
        if not password:
            raise ValueError("Mot de passe introuvable.")
            
        config = SERVERS.get(account_type)
        if not config:
            raise ValueError(f"Type de compte inconnu: {account_type}")
        
        message = MIMEMultipart()
        message["From"] = email_addr
        message["To"] = to
        message["Subject"] = subject
        if cc:
            message["Cc"] = cc
            
        message.attach(MIMEText(body, "plain"))
        
        if attachment_paths:
            for path in attachment_paths:
                if not os.path.exists(path):
                    continue
                filename = os.path.basename(path)
                mime_type, _ = mimetypes.guess_type(path)
                if mime_type is None:
                    mime_type = "application/octet-stream"
                main_type, sub_type = mime_type.split("/", 1)
                
                with open(path, "rb") as fp:
                    part = MIMEBase(main_type, sub_type)
                    part.set_payload(fp.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", "attachment", filename=filename)
                message.attach(part)
                
        if config["use_starttls"]:
            server = smtplib.SMTP(config["smtp_host"], config["smtp_port"])
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(config["smtp_host"], config["smtp_port"])
            
        server.login(email_addr, password)
        
        recipients = [to]
        if cc:
            recipients.extend([c.strip() for c in cc.split(",")])
            
        server.sendmail(email_addr, recipients, message.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Erreur d'envoi SMTP: {e}")
        return False

def trash_message(account_id: str, account_type: str, email_addr: str, folder_query: str, msg_id: str) -> bool:
    try:
        imap = connect_imap(account_id, account_type, email_addr)
        folder = get_imap_folder(account_type, folder_query)
        imap.select(folder, readonly=False)
        
        trash_folder = get_imap_folder(account_type, "label:TRASH")
        
        res, _ = imap.copy(msg_id.encode("utf-8"), trash_folder)
        if res == "OK":
            imap.store(msg_id.encode("utf-8"), "+FLAGS", "\\Deleted")
            imap.expunge()
            imap.logout()
            return True
        imap.logout()
        return False
    except Exception as e:
        print(f"Erreur déplacement corbeille IMAP: {e}")
        return False

def archive_message(account_id: str, account_type: str, email_addr: str, folder_query: str, msg_id: str) -> bool:
    try:
        imap = connect_imap(account_id, account_type, email_addr)
        folder = get_imap_folder(account_type, folder_query)
        imap.select(folder, readonly=False)
        
        res, _ = imap.copy(msg_id.encode("utf-8"), "Archive")
        if res == "OK":
            imap.store(msg_id.encode("utf-8"), "+FLAGS", "\\Deleted")
            imap.expunge()
            imap.logout()
            return True
        imap.logout()
        return False
    except Exception as e:
        print(f"Erreur archivage IMAP: {e}")
        return False

def mark_message_unread(account_id: str, account_type: str, email_addr: str, folder_query: str, msg_id: str, unread: bool) -> bool:
    try:
        imap = connect_imap(account_id, account_type, email_addr)
        folder = get_imap_folder(account_type, folder_query)
        imap.select(folder, readonly=False)
        
        if unread:
            imap.store(msg_id.encode("utf-8"), "-FLAGS", "\\Seen")
        else:
            imap.store(msg_id.encode("utf-8"), "+FLAGS", "\\Seen")
        imap.logout()
        return True
    except Exception as e:
        print(f"Erreur marquage lu/non lu IMAP: {e}")
        return False
