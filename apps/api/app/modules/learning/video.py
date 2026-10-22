"""External lesson video: only VK Video, Rutube and YouTube links, always rebuilt as a known embed URL.

The stored ``url`` is what the coordinator pasted; learners only ever get ``embed_url``
derived here, so no other address can reach an iframe.
"""
import re
from urllib.parse import parse_qs, urlsplit

PROVIDERS = {"vk": "VK Видео", "rutube": "Rutube", "youtube": "YouTube"}
_YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_RUTUBE_PATH = re.compile(r"^/(?:video|video/private|play/embed)/([0-9a-f]{32})/?$")
_VK_VIDEO = re.compile(r"video(-?\d{1,20})_(\d{1,20})")
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _first(query, name):
    values = query.get(name)
    return values[0] if values else None


def video_embed(url) -> tuple[str, str] | None:
    """Returns (provider, embed_url) for a supported public video link, otherwise None."""
    if not isinstance(url, str):
        return None
    url = url.strip()
    if not url or len(url) > 500 or any(char.isspace() for char in url):
        return None
    if "://" not in url:
        url = "https://" + url
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme not in {"http", "https"} or parts.username or parts.password or port is not None:
        return None
    host = (parts.hostname or "").lower()
    for prefix in ("www.", "m."):
        host = host.removeprefix(prefix)
    query = parse_qs(parts.query)
    path = parts.path
    if host in {"youtube.com", "youtube-nocookie.com"}:
        if path == "/watch":
            video = _first(query, "v")
        else:
            match = re.match(r"^/(?:embed|shorts|live)/([^/]+)/?$", path)
            video = match.group(1) if match else None
        if video and _YOUTUBE_ID.match(video):
            return "youtube", f"https://www.youtube-nocookie.com/embed/{video}"
        return None
    if host == "youtu.be":
        video = path.strip("/")
        return ("youtube", f"https://www.youtube-nocookie.com/embed/{video}") if _YOUTUBE_ID.match(video) else None
    if host == "rutube.ru":
        match = _RUTUBE_PATH.match(path)
        if not match:
            return None
        private = _first(query, "p")
        suffix = f"?p={private}" if private and _TOKEN.match(private) else ""
        return "rutube", f"https://rutube.ru/play/embed/{match.group(1)}/{suffix}"
    if host in {"vk.com", "vk.ru", "vkvideo.ru"}:
        if path == "/video_ext.php":
            owner, video = _first(query, "oid"), _first(query, "id")
            if not (owner and video and re.match(r"^-?\d{1,20}$", owner) and re.match(r"^\d{1,20}$", video)):
                return None
        else:
            # vk.com/video-1_2, vkvideo.ru/video-1_2 or a feed link with ?z=video-1_2/...
            match = _VK_VIDEO.fullmatch(path.strip("/")) or _VK_VIDEO.match(_first(query, "z") or "")
            if not match:
                return None
            owner, video = match.groups()
        secret = _first(query, "hash")
        suffix = f"&hash={secret}" if secret and _TOKEN.match(secret) else ""
        return "vk", f"https://vkvideo.ru/video_ext.php?oid={owner}&id={video}{suffix}"
    return None
