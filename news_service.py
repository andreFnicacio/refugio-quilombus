import re
import time
import html
import logging
import email.utils
import subprocess
from datetime import datetime
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
import httpx

logger = logging.getLogger("refugio.news")

# Cache em memória: TTL de 30 minutos (1800 segundos)
CACHE_TTL_SECONDS = 1800
_NEWS_CACHE: Dict[str, Any] = {
    "timestamp": 0,
    "data": None
}

# Feeds RSS oficiais e abertos
FEEDS = {
    "nerd": [
        {"url": "https://jovemnerd.com.br/feed/", "source": "Jovem Nerd"},
        {"url": "https://www.omelete.com.br/rss", "source": "Omelete"}
    ],
    "tech": [
        {"url": "https://tecnoblog.net/feed/", "source": "Tecnoblog"},
        {"url": "https://manualdousuario.net/feed/", "source": "Manual do Usuário"}
    ],
    "politics": [
        {"url": "https://g1.globo.com/rss/g1/politica/", "source": "G1 Política"},
        {"url": "https://feeds.bbci.co.uk/portuguese/rss.xml", "source": "BBC News Brasil"}
    ]
}

# Fallbacks visuais e de contingência (Neo-Brutalist & Retrô)
DEFAULT_IMAGES = {
    "nerd": "https://images.unsplash.com/photo-1578632767115-351597cf2477?q=80&w=800&auto=format&fit=crop",
    "tech": "https://images.unsplash.com/photo-1550745165-9bc0b252726f?q=80&w=800&auto=format&fit=crop",
    "politics": "https://images.unsplash.com/photo-1541872703-74c5e44368f9?q=80&w=800&auto=format&fit=crop"
}

# Static offline contingency items. published_at is stamped at use-time (not "Hoje" forever).
FALLBACK_NEWS = {
    "nerd": [
        {
            "title": "Grandes estreias e adaptações de ficção e fantasia ganham destaque em 2026",
            "link": "https://www.omelete.com.br",
            "image_url": "https://images.unsplash.com/photo-1578632767115-351597cf2477?q=80&w=800&auto=format&fit=crop",
            "source": "Omelete",
            "category": "nerd",
            "published_at": ""
        },
        {
            "title": "O impacto duradouro de Berserk e o legado incomparável de Kentaro Miura",
            "link": "https://www.omelete.com.br",
            "image_url": "https://images.unsplash.com/photo-1607604276583-eef5d076aa5f?q=80&w=800&auto=format&fit=crop",
            "source": "Omelete",
            "category": "nerd",
            "published_at": ""
        },
        {
            "title": "Guia de retrogaming e emulação: Clássicos dos 16 e 64 bits em alta fidelidade",
            "link": "https://www.omelete.com.br",
            "image_url": "https://images.unsplash.com/photo-1550745165-9bc0b252726f?q=80&w=800&auto=format&fit=crop",
            "source": "Omelete",
            "category": "nerd",
            "published_at": ""
        },
        {
            "title": "Cinema e animação tradicional resistem ao avanço de imagens geradas por IA",
            "link": "https://www.omelete.com.br",
            "image_url": "https://images.unsplash.com/photo-1536440136628-849c177e76a1?q=80&w=800&auto=format&fit=crop",
            "source": "Omelete",
            "category": "nerd",
            "published_at": ""
        },
        {
            "title": "RPG de Mesa e a busca pelo analógico em tempos de hiperconexão digital",
            "link": "https://www.omelete.com.br",
            "image_url": "https://images.unsplash.com/photo-1610890716171-6b1bb98ffd09?q=80&w=800&auto=format&fit=crop",
            "source": "Omelete",
            "category": "nerd",
            "published_at": ""
        }
    ],
    "tech": [
        {
            "title": "O movimento IndieWeb: Por que desenvolvedores estão resgatando a web pessoal",
            "link": "https://tecnoblog.net",
            "image_url": "https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?q=80&w=800&auto=format&fit=crop",
            "source": "Tecnoblog",
            "category": "Tecnologia & Dev",
            "published_at": ""
        },
        {
            "title": "SQLite como banco primário em produção: O guia da simplicidade arquitetural",
            "link": "https://manualdousuario.net",
            "image_url": "https://images.unsplash.com/photo-1558494949-ef010cbdcc31?q=80&w=800&auto=format&fit=crop",
            "source": "Manual do Usuário",
            "category": "Tecnologia & Dev",
            "published_at": ""
        },
        {
            "title": "Linux, terminais minimalistas e a arte de construir softwares sem bloatware",
            "link": "https://tecnoblog.net",
            "image_url": "https://images.unsplash.com/photo-1629654297299-c8506221ca97?q=80&w=800&auto=format&fit=crop",
            "source": "Tecnoblog",
            "category": "Tecnologia & Dev",
            "published_at": ""
        },
        {
            "title": "Privacidade digital e soberania de dados: As ferramentas essenciais para 2026",
            "link": "https://manualdousuario.net",
            "image_url": "https://images.unsplash.com/photo-1563986768609-322da13575f3?q=80&w=800&auto=format&fit=crop",
            "source": "Manual do Usuário",
            "category": "Tecnologia & Dev",
            "published_at": ""
        },
        {
            "title": "O retorno dos monitores monocromáticos e a busca por foco cognitivo no trabalho",
            "link": "https://tecnoblog.net",
            "image_url": "https://images.unsplash.com/photo-1518770660439-4636190af475?q=80&w=800&auto=format&fit=crop",
            "source": "Tecnoblog",
            "category": "Tecnologia & Dev",
            "published_at": ""
        }
    ],
    "politics": [
        {
            "title": "Regulamentação de plataformas digitais e soberania tecnológica no cenário global",
            "link": "https://g1.globo.com/politica",
            "image_url": "https://images.unsplash.com/photo-1541872703-74c5e44368f9?q=80&w=800&auto=format&fit=crop",
            "source": "G1 Política",
            "category": "Política & Sociedade",
            "published_at": ""
        },
        {
            "title": "Discussões fiscais e investimentos públicos em infraestrutura para a próxima década",
            "link": "https://g1.globo.com/politica",
            "image_url": "https://images.unsplash.com/photo-1529107386315-e1a2ed48a620?q=80&w=800&auto=format&fit=crop",
            "source": "G1 Política",
            "category": "Política & Sociedade",
            "published_at": ""
        },
        {
            "title": "Transição energética e desafios diplomáticos na agenda climática internacional",
            "link": "https://www.bbc.com/portuguese",
            "image_url": "https://images.unsplash.com/photo-1497435334941-8c899ee9e8e9?q=80&w=800&auto=format&fit=crop",
            "source": "BBC Brasil",
            "category": "Política & Sociedade",
            "published_at": ""
        },
        {
            "title": "O impacto da tecnologia na transparência pública e fiscalização cidadã",
            "link": "https://g1.globo.com/politica",
            "image_url": "https://images.unsplash.com/photo-1451187580459-43490279c0fa?q=80&w=800&auto=format&fit=crop",
            "source": "G1 Política",
            "category": "Política & Sociedade",
            "published_at": ""
        },
        {
            "title": "Políticas de incentivo à ciência nacional e retenção de talentos no Brasil",
            "link": "https://www.bbc.com/portuguese",
            "image_url": "https://images.unsplash.com/photo-1532094349884-543bc11b234d?q=80&w=800&auto=format&fit=crop",
            "source": "BBC Brasil",
            "category": "Política & Sociedade",
            "published_at": ""
        }
    ]
}


def _with_fallback_date(item: Dict[str, Any]) -> Dict[str, Any]:
    """Copy fallback item and stamp the real load date (avoids eternal 'Hoje')."""
    stamped = dict(item)
    stamped["published_at"] = datetime.now().strftime("%d/%m/%Y")
    return stamped


def _stamped_fallback_hub() -> Dict[str, List[Dict[str, Any]]]:
    """Return a full fallback hub with timestamps applied at call time."""
    return {
        category: [_with_fallback_date(item) for item in items]
        for category, items in FALLBACK_NEWS.items()
    }


def _extract_image_from_xml_item(item: ET.Element, default_img: str) -> str:
    """Extrai imagem de tags RSS comuns (enclosure, media:content, ou regex no description)."""
    # 1. Enclosure
    enclosure = item.find("enclosure")
    if enclosure is not None:
        url = enclosure.attrib.get("url")
        if url and any(url.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]):
            return url

    # 2. Namespaces media
    namespaces = {
        "media": "http://search.yahoo.com/mrss/",
        "content": "http://purl.org/rss/1.0/modules/content/"
    }
    media_content = item.find("media:content", namespaces)
    if media_content is not None and "url" in media_content.attrib:
        return media_content.attrib["url"]

    media_thumbnail = item.find("media:thumbnail", namespaces)
    if media_thumbnail is not None and "url" in media_thumbnail.attrib:
        return media_thumbnail.attrib["url"]

    # 3. Regex em description ou content
    desc_elem = item.find("description")
    if desc_elem is not None and desc_elem.text:
        match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', desc_elem.text)
        if match:
            return match.group(1)

    return default_img


def _clean_text(text: Optional[str]) -> str:
    if not text:
        return ""
    # Remove tags HTML e decodifica entidades
    clean = re.sub(r"<[^>]+>", "", text).strip()
    return html.unescape(clean)


def _format_pub_date(pub_date_str: Optional[str]) -> str:
    """Converte pubDate do RSS ou ISO 8601 em formato legível e dinâmico em pt-BR."""
    if not pub_date_str:
        return "Recente"
    try:
        dt = None
        # Tenta RFC 2822 (RSS pubDate)
        try:
            dt = email.utils.parsedate_to_datetime(pub_date_str)
        except Exception:
            pass

        # Tenta ISO 8601 (Omelete data-published: 2026-10-11 02:53:59+00:00 ou Z)
        if dt is None:
            clean_str = pub_date_str.strip().replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean_str)

        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        day_delta = (now.date() - dt.date()).days
        if day_delta <= 0:
            return f"Hoje às {dt.strftime('%H:%M')}"
        elif day_delta == 1:
            return f"Ontem às {dt.strftime('%H:%M')}"
        elif day_delta < 7:
            return f"Há {day_delta} dias"
        else:
            return dt.strftime("%d/%m/%Y às %H:%M")
    except Exception:
        return pub_date_str[:16].strip() if pub_date_str else "Recente"


def fetch_omelete_news() -> List[Dict[str, Any]]:
    """
    Coleta e parseia as 5 principais notícias mais recentes diretamente do Omelete (https://www.omelete.com.br/).
    Possui resiliência de transporte (httpx com fallback para curl do sistema contra quirks de TLS do Akamai)
    e fallback estrito para garantir que a coluna nunca quebre.
    """
    category_items: List[Dict[str, Any]] = []
    default_img = DEFAULT_IMAGES.get("nerd", "https://images.unsplash.com/photo-1578632767115-351597cf2477?q=80&w=800&auto=format&fit=crop")
    url = "https://www.omelete.com.br/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    raw_html = ""
    # 1. Tentativa primária via httpx com timeout curto
    try:
        with httpx.Client(timeout=4.0, headers=headers, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code == 200 and resp.text:
                raw_html = resp.text
    except Exception as e:
        logger.debug(f"[OMELETE] Conexão httpx falhou ({e}), acionando fallback de rede...")

    # 2. Fallback de transporte para curl caso haja handshake TLS time-out no ambiente local/container
    if not raw_html:
        try:
            cmd = [
                "curl", "-s", "-L", "--max-time", "4",
                "-A", headers["User-Agent"],
                url
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if res.returncode == 0 and res.stdout:
                raw_html = res.stdout
        except Exception as e:
            logger.warning(f"[OMELETE] Falha na requisição curl ao Omelete: {e}")

    # 3. Parsing das notícias se o HTML foi obtido com sucesso
    if raw_html:
        try:
            article_chunks = re.findall(r'<article\b[^>]*>(.*?)</article>', raw_html, flags=re.DOTALL | re.IGNORECASE)
            for chunk in article_chunks:
                if len(category_items) >= 5:
                    break

                # Título da matéria (<h2 ...> ou <h3 ...>)
                h_match = re.search(r'<h[1-3]\b[^>]*>(.*?)</h[1-3]>', chunk, flags=re.DOTALL | re.IGNORECASE)
                if not h_match:
                    continue
                title = _clean_text(h_match.group(1))
                if not title or len(title) < 5:
                    continue

                # Link de destino
                link_match = re.search(r'<a\b[^>]*\bhref=[\"\']([^\"\']+)[\"\']', chunk, flags=re.IGNORECASE)
                if not link_match:
                    continue
                link = link_match.group(1).strip()
                if not link:
                    continue
                if link.startswith("/"):
                    link = f"https://www.omelete.com.br{link}"
                elif not link.startswith("http://") and not link.startswith("https://"):
                    link = f"https://www.omelete.com.br/{link}"

                # Evita itens duplicados
                if any(existing["link"] == link for existing in category_items):
                    continue

                # Imagem de capa (src ou data-lazy-src)
                img_match = re.search(r'<img\b[^>]*\b(?:src|data-lazy-src|data-src)=[\"\']([^\"\']+)[\"\']', chunk, flags=re.IGNORECASE)
                img_url = default_img
                if img_match:
                    extracted_img = img_match.group(1).strip()
                    if extracted_img.startswith("//"):
                        img_url = f"https:{extracted_img}"
                    elif extracted_img.startswith("/"):
                        img_url = f"https://www.omelete.com.br{extracted_img}"
                    elif extracted_img.startswith("http://") or extracted_img.startswith("https://"):
                        img_url = extracted_img

                # Data de publicação (atributo data-published)
                date_match = re.search(r'data-published=[\"\']([^\"\']+)[\"\']', chunk, flags=re.IGNORECASE)
                raw_date = date_match.group(1).strip() if date_match else None
                pub_date = _format_pub_date(raw_date)

                category_items.append({
                    "title": title,
                    "link": link,
                    "image_url": img_url,
                    "source": "Omelete",
                    "category": "nerd",
                    "published_at": pub_date
                })
        except Exception as e:
            logger.warning(f"[OMELETE] Erro ao parsear notícias do Omelete: {e}")

    # 4. Fallback de contingência caso scraping falhe ou traga menos de 5 matérias
    if len(category_items) < 5:
        fallbacks = FALLBACK_NEWS.get("nerd", [])
        for fb in fallbacks:
            if len(category_items) >= 5:
                break
            if not any(it["title"] == fb["title"] for it in category_items):
                category_items.append(_with_fallback_date(fb))

    return category_items[:5]


def fetch_category_feed(category: str) -> List[Dict[str, Any]]:
    """Busca e parseia itens de uma categoria com timeout estrito e fallback."""
    if category == "nerd":
        return fetch_omelete_news()

    feed_list = FEEDS.get(category, [])
    category_items = []
    default_img = DEFAULT_IMAGES.get(category, DEFAULT_IMAGES["tech"])

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) O-Refugio-NewsHub/1.0"
    }

    for feed_info in feed_list:
        if len(category_items) >= 5:
            break
        try:
            with httpx.Client(timeout=4.0, headers=headers, follow_redirects=True) as client:
                resp = client.get(feed_info["url"])
                if resp.status_code == 200:
                    root = ET.fromstring(resp.content)
                    items = root.findall(".//item")
                    for it in items:
                        if len(category_items) >= 5:
                            break
                        title_el = it.find("title")
                        link_el = it.find("link")
                        pub_date_el = it.find("pubDate")

                        title = _clean_text(title_el.text if title_el is not None else "")
                        link = link_el.text.strip() if link_el is not None and link_el.text else ""
                        raw_pub_date = pub_date_el.text if pub_date_el is not None and pub_date_el.text else None
                        pub_date = _format_pub_date(raw_pub_date)

                        if not title or not link:
                            continue

                        # Evita duplicados
                        if any(existing["link"] == link for existing in category_items):
                            continue

                        img_url = _extract_image_from_xml_item(it, default_img)

                        category_items.append({
                            "title": title,
                            "link": link,
                            "image_url": img_url,
                            "source": feed_info["source"],
                            "category": category,
                            "published_at": pub_date
                        })
        except Exception as e:
            logger.warning(f"[NEWS] Falha ao coletar feed {feed_info['url']}: {e}")
            continue

    # Se a coleta externa não trouxe os 5 necessários (ex: sem internet ou feed fora do ar), completa com o fallback
    if len(category_items) < 5:
        fallbacks = FALLBACK_NEWS.get(category, [])
        for fb in fallbacks:
            if len(category_items) >= 5:
                break
            if not any(it["title"] == fb["title"] for it in category_items):
                category_items.append(_with_fallback_date(fb))

    return category_items[:5]


def get_news_hub_data() -> Dict[str, List[Dict[str, Any]]]:
    """
    Retorna as top 5 notícias para Nerd, Tecnologia e Política.
    Utiliza cache em memória com TTL de 30 minutos para garantir atualização contínua e diária.
    """
    global _NEWS_CACHE
    now = time.time()

    if _NEWS_CACHE["data"] and (now - _NEWS_CACHE["timestamp"] < CACHE_TTL_SECONDS):
        return _NEWS_CACHE["data"]

    try:
        nerd_news = fetch_category_feed("nerd")
        tech_news = fetch_category_feed("tech")
        politics_news = fetch_category_feed("politics")

        data = {
            "nerd": nerd_news,
            "tech": tech_news,
            "politics": politics_news
        }
        _NEWS_CACHE["timestamp"] = now
        _NEWS_CACHE["data"] = data
        return data
    except Exception as e:
        logger.error(f"[NEWS ERROR] Erro geral ao atualizar hub de notícias: {e}")
        if _NEWS_CACHE["data"]:
            return _NEWS_CACHE["data"]
        return _stamped_fallback_hub()


def get_news_last_updated() -> str:
    """Retorna data/hora formatada da última sincronização do radar."""
    global _NEWS_CACHE
    if _NEWS_CACHE["timestamp"]:
        dt = datetime.fromtimestamp(_NEWS_CACHE["timestamp"])
        return dt.strftime("%d/%m/%Y às %H:%M")
    return "Sincronizado Recentemente"


def refresh_news_hub_data() -> Dict[str, List[Dict[str, Any]]]:
    """Força invalidação do cache e recarrega notícias imediatamente."""
    global _NEWS_CACHE
    _NEWS_CACHE["timestamp"] = 0
    _NEWS_CACHE["data"] = None
    return get_news_hub_data()
