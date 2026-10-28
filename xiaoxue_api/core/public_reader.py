"""Read public article pages without depending on an assistant's tool runtime."""
from __future__ import annotations

from html import unescape
from html.parser import HTMLParser
import ipaddress
import re
import socket
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx


class _TextParser(HTMLParser):
    BLOCK = {"article", "main", "p", "li", "h1", "h2", "h3", "h4", "blockquote", "pre"}
    DROP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.drop_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.DROP:
            self.drop_depth += 1
        elif not self.drop_depth and tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.DROP and self.drop_depth:
            self.drop_depth -= 1
        elif not self.drop_depth and tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.drop_depth:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _TextParser()
    parser.feed(html)
    text = unescape("".join(parser.parts)).replace("\r", "")
    lines = [re.sub(r"[ \t\f\v]+", " ", line).strip() for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(line for line in lines if line)).strip()


def _public_url(url: str) -> bool:
    try:
        parsed = urlparse(str(url))
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            return False
        host = parsed.hostname.rstrip(".").casefold()
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            return False
        for item in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM):
            if not ipaddress.ip_address(item[4][0]).is_global:
                return False
        return True
    except (OSError, ValueError, TypeError):
        return False


def extract_public_page(urls: list[str], *, char_limit: int = 50000, timeout: float = 50) -> dict[str, Any]:
    """Return a stable extraction envelope; input must contain public HTTP URLs."""
    results: list[dict[str, Any]] = []
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/126 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5",
    }
    with httpx.Client(follow_redirects=False, timeout=timeout, headers=headers) as client:
        for raw_url in urls:
            if not _public_url(str(raw_url)):
                results.append({"url": str(raw_url), "error": "unsupported_url"})
                continue
            try:
                current = str(raw_url)
                for _ in range(5):
                    response = client.get(current)
                    if not response.is_redirect:
                        break
                    current = urljoin(current, str(response.headers.get("location") or ""))
                    if not _public_url(current):
                        raise ValueError("unsafe redirect")
                else:
                    raise ValueError("too many redirects")
                content_type = response.headers.get("content-type", "").lower()
                raw = response.text
                text = raw if content_type.startswith("text/plain") else html_to_text(raw)
                if response.status_code != 200:
                    results.append({"url": str(response.url), "error": f"http_{response.status_code}"})
                    continue
                if re.search(r"环境异常|完成验证|访问过于频繁|access denied|request blocked|403 forbidden", text[:1000], re.I):
                    results.append({"url": str(response.url), "error": "access_denied", "blocked_by_policy": True})
                    continue
                title_match = re.search(r"<title[^>]*>(.*?)</title>", raw, re.I | re.S)
                title = html_to_text(title_match.group(1)) if title_match else ""
                truncated = len(text) > char_limit
                results.append({
                    "url": str(response.url),
                    "title": title[:300],
                    "content": text[:char_limit],
                    "truncated": truncated,
                })
            except Exception as exc:
                results.append({"url": str(raw_url), "error": type(exc).__name__})
    return {"results": results}
