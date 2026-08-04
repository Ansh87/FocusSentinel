"""Website catalog + family custom-website management, backing the parent
dashboard's rule-builder multi-select.

GET /websites/catalog returns the built-in catalog (TikTok, YouTube, YouTube
Shorts, Instagram, Instagram Reels, etc. — the same rows
database/seed/seed.py inserts with family_id=None) plus, when a family_id is
given, that family's own custom-added domains. It auto-seeds the global
catalog rows if the table is empty (e.g. a database created via
Base.metadata.create_all that never had seed.py run against it) — the same
self-healing pattern routers/demo.py uses for ActivityCategory rows — so this
endpoint never 500s on a fresh database.

POST /websites lets a parent add a custom domain (e.g. "Khan Academy") that
isn't in the built-in catalog, with domain validation/normalization so
"https://www.Example.com/foo" and "example.com" resolve to the same stored
row instead of silently double-counting usage under two different domain
spellings.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_parent

router = APIRouter(prefix="/websites", tags=["websites"])

# Mirrors database/seed/seed.py's CATALOG_WEBSITES, plus two extra
# optional entries the spec calls out (Facebook Watch, Snapchat). Duplicated
# here rather than imported because services/api ships as its own standalone
# deployable and shouldn't depend on the sibling database/ package being on
# its import path in production.
_CATALOG = [
    ("tiktok.com", None, "TikTok", "short_form_video", "limited"),
    ("youtube.com", "/shorts", "YouTube Shorts", "short_form_video", "limited"),
    ("instagram.com", "/reels", "Instagram Reels", "short_form_video", "limited"),
    ("facebook.com", "/reel", "Facebook Reels", "short_form_video", "limited"),
    ("instagram.com", None, "Instagram", "social_media", "limited"),
    ("facebook.com", None, "Facebook", "social_media", "limited"),
    ("facebook.com", "/watch", "Facebook Watch", "entertainment_video", "limited"),
    ("snapchat.com", None, "Snapchat", "social_media", "limited"),
    ("twitch.tv", None, "Twitch", "entertainment_video", "limited"),
    ("discord.com", None, "Discord", "messaging", "neutral"),
    ("reddit.com", None, "Reddit", "social_media", "limited"),
    ("netflix.com", None, "Netflix", "entertainment_video", "limited"),
    ("youtube.com", None, "YouTube", "entertainment_video", "neutral"),
]

_CATEGORY_LABELS = {
    "games": "Games",
    "short_form_video": "Short-form video",
    "social_media": "Social media",
    "entertainment_video": "Entertainment video",
    "messaging": "Messaging",
    "educational": "Educational",
    "productivity": "Productivity",
    "creative_work": "Creative work",
    "reading_research": "Reading and research",
    "other": "Other",
}

# Deliberately conservative: a plain "label.label...label" hostname, no
# scheme, no path, no whitespace, no unicode punycode edge cases. Anything
# fancier gets rejected with a clear 400 rather than silently accepted and
# mismatched later.
_DOMAIN_RE = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)(\.[a-z0-9-]{1,63})+$")


def normalize_domain(raw: str) -> str:
    """Strips scheme, "www.", path/query/fragment, and lowercases — so
    "https://www.Example.com/foo?x=1" and "example.com" both normalize to
    "example.com" and match the same stored Website row instead of being
    tracked (and counted) as two different sites."""
    value = raw.strip().lower()
    value = re.sub(r"^[a-z]+://", "", value)
    value = value.split("/")[0].split("?")[0].split("#")[0]
    if value.startswith("www."):
        value = value[4:]
    return value


def _ensure_catalog_seeded(db: Session) -> None:
    if db.query(models.Website).filter_by(family_id=None).first():
        return
    for domain, url_pattern, label, category_key, classification in _CATALOG:
        category = db.query(models.ActivityCategory).filter_by(key=category_key).first()
        if category is None:
            category = models.ActivityCategory(key=category_key, label=_CATEGORY_LABELS.get(category_key, category_key))
            db.add(category)
            db.flush()
        db.add(
            models.Website(
                family_id=None,
                domain=domain,
                url_pattern=url_pattern,
                label=label,
                category_id=category.id,
                classification=classification,
                source="catalog",
            )
        )
    db.commit()


def _to_out(w: models.Website) -> schemas.WebsiteOut:
    return schemas.WebsiteOut(
        id=w.id,
        domain=w.domain,
        url_pattern=w.url_pattern,
        label=w.label,
        category_id=w.category_id,
        source=w.source,
        is_custom=w.family_id is not None,
    )


@router.get("/catalog", response_model=list[schemas.WebsiteOut])
def list_catalog(
    family_id: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_parent),
):
    _ensure_catalog_seeded(db)
    rows = db.query(models.Website).filter(models.Website.family_id.is_(None)).order_by(models.Website.label).all()
    if family_id:
        custom = (
            db.query(models.Website)
            .filter(models.Website.family_id == family_id)
            .order_by(models.Website.label)
            .all()
        )
        rows = rows + custom
    return [_to_out(w) for w in rows]


@router.post("", response_model=schemas.WebsiteOut, status_code=201)
def add_custom_website(
    payload: schemas.WebsiteCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_parent),
):
    family = db.get(models.Family, payload.family_id)
    if not family:
        raise HTTPException(404, "Family not found")
    membership = db.query(models.FamilyMember).filter_by(family_id=family.id, user_id=user.id).first()
    if not membership:
        raise HTTPException(403, "You don't have access to this family")

    domain = normalize_domain(payload.domain)
    if not domain or not _DOMAIN_RE.match(domain):
        raise HTTPException(400, "Enter a valid domain, like example.com")

    category_id = None
    if payload.category_key:
        category = db.query(models.ActivityCategory).filter_by(key=payload.category_key).first()
        if not category:
            # Categories are just labels, not a curated enum — auto-create
            # rather than reject, the same self-healing pattern used for the
            # catalog seed above, so a custom "Educational" pick doesn't fail
            # just because no rule has referenced that category yet.
            category = models.ActivityCategory(
                key=payload.category_key,
                label=_CATEGORY_LABELS.get(payload.category_key, payload.category_key.replace("_", " ").title()),
            )
            db.add(category)
            db.flush()
        category_id = category.id

    existing = (
        db.query(models.Website)
        .filter_by(family_id=payload.family_id, domain=domain, url_pattern=payload.url_pattern)
        .first()
    )
    if existing:
        return _to_out(existing)

    label = payload.label.strip() or domain
    website = models.Website(
        family_id=payload.family_id,
        domain=domain,
        url_pattern=payload.url_pattern,
        label=label,
        category_id=category_id,
        classification="limited",
        source="custom",
    )
    db.add(website)
    db.add(
        models.AuditLog(
            family_id=family.id,
            actor_user_id=user.id,
            actor_type="parent",
            action="website.created",
            target_type="website",
            target_id=website.id,
            event_metadata={"domain": domain, "label": label},
        )
    )
    db.commit()
    db.refresh(website)
    return _to_out(website)
