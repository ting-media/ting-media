"""
Article scraper for auto.co.il and generic news sites.
Uses trafilatura for content extraction + BeautifulSoup for listing pages.
"""

import logging
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

try:
    import trafilatura
    _TRAFILATURA = True
except ImportError:
    _TRAFILATURA = False

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Selectors tried in order for listing pages (article links)
LISTING_SELECTORS = [
    "article a[href]",
    ".post a[href]",
    ".entry a[href]",
    "h2 > a[href]",
    "h3 > a[href]",
    ".article-title a[href]",
    ".post-title a[href]",
    ".item-title a[href]",
    ".td-module-title a[href]",  # TD themes
    ".entry-title a[href]",
]

# Selectors tried in order for article body
BODY_SELECTORS = [
    ".entry-content",
    ".post-content",
    ".article-body",
    ".article-content",
    ".td-post-content",
    "article .content",
    "article",
    "main .content",
    "main",
]

# Selectors for article title
TITLE_SELECTORS = [
    "h1.entry-title",
    "h1.post-title",
    "h1.article-title",
    ".td-post-title h1",
    "article h1",
    "h1",
]


def _fetch(url: str) -> str | None:
    """Fetch URL and return HTML text, or None on failure."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text
    except Exception as e:
        logger.error("Fetch failed for %s: %s", url, e)
        return None


def scrape_listing(listing_url: str) -> list[dict]:
    """
    Scrape the article listing page and return a list of
    {url, title} dicts for articles found on the page.
    """
    html = _fetch(listing_url)
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    base = f"{urlparse(listing_url).scheme}://{urlparse(listing_url).netloc}"
    same_domain = urlparse(listing_url).netloc

    seen: set[str] = set()
    articles: list[dict] = []

    for selector in LISTING_SELECTORS:
        links = soup.select(selector)
        if not links:
            continue

        for link in links:
            href = link.get("href", "").strip()
            if not href or href.startswith("#"):
                continue

            full_url = urljoin(base, href)

            # Stay on same domain
            if urlparse(full_url).netloc != same_domain:
                continue

            # Skip pagination / category pages
            if full_url.rstrip("/") == listing_url.rstrip("/"):
                continue

            if full_url in seen:
                continue

            title = link.get_text(strip=True)
            if len(title) < 8:
                # Try parent element for title text
                parent = link.parent
                if parent:
                    title = parent.get_text(strip=True)

            if len(title) < 8:
                continue

            seen.add(full_url)
            articles.append({"url": full_url, "title": title})

        if articles:
            logger.info("Found %d articles using selector: %s", len(articles), selector)
            break

    if not articles:
        logger.warning("No articles found on listing page %s", listing_url)

    return articles


def scrape_article(url: str) -> dict | None:
    """
    Scrape a single article page and return structured data:
    {url, title, date, body, image_urls}
    Returns None if extraction fails.
    """
    html = _fetch(url)
    if not html:
        return None

    soup = BeautifulSoup(html, "lxml")

    # ── Title ──────────────────────────────────────────────────────────────
    title = ""
    for sel in TITLE_SELECTORS:
        el = soup.select_one(sel)
        if el:
            title = el.get_text(strip=True)
            if title:
                break

    # Fallback: OG title
    if not title:
        og = soup.find("meta", property="og:title")
        if og:
            title = og.get("content", "").strip()

    if not title:
        title = url.rstrip("/").split("/")[-1].replace("-", " ").title()

    # ── Date ───────────────────────────────────────────────────────────────
    date_str = datetime.today().strftime("%Y-%m-%d")
    for sel in ["time[datetime]", ".entry-date", ".post-date", ".published", "time"]:
        el = soup.select_one(sel)
        if el:
            candidate = el.get("datetime", "") or el.get_text(strip=True)
            if candidate:
                # Normalize: keep only first 10 chars if looks like ISO date
                m = re.search(r"\d{4}-\d{2}-\d{2}", candidate)
                if m:
                    date_str = m.group(0)
                break

    # ── Images ─────────────────────────────────────────────────────────────
    image_urls: list[str] = []

    # OG image first (featured image)
    og_img = soup.find("meta", property="og:image")
    if og_img and og_img.get("content"):
        image_urls.append(og_img["content"].strip())

    # Article body images
    for sel in BODY_SELECTORS + ["article"]:
        container = soup.select_one(sel)
        if not container:
            continue
        for img in container.find_all("img"):
            src = (
                img.get("src")
                or img.get("data-src")
                or img.get("data-lazy-src")
                or img.get("data-original")
            )
            if src and src.startswith("http") and src not in image_urls:
                image_urls.append(src)
        if image_urls:
            break

    image_urls = image_urls[:6]  # cap at 6

    # ── Body text ──────────────────────────────────────────────────────────
    body = ""

    if _TRAFILATURA:
        body = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
        ) or ""

    if not body:
        for sel in BODY_SELECTORS:
            el = soup.select_one(sel)
            if el:
                # Remove scripts, styles, navs
                for tag in el.find_all(["script", "style", "nav", "aside", "footer"]):
                    tag.decompose()
                body = el.get_text(separator="\n", strip=True)
                if len(body) > 200:
                    break

    if not body or len(body) < 100:
        logger.warning("Could not extract usable body text from %s", url)
        return None

    # Clean up excessive whitespace
    body = re.sub(r"\n{3,}", "\n\n", body).strip()

    logger.info("Scraped article: %s (%d chars)", title, len(body))
    return {
        "url": url,
        "title": title,
        "date": date_str,
        "body": body,
        "image_urls": image_urls,
    }
