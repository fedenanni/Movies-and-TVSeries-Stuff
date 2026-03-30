"""Vercel serverless function for fetching TV series ratings."""

import json
import os
import time
from collections import defaultdict

import requests

# CORS: Set to specific domain or "*" for open access
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "https://fedenanni.github.io")

# Rate limiting (in-memory - resets on cold starts, limited effectiveness in serverless)
RATE_LIMIT_REQUESTS = 10  # max requests per window
RATE_LIMIT_WINDOW_SECONDS = 60  # time window
_request_counts: dict[str, list[float]] = defaultdict(list)

IMDB_GRAPHQL_URL = "https://graphql.imdb.com/"
IMDB_SUGGESTION_URL = "https://v2.sg.media-imdb.com/suggestion"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Content-Type": "application/json",
}


def search_series(title: str) -> tuple[str, str]:
    """Search IMDb for a TV series and return (imdb_id, display_title)."""
    # Use IMDb suggestion API: /suggestion/{first_letter}/{query}.json
    query = title.lower().replace(" ", "+")
    first_letter = query[0] if query else "a"
    r = requests.get(
        f"{IMDB_SUGGESTION_URL}/{first_letter}/{query}.json",
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    for item in data.get("d", []):
        # Filter for TV series only (qid: tvSeries or tvMiniSeries)
        if item.get("qid") in ("tvSeries", "tvMiniSeries"):
            return item["id"], item["l"]
    raise ValueError(f"No TV series found for '{title}'")


def get_season_numbers(imdb_id: str) -> list[int]:
    """Return list of season numbers for a series via IMDb GraphQL API."""
    query = """
    query {
        title(id: "%s") {
            episodes {
                seasons { number }
            }
        }
    }
    """ % imdb_id
    r = requests.post(
        IMDB_GRAPHQL_URL,
        headers=HEADERS,
        json={"query": query},
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    seasons = data.get("data", {}).get("title", {}).get("episodes", {}).get("seasons", [])
    return sorted(s["number"] for s in seasons if s.get("number") is not None)


def get_episode_ratings(imdb_id: str, season: int) -> list[float]:
    """Return list of episode ratings for a given season via IMDb GraphQL API."""
    query = """
    query {
        title(id: "%s") {
            episodes {
                episodes(first: 50, filter: {includeSeasons: ["%d"]}) {
                    edges {
                        node {
                            series {
                                displayableEpisodeNumber {
                                    episodeNumber { episodeNumber }
                                }
                            }
                            ratingsSummary { aggregateRating }
                        }
                    }
                }
            }
        }
    }
    """ % (imdb_id, season)
    r = requests.post(
        IMDB_GRAPHQL_URL,
        headers=HEADERS,
        json={"query": query},
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    edges = (data.get("data", {}).get("title", {}).get("episodes", {})
             .get("episodes", {}).get("edges", []))
    ratings = []
    for edge in edges:
        node = edge.get("node", {})
        # Skip specials (episode number "0")
        ep_num = (node.get("series", {}).get("displayableEpisodeNumber", {})
                  .get("episodeNumber", {}).get("episodeNumber", ""))
        if ep_num == "0":
            continue
        rating = node.get("ratingsSummary", {}).get("aggregateRating")
        if rating is not None and 0.0 < rating <= 10.0:
            ratings.append(float(rating))
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
