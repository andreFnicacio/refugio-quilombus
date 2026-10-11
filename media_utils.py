import re
import html
from typing import Optional
from urllib.parse import urlparse

# Expressões regulares robustas para todas as variações de URLs do YouTube
YOUTUBE_PATTERNS = [
    re.compile(r'(?:https?:\/\/)?(?:www\.|m\.)?youtube\.com\/watch\?(?:[^&\s]*&)*v=([a-zA-Z0-9_-]{11})(?:[^\s]*)?', re.IGNORECASE),
    re.compile(r'(?:https?:\/\/)?(?:www\.|m\.)?youtube\.com\/shorts\/([a-zA-Z0-9_-]{11})(?:[^\s]*)?', re.IGNORECASE),
    re.compile(r'(?:https?:\/\/)?(?:www\.|m\.)?youtube\.com\/embed\/([a-zA-Z0-9_-]{11})(?:[^\s]*)?', re.IGNORECASE),
    re.compile(r'(?:https?:\/\/)?youtu\.be\/([a-zA-Z0-9_-]{11})(?:[^\s]*)?', re.IGNORECASE),
]


def extract_youtube_id(url: Optional[str]) -> Optional[str]:
    """
    Identifica e extrai o ID de 11 caracteres de URLs do YouTube.
    Suporta:
      - youtube.com/watch?v=ID
      - youtu.be/ID
      - youtube.com/shorts/ID
      - youtube.com/embed/ID
      - URLs móveis (m.youtube.com) e com parâmetros adicionais (?t=, &feature=)
    """
    if not url:
        return None

    clean_url = url.strip()
    for pattern in YOUTUBE_PATTERNS:
        match = pattern.search(clean_url)
        if match:
            return match.group(1)
    return None


def render_youtube_card(video_id: str, original_url: str = "") -> str:
    """
    Renderiza um card de mídia Neo-Brutalist formatado com a thumbnail oficial
    em alta resolução (hqdefault.jpg), overlay de play e suporte a iframe responsivo leve.
    """
    safe_id = html.escape(video_id)
    watch_url = f"https://www.youtube.com/watch?v={safe_id}"
    thumb_url = f"https://img.youtube.com/vi/{safe_id}/hqdefault.jpg"

    return f"""<div class="video-embed-card" data-video-id="{safe_id}">
  <div class="video-header-bar">
    <span class="video-header-tag">[YOUTUBE // TRANSMISSÃO AUDIOVISUAL]</span>
    <span class="video-header-id">ID: {safe_id}</span>
  </div>
  <div class="video-thumbnail-container" data-video-id="{safe_id}">
    <img src="{thumb_url}" alt="Thumbnail do Vídeo YouTube {safe_id}" class="video-thumbnail-img" loading="lazy">
    <div class="video-play-overlay">
      <span class="video-play-icon">▶</span>
      <span class="video-play-label">[CLIQUE PARA REPRODUZIR]</span>
    </div>
  </div>
  <div class="video-footer-bar">
    <a href="{watch_url}" target="_blank" rel="noopener noreferrer" class="btn btn-sm">
      ASSISTIR NO YOUTUBE &gt;&gt;
    </a>
  </div>
</div>"""


def render_link_preview(url: str, text: Optional[str] = None) -> str:
    """
    Renderiza um componente visual limpo de preview/hiperlink para links convencionais (não-vídeo).
    """
    safe_url = html.escape(url.strip())
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or "link externo"
    except Exception:
        domain = "link externo"

    safe_domain = html.escape(domain)
    display_text = html.escape(text.strip()) if text else safe_url

    return f"""<div class="link-preview-box">
  <div class="link-preview-info">
    <span class="link-preview-badge">[{safe_domain.upper()}]</span>
    <a href="{safe_url}" target="_blank" rel="noopener noreferrer" class="link-preview-url">{display_text}</a>
  </div>
  <a href="{safe_url}" target="_blank" rel="noopener noreferrer" class="btn btn-sm btn-cyan">
    VISITAR &gt;&gt;
  </a>
</div>"""


def process_media_links(text: str) -> str:
    """
    Analisa o conteúdo textual/markdown e transforma:
      1. Links ou linhas contendo URLs do YouTube em cards com thumbnail e player.
      2. Linhas contendo URLs convencionais isoladas em cards limpos de link preview.
    """
    if not text:
        return ""

    lines = text.split("\n")
    processed_lines = []

    for line in lines:
        stripped = line.strip()

        # 1. Verifica se a linha é um link markdown apontando para o YouTube: [Texto](https://youtube...)
        md_yt = re.match(r'^\[(.*?)\]\((https?:\/\/[^\s\)]+)\)$', stripped)
        if md_yt:
            target_url = md_yt.group(2)
            yt_id = extract_youtube_id(target_url)
            if yt_id:
                processed_lines.append(render_youtube_card(yt_id, target_url))
                continue

        # 2. Verifica se a linha é uma URL isolada do YouTube
        if stripped.startswith("http://") or stripped.startswith("https://"):
            yt_id = extract_youtube_id(stripped)
            if yt_id:
                processed_lines.append(render_youtube_card(yt_id, stripped))
                continue

            # 3. Se for uma URL isolada convencional (não-vídeo)
            is_single_url = re.match(r'^https?:\/\/[^\s]+$', stripped)
            if is_single_url:
                processed_lines.append(render_link_preview(stripped))
                continue

        processed_lines.append(line)

    return "\n".join(processed_lines)
