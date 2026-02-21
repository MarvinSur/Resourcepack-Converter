#!/usr/bin/env python3
"""
link_converter.py
=================
Converts share/preview links into direct download links.

Supported platforms:
  - Dropbox       : ?dl=0 → ?dl=1  (no domain swap needed)
  - Google Drive  : share URL → export=download
  - MediaFire     : page URL → actual download link (scraped)
  - OneDrive      : share URL → API direct link
  - GitHub        : releases/download already direct; raw links supported
  - MCPacks       : /p/<id> → /api/v2/files/<id>/download
"""

import re, logging, urllib.request, urllib.error, base64
logger = logging.getLogger(__name__)


def convert_to_direct(url: str) -> str:
    url = url.strip()
    for fn in [_dropbox, _gdrive, _mediafire, _onedrive, _github, _mcpacks]:
        result = fn(url)
        if result != url:
            logger.info(f"Converted URL: {url[:70]}")
            logger.info(f"          → : {result[:70]}")
            return result
    logger.info(f"URL used as-is: {url[:70]}")
    return url


# ---------------------------------------------------------------------------
# Dropbox
# ---------------------------------------------------------------------------

def _dropbox(url: str) -> str:
    if "dropbox.com" not in url:
        return url
    # Strip existing dl param then force dl=1
    url = re.sub(r'[?&]dl=\d', '', url).rstrip('?').rstrip('&')
    sep = '&' if '?' in url else '?'
    return url + sep + 'dl=1'


# ---------------------------------------------------------------------------
# Google Drive
# ---------------------------------------------------------------------------

def _gdrive(url: str) -> str:
    if "drive.google.com" not in url and "docs.google.com" not in url:
        return url

    fid = None
    # Format: /file/d/<id>/view
    m = re.search(r'/file/d/([a-zA-Z0-9_-]+)', url)
    if m:
        fid = m.group(1)
    else:
        # Format: ?id=<id>
        m = re.search(r'[?&]id=([a-zA-Z0-9_-]+)', url)
        if m:
            fid = m.group(1)

    if fid:
        # confirm=t bypasses the "large file" warning page
        return f"https://drive.google.com/uc?export=download&id={fid}&confirm=t"
    return url


# ---------------------------------------------------------------------------
# MediaFire
# ---------------------------------------------------------------------------

def _mediafire(url: str) -> str:
    if "mediafire.com" not in url:
        return url

    # If it's already a direct download link, return as-is
    if "download.mediafire.com" in url:
        return url

    try:
        req  = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", errors="ignore")

        # Try multiple patterns MediaFire uses
        patterns = [
            r'href="(https://download\d*\.mediafire\.com/[^"]+)"',
            r'"(https://download\d*\.mediafire\.com/[^"]+)"',
            r"(https://download\d*\.mediafire\.com/[^\s\"'<>]+)",
        ]
        for pat in patterns:
            m = re.search(pat, html)
            if m:
                return m.group(1)

        logger.warning("MediaFire: download link not found in page HTML")
    except urllib.error.URLError as e:
        logger.warning(f"MediaFire fetch failed: {e}")
    except Exception as e:
        logger.warning(f"MediaFire unexpected error: {e}")

    return url


# ---------------------------------------------------------------------------
# OneDrive
# ---------------------------------------------------------------------------

def _onedrive(url: str) -> str:
    if "1drv.ms" not in url and "onedrive.live.com" not in url and "sharepoint.com" not in url:
        return url
    # Encode share URL to base64 then hit the sharing API
    encoded = (
        base64.b64encode(url.encode())
        .decode()
        .rstrip("=")
        .replace("/", "_")
        .replace("+", "-")
    )
    return f"https://api.onedrive.com/v1.0/shares/u!{encoded}/root/content"


# ---------------------------------------------------------------------------
# GitHub
# ---------------------------------------------------------------------------

def _github(url: str) -> str:
    if "github.com" not in url and "raw.githubusercontent.com" not in url:
        return url
    # Already a direct link
    if "/releases/download/" in url or "raw.githubusercontent.com" in url:
        return url
    # raw content URL conversion
    # https://github.com/user/repo/blob/branch/file → raw.githubusercontent.com
    m = re.match(
        r'https://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)', url
    )
    if m:
        user, repo, branch, path = m.groups()
        return f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/{path}"
    return url


# ---------------------------------------------------------------------------
# MCPacks
# ---------------------------------------------------------------------------

def _mcpacks(url: str) -> str:
    if "mcpacks.net" not in url:
        return url
    if "/api/v2/files/" in url:
        return url
    m = re.search(r'/p/([a-zA-Z0-9]+)', url)
    if m:
        return f"https://mcpacks.net/api/v2/files/{m.group(1)}/download"
    return url
