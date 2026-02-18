#!/usr/bin/env python3

import re, logging, urllib.request, base64
logger = logging.getLogger(__name__)


def convert_to_direct(url: str) -> str:
    url = url.strip()
    for fn in [_dropbox, _gdrive, _mediafire, _onedrive, _github, _mcpacks]:
        result = fn(url)
        if result != url:
            logger.info(f"Converted: {url[:50]} → {result[:50]}")
            return result
    return url


def _dropbox(url: str) -> str:
    if "dropbox.com" not in url:
        return url
    url = re.sub(r'[?&]dl=\d', '', url).rstrip('?')
    sep = '&' if '?' in url else '?'
    url = url.replace('www.dropbox.com', 'dl.dropboxusercontent.com')
    return url + sep + 'dl=1'


def _gdrive(url: str) -> str:
    if "drive.google.com" not in url and "docs.google.com" not in url:
        return url
    fid = None
    m = re.search(r'/file/d/([a-zA-Z0-9_-]+)', url)
    if m:
        fid = m.group(1)
    else:
        m = re.search(r'[?&]id=([a-zA-Z0-9_-]+)', url)
        if m:
            fid = m.group(1)
    if fid:
        return f"https://drive.google.com/uc?export=download&id={fid}&confirm=t"
    return url


def _mediafire(url: str) -> str:
    if "mediafire.com" not in url:
        return url
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(req, timeout=10).read().decode('utf-8', errors='ignore')
        m = re.search(r'href="(https://download\d*\.mediafire\.com/[^"]+)"', html)
        if m:
            return m.group(1)
    except Exception as e:
        logger.warning(f"MediaFire fetch failed: {e}")
    return url


def _onedrive(url: str) -> str:
    if "1drv.ms" not in url and "onedrive.live.com" not in url:
        return url
    encoded = base64.b64encode(url.encode()).decode().rstrip('=').replace('/', '_').replace('+', '-')
    return f"https://api.onedrive.com/v1.0/shares/u!{encoded}/root/content"


def _github(url: str) -> str:
    if "github.com" not in url:
        return url
    # Already direct if releases/download or raw
    if "/releases/download/" in url or "raw.githubusercontent.com" in url:
        return url
    return url


def _mcpacks(url: str) -> str:
    if "mcpacks.net" not in url:
        return url
    if "/api/v2/files/" in url:
        return url
    m = re.search(r'/p/([a-zA-Z0-9]+)', url)
    if m:
        return f"https://mcpacks.net/api/v2/files/{m.group(1)}/download"
    return url
