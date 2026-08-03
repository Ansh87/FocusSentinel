"""Maintained classification catalog shared conceptually with
apps/browser-extension/lib/classifier.js (kept in sync manually; see that
file's header comment). This is the source used by the API for
auto-detected applications/websites and for seeding the default catalog.

Adding an entry here does not, by itself, track anything — an activity is
only measured once a family enables it (see `websites`/`applications`
tables, `source = 'catalog'` rows are suggestions, not active rules).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogEntry:
    key: str                 # domain or process/package identifier
    label: str
    category: str            # matches activity_categories.key
    match_type: str          # 'domain' | 'url_pattern' | 'process' | 'package' | 'bundle_id'
    classification: str = "limited"  # 'productive' | 'neutral' | 'limited'


_DOMAIN_CATALOG: list[CatalogEntry] = [
    CatalogEntry("tiktok.com", "TikTok", "short_form_video", "domain"),
    CatalogEntry("youtube.com/shorts", "YouTube Shorts", "short_form_video", "url_pattern"),
    CatalogEntry("instagram.com/reels", "Instagram Reels", "short_form_video", "url_pattern"),
    CatalogEntry("facebook.com/reel", "Facebook Reels", "short_form_video", "url_pattern"),
    CatalogEntry("instagram.com", "Instagram", "social_media", "domain"),
    CatalogEntry("facebook.com", "Facebook", "social_media", "domain"),
    CatalogEntry("twitch.tv", "Twitch", "entertainment_video", "domain"),
    CatalogEntry("discord.com", "Discord", "messaging", "domain", classification="neutral"),
    CatalogEntry("reddit.com", "Reddit", "social_media", "domain"),
    CatalogEntry("netflix.com", "Netflix", "entertainment_video", "domain"),
    CatalogEntry("youtube.com", "YouTube", "entertainment_video", "domain", classification="neutral"),
]

_PROCESS_CATALOG: list[CatalogEntry] = [
    CatalogEntry("steam.exe", "Steam", "games", "process"),
    CatalogEntry("epicgameslauncher.exe", "Epic Games Launcher", "games", "process"),
    CatalogEntry("xboxapp.exe", "Xbox App", "games", "process"),
    CatalogEntry("robloxplayerbeta.exe", "Roblox", "games", "process"),
    CatalogEntry("minecraft.exe", "Minecraft", "games", "process"),
    CatalogEntry("fortniteclient-win64-shipping.exe", "Fortnite", "games", "process"),
    CatalogEntry("com.mojang.minecraftpe", "Minecraft (mobile)", "games", "package"),
    CatalogEntry("com.roblox.client", "Roblox (mobile)", "games", "package"),
    CatalogEntry("com.zhiliaoapp.musically", "TikTok (mobile)", "short_form_video", "package"),
    CatalogEntry("com.instagram.android", "Instagram (mobile)", "social_media", "package"),
    CatalogEntry("com.burbn.instagram", "Instagram (iOS)", "social_media", "bundle_id"),
]


def default_catalog() -> list[CatalogEntry]:
    return list(_DOMAIN_CATALOG) + list(_PROCESS_CATALOG)


def classify_domain(hostname: str, path: str = "") -> CatalogEntry | None:
    """Longest-match-wins classification for a browser URL. `hostname` should
    be lowercased and stripped of 'www.'; `path` is the URL path (with
    leading slash) used for url_pattern entries like youtube.com/shorts.
    """
    hostname = hostname.lower().removeprefix("www.")
    candidates = [
        c
        for c in _DOMAIN_CATALOG
        if c.match_type == "domain" and hostname == c.key
        or c.match_type == "url_pattern" and f"{hostname}{path}".startswith(c.key)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda c: len(c.key))


def classify_process(identifier: str) -> CatalogEntry | None:
    identifier = identifier.lower()
    for c in _PROCESS_CATALOG:
        if c.key == identifier:
            return c
    return None
