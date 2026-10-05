"""Offline tests for the RSS news ingestion + importance scoring engine.

No network anywhere: feeds are injected via a fake http_get and fixture XML.
"""

import calendar
import time

import pytest

from godmode.data.news_monitor import (
    DEFAULT_FEEDS,
    NewsMonitor,
    parse_feed,
    recency_score,
    score_items,
    severity_score,
    tier_credibility,
    title_similarity,
)

SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>Feed</title>
<item>
  <title>Major exchange hacked, millions stolen</title>
  <link>https://example.com/1</link>
  <pubDate>Tue, 25 Aug 2026 10:00:00 GMT</pubDate>
  <description>Brief text</description>
</item>
<item>
  <title>Routine weekly market roundup</title>
  <link>https://example.com/2</link>
  <pubDate>Mon, 24 Aug 2026 09:00:00 GMT</pubDate>
</item>
</channel></rss>"""

SAMPLE_ATOM = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<title>Feed</title>
<entry>
  <title>ETF approval sparks rally</title>
  <link href="https://example.com/a1"/>
  <updated>2026-08-25T08:30:00Z</updated>
  <summary>Text</summary>
</entry>
</feed>"""


def test_default_feeds_have_name_url_tier():
    assert len(DEFAULT_FEEDS) >= 3
    for feed in DEFAULT_FEEDS:
        assert feed["name"] and feed["url"].startswith("https://")
        assert feed["tier"] in (1, 2, 3)


def test_parse_rss_extracts_items_and_dates():
    items = parse_feed(SAMPLE_RSS)
    assert len(items) == 2
    assert items[0]["title"] == "Major exchange hacked, millions stolen"
    assert items[0]["link"] == "https://example.com/1"
    assert items[0]["published_epoch"] is not None
    expected = calendar.timegm((2026, 8, 25, 10, 0, 0, 0, 0, 0))
    assert abs(items[0]["published_epoch"] - expected) < 1.0


def test_parse_atom_entries():
    items = parse_feed(SAMPLE_ATOM)
    assert len(items) == 1
    assert items[0]["title"] == "ETF approval sparks rally"
    assert items[0]["link"] == "https://example.com/a1"
    assert items[0]["published_epoch"] is not None


def test_parse_garbage_returns_empty():
    assert parse_feed("this is not xml <<<") == []
    assert parse_feed("") == []


def test_severity_keywords_ranking():
    assert severity_score("Exchange hack drains wallets") == 1.0
    assert severity_score("Company files for bankruptcy") == 1.0
    assert severity_score("Bitcoin surge continues") == 0.70
    assert severity_score("Weekly roundup of quiet news") == 0.35


def test_recency_decay_and_unknown_neutral():
    now = 1_800_000_000.0
    fresh = recency_score(now - 600, now)
    old = recency_score(now - 48 * 3600, now)
    unknown = recency_score(None, now)
    assert fresh > old
    assert old < 0.1
    assert unknown == 0.5


def test_tier_credibility_mapping():
    assert tier_credibility(1) == 1.0
    assert tier_credibility(2) > tier_credibility(3)
    assert tier_credibility(99) == tier_credibility(3)


def test_title_similarity_jaccard():
    assert title_similarity("btc etf approved today", "BTC ETF Approved Today") == 1.0
    assert title_similarity("cat", "dog") == 0.0
    assert 0.0 < title_similarity("btc rally", "btc rally today") < 1.0


def test_importance_formula_exact_single_item():
    # routine title -> severity .35; tier3 -> .3333; no corroboration; unknown date -> recency .5
    items = [{
        "title": "quiet weekly note",
        "source": "BlogC",
        "tier": 3,
        "published_epoch": None,
        "link": "",
    }]
    scored = score_items(items, now=1_800_000_000.0)
    assert len(scored) == 1
    expected = round(0.55 * 0.35 + 0.20 * (1 / 3) + 0.15 * 0.0 + 0.10 * 0.5, 4)
    assert scored[0]["importance"] == pytest.approx(expected, abs=1e-4)


def test_corroboration_merges_duplicate_story_across_sources():
    now = 1_800_000_000.0
    items = [
        {"title": "major exchange hack funds stolen", "source": "A", "tier": 1,
         "published_epoch": now - 3600},
        {"title": "major exchange hack funds stolen", "source": "B", "tier": 2,
         "published_epoch": now - 7200},
        {"title": "completely different topic about weather", "source": "A", "tier": 1,
         "published_epoch": now - 60},
    ]
    scored = score_items(items, now=now)
    assert len(scored) == 2
    top = scored[0]
    assert top["member_count"] == 2
    assert set(top["corroborating_sources"]) == {"B"}
    # corroboration component must be exactly 0.5 for two distinct sources
    assert top["components"]["corroboration"] == pytest.approx(0.5, abs=1e-4)
    # ranked by importance: corroborated high-severity wire story first
    assert "hack" in top["title"]
    assert top["importance"] > scored[1]["importance"]


def _fake_http_get_factory(responses):
    def fake_get(url, timeout=8.0):
        if url in responses:
            value = responses[url]
            if isinstance(value, Exception):
                raise value
            return value
        raise AssertionError(f"unexpected url {url}")
    return fake_get


def test_news_monitor_fetch_all_scores_and_attaches_source():
    monitor = NewsMonitor(
        feeds=[{"name": "TestWire", "url": "https://feeds.test/rss", "tier": 1}],
        http_get=_fake_http_get_factory({"https://feeds.test/rss": SAMPLE_RSS}),
    )
    out = monitor.fetch_all()
    assert len(out) == 2
    assert all(i["source"] == "TestWire" for i in out)
    assert out[0]["importance"] >= out[1]["importance"]
    assert out[0]["title"] == "Major exchange hacked, millions stolen"


def test_news_monitor_fail_soft_on_dead_feed():
    responses = {
        "https://dead.test/rss": ConnectionError("boom"),
        "https://alive.test/rss": SAMPLE_RSS,
    }
    monitor = NewsMonitor(
        feeds=[
            {"name": "Dead", "url": "https://dead.test/rss", "tier": 1},
            {"name": "Alive", "url": "https://alive.test/rss", "tier": 2},
        ],
        http_get=_fake_http_get_factory(responses),
    )
    out = monitor.fetch_all()
    assert len(out) == 2
    assert {i["source"] for i in out} == {"Alive"}
