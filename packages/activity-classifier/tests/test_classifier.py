from activity_classifier import classify_domain, classify_process


def test_classifies_tiktok_domain():
    entry = classify_domain("tiktok.com")
    assert entry is not None
    assert entry.category == "short_form_video"


def test_classifies_youtube_shorts_url_pattern_not_youtube_generic():
    entry = classify_domain("youtube.com", "/shorts/abc123")
    assert entry is not None
    assert entry.key == "youtube.com/shorts"
    assert entry.category == "short_form_video"


def test_classifies_generic_youtube_as_neutral_entertainment():
    entry = classify_domain("youtube.com", "/watch?v=abc123")
    assert entry is not None
    assert entry.key == "youtube.com"
    assert entry.classification == "neutral"


def test_strips_www_prefix():
    entry = classify_domain("www.tiktok.com")
    assert entry is not None
    assert entry.key == "tiktok.com"


def test_unknown_domain_returns_none():
    assert classify_domain("example.com") is None


def test_classifies_known_game_process():
    entry = classify_process("RobloxPlayerBeta.exe")
    assert entry is not None
    assert entry.category == "games"


def test_unknown_process_returns_none():
    assert classify_process("notepad.exe") is None
