"""Provider abstraction for TikTok video data.

Two implementations:
  RealTikTokProvider  – calls TikTok API v2 with a stored access token
  MockTikTokProvider  – generates deterministic fake data for testing / demo

Switch via Settings → use_mock_tiktok.
"""
from __future__ import annotations
import hashlib
import random
import logging
from abc import ABC, abstractmethod
from typing import Optional
from models.game import GameVideo

log = logging.getLogger(__name__)

# ── Mock data pool ────────────────────────────────────────────────────────────

_DESCRIPTIONS = [
    "Teaching my cat to code 🐱💻",
    "POV: you finally fixed the bug at 3am ✨",
    "Cooking the best ramen you'll ever taste 🍜",
    "Day in the life of a software engineer",
    "When the product manager says 'just a small change'",
    "This sunset hit different 🌅",
    "My dog learned a new trick! 🐕",
    "Explaining recursion using Russian dolls",
    "Street magic that'll blow your mind 🪄",
    "Making sourdough bread from scratch",
    "The most satisfying pressure wash of 2024",
    "Why I quit my 9-5 to travel the world ✈️",
    "Rating every fast food fries – tier list",
    "Running my first marathon at 50 🏃",
    "This life hack changed everything",
    "Painting a portrait in 60 seconds",
    "Building a tiny house in the woods 🏡",
    "The algorithm is wild tonight 😂",
    "Learning guitar: one week challenge 🎸",
    "Science experiment gone wrong 💥",
    "Thrift flip: $5 to stunning 🪡",
    "What I eat in a day as a vegan athlete 🥗",
    "History of the internet in 60 seconds",
    "My plant died so I painted it instead 🪴",
    "Unpacking my vintage camera haul 📷",
    "When math finally makes sense ✨",
    "Street art timelapse in NYC 🎨",
    "Making a drum kit out of trash 🥁",
    "Trying viral TikTok foods, ranked",
    "Honest apartment tour no filter",
    "Night shift nurses deserve the world 💙",
    "Coding a snake game in Python 🐍",
    "The perfect cup of pour-over coffee ☕",
    "How I lost 30lbs without giving up pizza 🍕",
    "Satisfying embroidery tutorial",
    "Testing $1 vs $1,000 headphones 🎧",
    "Midnight library aesthetic 📚",
    "Dance challenge ft. my grandma 💃",
    "Surprising my mom with a house 🏠",
    "Anime openings but make it lo-fi",
    "I tried every Trader Joe's snack 🛒",
    "Interior design transformation – 60 seconds",
    "First time paragliding in the Alps 🏔️",
    "Coding an entire game in 24 hours",
    "Mini city built from cardboard",
    "Why your plants keep dying 🌿",
    "Honest résumé roast session",
    "Lego mosaic of the Mona Lisa 🧱",
    "Foods from my childhood country 🍽️",
    "Midnight baking session 🌙",
]

_CATEGORIES = [
    ("#FF6B6B", "#FF8E53"),
    ("#4ECDC4", "#44A08D"),
    ("#43E97B", "#38F9D7"),
    ("#F7971E", "#FFD200"),
    ("#667EEA", "#764BA2"),
    ("#FE2C55", "#FE2C8A"),
    ("#25F4EE", "#0070F3"),
    ("#A18CD1", "#FBC2EB"),
]

_AUTHORS = [
    "creator_x", "viralqueen", "techbro99", "chef_modo",
    "traveler.jess", "fitguru", "artblock", "gamer_real",
    "musicmaker", "comedykid",
]


class TikTokProvider(ABC):
    @abstractmethod
    def get_videos(self, access_token: str, max_count: int = 30) -> list[GameVideo]:
        """Fetch the user's videos (posted or liked, depending on scope)."""

    @abstractmethod
    def get_user_info(self, access_token: str) -> Optional[dict]:
        """Return {'open_id', 'display_name'} or None on error."""

    def get_gradient_colors(self, video: GameVideo) -> tuple[str, str]:
        """Return a (color1, color2) gradient pair for thumbnail placeholder."""
        idx = int(hashlib.md5(video.video_id.encode()).hexdigest(), 16) % len(_CATEGORIES)
        return _CATEGORIES[idx]


class MockTikTokProvider(TikTokProvider):
    """Deterministic mock provider – no network required."""

    def get_videos(self, access_token: str, max_count: int = 30) -> list[GameVideo]:
        # Seed from the token so the same "user" always gets the same videos
        seed_val = int(hashlib.md5(access_token.encode()).hexdigest(), 16) % (2 ** 31)
        rng = random.Random(seed_val)
        indices = rng.sample(range(len(_DESCRIPTIONS)), min(max_count, len(_DESCRIPTIONS)))
        videos = []
        for i in indices:
            c1, c2 = _CATEGORIES[i % len(_CATEGORIES)]
            videos.append(GameVideo(
                video_id=f"mock_{access_token[:8]}_{i:04d}",
                description=_DESCRIPTIONS[i],
                thumbnail_url=f"mock://{c1}/{c2}",
                thumbnail_path=None,
                author_username=_AUTHORS[i % len(_AUTHORS)],
                view_count=rng.randint(1_000, 10_000_000),
                like_count=rng.randint(100, 500_000),
                owner_player_id="",
            ))
        return videos

    def get_user_info(self, access_token: str) -> Optional[dict]:
        return {"open_id": f"mock_{access_token[:8]}", "display_name": "MockUser"}


class RealTikTokProvider(TikTokProvider):
    """Calls TikTok API v2. Requires valid client credentials and access token."""

    def get_videos(self, access_token: str, max_count: int = 30) -> list[GameVideo]:
        """Fetch videos posted by the authenticated user (video.list scope)."""
        import requests
        videos: list[GameVideo] = []
        cursor = 0
        per_page = min(max_count, 20)

        while len(videos) < max_count:
            try:
                resp = requests.post(
                    "https://open.tiktokapis.com/v2/video/list/",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type":  "application/json",
                    },
                    json={
                        "max_count": per_page,
                        "cursor":    cursor,
                        "fields":    [
                            "id", "title", "description", "cover_image_url",
                            "author_name", "view_count", "like_count",
                        ],
                    },
                    timeout=15,
                )
                resp.raise_for_status()
                data = resp.json().get("data", {})
                items = data.get("videos", [])
                for item in items:
                    videos.append(GameVideo(
                        video_id=item.get("id", ""),
                        description=(item.get("title") or item.get("description") or "")[:200],
                        thumbnail_url=item.get("cover_image_url", ""),
                        thumbnail_path=None,
                        author_username=item.get("author_name", ""),
                        view_count=item.get("view_count", 0),
                        like_count=item.get("like_count", 0),
                        owner_player_id="",
                    ))
                if not data.get("has_more", False):
                    break
                cursor = data.get("cursor", 0)
            except Exception as exc:
                log.error("TikTok video list error: %s", exc)
                break

        return videos[:max_count]

    def get_user_info(self, access_token: str) -> Optional[dict]:
        import requests
        try:
            resp = requests.get(
                "https://open.tiktokapis.com/v2/user/info/",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"fields": "open_id,display_name,avatar_url"},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json().get("data", {}).get("user", {})
        except Exception as exc:
            log.error("TikTok user info error: %s", exc)
            return None


def make_provider(use_mock: bool = True) -> TikTokProvider:
    return MockTikTokProvider() if use_mock else RealTikTokProvider()
