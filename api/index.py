"""Vercel serverless function for fetching TV series ratings."""

import json
import os
import re
import time
from collections import defaultdict

import requests
from bs4 import BeautifulSoup

# CORS: Set to specific domain or "*" for open access
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "https://fedenanni.github.io")

# Rate limiting (in-memory - resets on cold starts, limited effectiveness in serverless)
RATE_LIMIT_REQUESTS = 10  # max requests per window
RATE_LIMIT_WINDOW_SECONDS = 60  # time window
_request_counts: dict[str, list[float]] = defaultdict(list)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def search_series(title: str) -> tuple[str, str]:
    """Search IMDb for a TV series and return (imdb_id, display_title)."""
    r = requests.get(
        "https://www.imdb.com/find/",
        params={"q": title, "s": "tt", "ttype": "tv"},
        headers=HEADERS,
        timeout=10,
    )
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for a in soup.find_all("a", href=re.compile(r"/title/(tt\d+)")):
        text = a.get_text(strip=True)
        if text:
            imdb_id = re.search(r"(tt\d+)", a["href"]).group(1)
            return imdb_id, text
    raise ValueError(f"No TV series found for '{title}'")


def get_season_numbers(imdb_id: str) -> list[int]:
    """Return list of season numbers for a series."""
    r = requests.get(
        f"https://www.imdb.com/title/{imdb_id}/episodes/",
        headers=HEADERS,
        timeout=10,
    )
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    seasons = set()
    for a in soup.find_all("a", href=re.compile(r"season=(\d+)")):
        m = re.search(r"season=(\d+)", a["href"])
        if m:
            text = a.get_text(strip=True)
            if text.isdigit():
                seasons.add(int(m.group(1)))
    return sorted(seasons)


def get_episode_ratings(imdb_id: str, season: int) -> list[float]:
    """Return list of episode ratings for a given season."""
    r = requests.get(
        f"https://www.imdb.com/title/{imdb_id}/episodes/",
        params={"season": season},
        headers=HEADERS,
        timeout=10,
    )
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    ratings = []
    for article in soup.find_all("article", class_="episode-item-wrapper"):
        # Skip specials (E0)
        h4 = article.find("h4")
        if h4 and re.search(r"\.E0\b", h4.get_text()):
            continue
        span = article.find("span", class_="ipc-rating-star--rating")
        if span:
            try:
                val = float(span.get_text(strip=True))
                if 0.0 < val <= 10.0:
                    ratings.append(val)
            except ValueError:
                continue
    return ratings


def get_scores(title: str) -> dict:
    """Fetch all season episode ratings and return as JSON-serializable dict."""
    try:
        imdb_id, display_title = search_series(title)
        seasons = get_season_numbers(imdb_id)

        all_scores = []
        for s in seasons:
            ratings = get_episode_ratings(imdb_id, s)
            if len(ratings) > 1:
                all_scores.append(ratings)
            time.sleep(0.3)

        return {
            "success": True,
            "title": display_title,
            "imdb_id": imdb_id,
            "seasons": all_scores,
        }
    except ValueError as e:
        # User-facing errors (e.g., "No TV series found")
        return {"success": False, "error": str(e)}
    except Exception:
        # Hide internal errors from clients
        return {"success": False, "error": "An error occurred while fetching data"}


from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

# Cache duration: 30 days in seconds
CACHE_MAX_AGE_SECONDS = 30 * 24 * 60 * 60


def _is_rate_limited(client_ip: str) -> bool:
    """Check if client has exceeded rate limit. Returns True if limited."""
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS

    # Clean old entries and get recent requests
    _request_counts[client_ip] = [t for t in _request_counts[client_ip] if t > window_start]

    if len(_request_counts[client_ip]) >= RATE_LIMIT_REQUESTS:
        return True

    _request_counts[client_ip].append(now)
    return False


class handler(BaseHTTPRequestHandler):
    """Vercel serverless function handler."""

    def _get_client_ip(self) -> str:
        """Get client IP from headers (Vercel forwards real IP)."""
        return (
            self.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or self.headers.get("x-real-ip", "")
            or self.client_address[0]
        )

    def do_GET(self):
        client_ip = self._get_client_ip()

        # Check rate limit
        if _is_rate_limited(client_ip):
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
            self.send_header("Retry-After", str(RATE_LIMIT_WINDOW_SECONDS))
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": False,
                "error": "Rate limit exceeded. Please try again later."
            }).encode())
            return

        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        title = params.get("title", [""])[0]

        if not title:
            response = {"success": False, "error": "Missing 'title' parameter"}
            cache_header = "no-store"
        else:
            response = get_scores(title)
            # Cache successful responses at CDN level for 30 days
            # Use max-age=0 so browsers don't cache, but s-maxage for Vercel edge
            if response.get("success"):
                cache_header = f"max-age=0, s-maxage={CACHE_MAX_AGE_SECONDS}, stale-while-revalidate={CACHE_MAX_AGE_SECONDS}"
            else:
                cache_header = "no-store"

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        self.send_header("Cache-Control", cache_header)
        self.send_header("CDN-Cache-Control", cache_header)
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
