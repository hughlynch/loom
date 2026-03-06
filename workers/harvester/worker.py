"""HarvesterWorker — retrieves raw content from sources.

Responsible for fetching content from web pages, structured APIs, and uploaded
documents. Each skill computes a SHA-256 content hash for deduplication and
provenance tracking. Respects robots.txt directives for web harvesting.
"""

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse

from grove.uwp import Worker, skill

# Anti-patterns from the spec
ANTI_PATTERN_BLIND_SCRAPING = "blind_scraping"  # Harvesting without robots.txt check
ANTI_PATTERN_NO_HASH = "no_content_hash"  # Storing content without integrity hash
ANTI_PATTERN_STALE_FETCH = "stale_fetch"  # Re-fetching without checking staleness


def _compute_hash(content: str) -> str:
    """Compute SHA-256 hash of content for deduplication."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _check_robots_txt(url: str) -> dict:
    """Check robots.txt for the given URL's domain.

    Stub implementation. In production, this would fetch and parse
    the robots.txt file, checking whether our user-agent is permitted
    to access the given path.

    Returns:
        dict with {allowed: bool, reason: str}
    """
    parsed = urlparse(url)
    # Stub: always allow, but flag that check was performed
    return {
        "allowed": True,
        "reason": "robots.txt check stub — not yet implemented",
        "domain": parsed.netloc,
        "path": parsed.path,
    }


def _html_to_text(html: str) -> str:
    """Extract readable text from HTML, stripping tags and scripts."""
    import re
    # Remove script and style blocks
    text = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    # Replace block-level tags with newlines
    text = re.sub(r'<(?:p|div|br|h[1-6]|li|tr)[^>]*>', '\n', text, flags=re.IGNORECASE)
    # Strip remaining tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Decode common entities
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&quot;', '"').replace('&#39;', "'").replace('&nbsp;', ' ')
    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n\s*\n+', '\n\n', text)
    return text.strip()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class HarvesterWorker(Worker):
    worker_type = "harvester"

    @skill("harvest.web", "Fetch a URL and extract text content")
    def harvest_web(self, handle):
        """Fetch a web page, extract text content, compute content hash.

        Params (from handle.params):
            url (str): The URL to fetch.
            user_agent (str, optional): User-agent string to use.

        Returns:
            dict with url, content, content_hash, retrieved_at, metadata,
            and robots_check result.
        """
        params = handle.params
        url = params.get("url", "")

        if not url:
            return {"error": "url is required"}

        # Check robots.txt before fetching
        robots_check = _check_robots_txt(url)
        if not robots_check["allowed"]:
            return {
                "error": "blocked by robots.txt",
                "robots_check": robots_check,
            }

        # Fetch the page
        import urllib.request
        import urllib.error
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": params.get(
                    "user_agent",
                    "Loom/0.1 (knowledge-acquisition; +https://github.com/hughlynch/loom)"
                )},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                charset = resp.headers.get_content_charset() or "utf-8"
                html = raw.decode(charset, errors="replace")
                status_code = resp.status
                content_type = resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            return {"error": f"HTTP {e.code}", "url": url}
        except urllib.error.URLError as e:
            return {"error": str(e.reason), "url": url}
        except Exception as e:
            return {"error": str(e), "url": url}

        # Strip HTML to plain text
        content = _html_to_text(html)
        content_hash = _compute_hash(content)

        return {
            "url": url,
            "content": content,
            "content_hash": content_hash,
            "retrieved_at": _now_iso(),
            "robots_check": robots_check,
            "metadata": {
                "status_code": status_code,
                "content_type": content_type,
                "content_length": len(content),
            },
        }

    @skill("harvest.api", "Fetch from a structured API endpoint")
    def harvest_api(self, handle):
        """Fetch JSON data from a structured API endpoint.

        Params (from handle.params):
            url (str): The API endpoint URL.
            method (str, optional): HTTP method (default GET).
            headers (dict, optional): Additional request headers.
            body (dict, optional): Request body for POST/PUT.

        Returns:
            dict with url, data, content_hash, retrieved_at.
        """
        params = handle.params
        url = params.get("url", "")
        method = params.get("method", "GET")

        if not url:
            return {"error": "url is required"}

        # Stub: in production, use urllib.request to fetch the API response.
        data = {"stub": True, "source": url, "method": method}
        raw = json.dumps(data, sort_keys=True)
        content_hash = _compute_hash(raw)

        return {
            "url": url,
            "data": data,
            "content_hash": content_hash,
            "retrieved_at": _now_iso(),
        }

    @skill("harvest.document", "Process an uploaded document")
    def harvest_document(self, handle):
        """Process an uploaded document (PDF, DOCX, etc.) and extract text.

        Params (from handle.params):
            path (str): Path to the document file.
            doc_type (str, optional): Document type hint (pdf, docx, txt).

        Returns:
            dict with content, content_hash, doc_type, metadata.
        """
        params = handle.params
        path = params.get("path", "")

        if not path:
            return {"error": "path is required"}

        # Infer doc_type from extension if not provided
        doc_type = params.get("doc_type", "")
        if not doc_type and "." in path:
            doc_type = path.rsplit(".", 1)[-1].lower()

        # Stub: in production, use appropriate parser per doc_type
        # (e.g., pdfplumber for PDF, python-docx for DOCX).
        content = f"[stub] Extracted text from document: {path}"
        content_hash = _compute_hash(content)

        return {
            "content": content,
            "content_hash": content_hash,
            "doc_type": doc_type or "unknown",
            "metadata": {
                "path": path,
                "page_count": 1,
                "word_count": len(content.split()),
            },
        }


worker = HarvesterWorker(worker_id="loom-harvester-1")

if __name__ == "__main__":
    worker.run()
