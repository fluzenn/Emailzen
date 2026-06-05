def render_text(text: str, max_len: int = 20000) -> str:
    if text is None:
        return ""
    t = text.replace("\r\n", "\n")
    if len(t) > max_len:
        return t[:max_len] + "\n\n...[Contenu Tronqué pour des raisons de performance]"
    return t