#!/usr/bin/env python3
"""Plot IMDb episode ratings for a TV series."""

import re
import sys
import time

import numpy as np
import matplotlib.pyplot as plt
import requests
from bs4 import BeautifulSoup

plt.style.use("dark_background")

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
    )
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    seasons = set()
    for a in soup.find_all("a", href=re.compile(r"season=(\d+)")):
        m = re.search(r"season=(\d+)", a["href"])
        if m:
            text = a.get_text(strip=True)
            # Only take numeric season links (skip "Seasons" label)
            if text.isdigit():
                seasons.add(int(m.group(1)))
    return sorted(seasons)


def get_episode_ratings(imdb_id: str, season: int) -> list[float]:
    """Return list of episode ratings for a given season."""
    r = requests.get(
        f"https://www.imdb.com/title/{imdb_id}/episodes/",
        params={"season": season},
        headers=HEADERS,
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


def get_scores(title: str) -> tuple[list[list[float]], str]:
    """Fetch all season episode ratings for a TV series title.

    Returns (list of per-season rating lists, display_title).
    """
    imdb_id, display_title = search_series(title)
    print(f"Found: {display_title} ({imdb_id})")
    seasons = get_season_numbers(imdb_id)
    print(f"Seasons: {seasons}")

    all_scores = []
    for s in seasons:
        ratings = get_episode_ratings(imdb_id, s)
        if len(ratings) > 1:
            all_scores.append(ratings)
        time.sleep(0.3)  # be polite
    return all_scores, display_title


def make_series_plot(title: str) -> None:
    """Produce a scatter + trend plot of episode ratings across seasons."""
    all_scores, display_title = get_scores(title)
    if not all_scores:
        print(f"No episode ratings found for '{title}'")
        return

    ct = 0
    fig = plt.figure(figsize=(12, 10), dpi=100)

    for season_scores in all_scores:
        order = [ct + x for x in range(len(season_scores))]
        x = np.array(order)
        y = np.array(season_scores)
        plt.scatter(x, y)
        plt.plot(np.unique(x), np.poly1d(np.polyfit(x, y, 1))(np.unique(x)))
        ct += len(order)

    plt.title(display_title)
    plt.xlabel("Episode Number")
    plt.ylabel("IMDb Score")
    plt.ylim((0.0, 10.0))
    plt.show()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <TV series title>")
        sys.exit(1)
    make_series_plot(" ".join(sys.argv[1:]))
