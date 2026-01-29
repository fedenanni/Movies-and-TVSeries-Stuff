"""Vercel serverless function for fetching TV series ratings."""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

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
    except Exception as e:
        return {"success": False, "error": str(e)}


from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

# Cache duration: 30 days in seconds
CACHE_MAX_AGE_SECONDS = 30 * 24 * 60 * 60


class handler(BaseHTTPRequestHandler):
    """Vercel serverless function handler."""

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        title = params.get("title", [""])[0]

        if not title:
            response = {"success": False, "error": "Missing 'title' parameter"}
            cache_header = "no-store"
        else:
            response = get_scores(title)
            # Cache successful responses at CDN level for 30 days
            if response.get("success"):
                cache_header = f"s-maxage={CACHE_MAX_AGE_SECONDS}, stale-while-revalidate"
            else:
                cache_header = "no-store"

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", cache_header)
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
