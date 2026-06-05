import base64
import time
from html import unescape # Pour corriger le bug des caractères comme '
from html.parser import HTMLParser
from googleapiclient.discovery import build
import re
from typing import List, Dict, Tuple, Optional

def build_service(creds):
    return build("gmail", "v1", credentials=creds, cache_discovery=False)

# Récupération ultra-rapide grâce au Batching
def list_messages_headers(service, user_id="me", max_results=25, page_token=None, query_string="") -> Tuple[List[Dict], Optional[str]]:
    try:
        resp = service.users().messages().list(
            userId=user_id, maxResults=max_results, pageToken=page_token, q=query_string
        ).execute()
        
        msgs = resp.get("messages", []) or []
        next_page_token = resp.get("nextPageToken", None)
        
        out = []
        if not msgs:
            return [], None

        # Callback interne pour traiter les réponses du lot
        def batch_callback(request_id, response, exception):
            if exception is None:
                headers = {h["name"]: h["value"] for h in response.get("payload", {}).get("headers", [])}
                out.append({
                    "id": response["id"],
                    "snippet": unescape(response.get("snippet", "")),
                    "headers": headers,
                    "labelIds": response.get("labelIds", [])
                })
            else:
                # Si Google rejette quand même un message, on évite le crash global
                print(f"Erreur batch message {request_id}: {exception}")

        # ASTUCE ANTI-429 : Découper les 25 messages en sous-lots de 10 max
        chunk_size = 10
        for i in range(0, len(msgs), chunk_size):
            chunk = msgs[i:i + chunk_size]
            
            # On crée un batch dédié pour ce sous-lot
            batch = service.new_batch_http_request(callback=batch_callback)
            for m in chunk:
                batch.add(service.users().messages().get(
                    userId=user_id, id=m["id"], format="metadata",
                    metadataHeaders=["From", "Subject", "Date"]
                ))
            
            # Exécution du sous-lot
            batch.execute()
            
            # Une micro-pause optionnelle si ton compte est très restrictif (ex: 0.05s)
            # time.sleep(0.05)

        return out, next_page_token
    except Exception as e:
        print(f"Erreur API Gmail List : {e}")
        return [], None

class EmailMarkdownParser(HTMLParser):
    def __init__(self, allow_images=False):
        super().__init__()
        self.result = []
        self.in_style_or_script = False
        self.current_link_url = None
        self.link_text_buffer = []
        self.allow_images = allow_images

    def handle_starttag(self, tag, attrs):
        if tag in ["style", "script", "head", "meta", "title"]:
            self.in_style_or_script = True
            return
        
        attrs_dict = dict(attrs)

        if tag == "img" and not self.in_style_or_script and self.allow_images:
            src = attrs_dict.get("src")
            if src and src.startswith("http"):
                self.result.append(f' <img src="{src}" style="max-height:60px; max-width:180px; display:inline-block; vertical-align:middle; margin:2px;" /> ')

        elif tag == "a" and not self.in_style_or_script:
            self.current_link_url = attrs_dict.get("href")
            self.link_text_buffer = []

        elif tag in ["p", "div", "tr", "br"] and not self.in_style_or_script:
            self.result.append("\n")
        elif tag in ["h1", "h2", "h3"] and not self.in_style_or_script:
            self.result.append("\n\n### ")

    def handle_endtag(self, tag):
        if tag in ["style", "script", "head", "meta", "title"]:
            self.in_style_or_script = False
            return
            
        if tag == "a" and not self.in_style_or_script:
            link_text = "".join(self.link_text_buffer).strip()
            if self.current_link_url and self.current_link_url.startswith("http"):
                if link_text and not link_text.isdigit():
                    self.result.append(f" [{link_text}]({self.current_link_url}) ")
                else:
                    self.result.append(f" [Lien]({self.current_link_url}) ")
            self.current_link_url = None
            self.link_text_buffer = []
        elif tag in ["p", "div", "tr", "h1", "h2", "h3"]:
            self.result.append("\n")

    def handle_data(self, data):
        if self.in_style_or_script:
            return
        # FIX : Traduire les entités HTML en texte clair (' instead of &#39;)
        decoded_data = unescape(data)
        cleaned_data = re.sub(r'[\u200b-\u200d\u00a0\uFEFF\u034f]+', '', decoded_data)
        
        if self.current_link_url:
            self.link_text_buffer.append(cleaned_data)
        else:
            text = cleaned_data.strip()
            if text:
                text = re.sub(r'\s+', ' ', text)
                self.result.append(text)

    def get_markdown(self) -> str:
        return re.sub(r'\n{3,}', '\n\n', "".join(self.result)).strip()

def get_message_details(service, msg_id, user_id="me", show_images=False) -> Tuple[str, List[Dict]]:
    m = service.users().messages().get(userId=user_id, id=msg_id, format="full").execute()
    payload = m.get("payload", {})
    
    html_parts = []
    plain_parts = []
    attachments = []

    def walk_mime_parts(part):
        mime_type = part.get("mimeType")
        filename = part.get("filename", "")
        body = part.get("body", {})
        attachment_id = body.get("attachmentId")
        
        # S'il y a un nom de fichier et un attachmentId, c'est une pièce jointe
        if filename and attachment_id:
            attachments.append({
                "filename": filename,
                "mimeType": mime_type,
                "attachmentId": attachment_id,
                "size": body.get("size", 0)
            })
        
        body_data = body.get("data", "")
        if mime_type == "text/plain" and body_data and not filename:
            text = base64.urlsafe_b64decode(body_data.encode("utf-8")).decode("utf-8", errors="replace")
            plain_parts.append(unescape(text))
        elif mime_type == "text/html" and body_data and not filename:
            html = base64.urlsafe_b64decode(body_data.encode("utf-8")).decode("utf-8", errors="replace")
            html_parts.append(html)
            
        if "parts" in part:
            for sub_part in part["parts"]:
                walk_mime_parts(sub_part)

    walk_mime_parts(payload)

    body_text = ""
    if html_parts:
        parser = EmailMarkdownParser(allow_images=show_images)
        parser.feed("\n".join(html_parts))
        body_text = parser.get_markdown()
        
    if not body_text:
        body_text = "\n\n".join(plain_parts) if plain_parts else m.get("snippet", "")

    return body_text, attachments

def get_message_plain(service, msg_id, user_id="me", show_images=False) -> str:
    body, _ = get_message_details(service, msg_id, user_id, show_images)
    return body

def download_attachment(service, msg_id, attachment_id, user_id="me") -> bytes:
    try:
        attachment = service.users().messages().attachments().get(
            userId=user_id, messageId=msg_id, id=attachment_id
        ).execute()
        data = attachment.get("data")
        if data:
            return base64.urlsafe_b64decode(data.encode("utf-8"))
        return b""
    except Exception as e:
        print(f"Erreur téléchargement pièce jointe {attachment_id}: {e}")
        return b""

def modify_message_labels(service, msg_id, add_labels=None, remove_labels=None, user_id="me") -> bool:
    body = {}
    if add_labels:
        body["addLabelIds"] = add_labels
    if remove_labels:
        body["removeLabelIds"] = remove_labels
    try:
        service.users().messages().modify(userId=user_id, id=msg_id, body=body).execute()
        return True
    except Exception as e:
        print(f"Erreur modification labels {msg_id}: {e}")
        return False

def trash_message(service, msg_id, user_id="me") -> bool:
    try:
        service.users().messages().trash(userId=user_id, id=msg_id).execute()
        return True
    except Exception as e:
        print(f"Erreur mise à la corbeille {msg_id}: {e}")
        return False

def archive_message(service, msg_id, user_id="me") -> bool:
    return modify_message_labels(service, msg_id, remove_labels=["INBOX"], user_id=user_id)

def mark_message_unread(service, msg_id, unread: bool, user_id="me") -> bool:
    add_labels = ["UNREAD"] if unread else []
    remove_labels = [] if unread else ["UNREAD"]
    return modify_message_labels(service, msg_id, add_labels=add_labels, remove_labels=remove_labels, user_id=user_id)

def send_email(service, to: str, subject: str, body: str, cc: Optional[str] = None, attachment_paths: List[str] = None, user_id="me") -> bool:
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.base import MIMEBase
    from email import encoders
    import os
    import mimetypes

    try:
        message = MIMEMultipart()
        message['to'] = to
        message['subject'] = subject
        if cc:
            message['cc'] = cc
        
        message.attach(MIMEText(body, 'plain'))
        
        if attachment_paths:
            for path in attachment_paths:
                if not os.path.exists(path):
                    continue
                filename = os.path.basename(path)
                mime_type, _ = mimetypes.guess_type(path)
                if mime_type is None:
                    mime_type = 'application/octet-stream'
                main_type, sub_type = mime_type.split('/', 1)
                
                with open(path, 'rb') as fp:
                    part = MIMEBase(main_type, sub_type)
                    part.set_payload(fp.read())
                
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', 'attachment', filename=filename)
                message.attach(part)
                
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        service.users().messages().send(userId=user_id, body={'raw': raw}).execute()
        return True
    except Exception as e:
        print(f"Erreur d'envoi : {e}")
        return False

def send_plain_email(service, to: str, subject: str, body: str, cc: Optional[str] = None, user_id="me") -> bool:
    return send_email(service, to, subject, body, cc, user_id=user_id)