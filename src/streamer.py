"""
src/streamer.py
---------------
Connects to Reddit via PRAW and streams comments from World Cup
related subreddits into a shared thread-safe deque.

Usage (run in a background thread):
    from src.streamer import start_stream
    import threading, collections
    q = collections.deque(maxlen=500)
    t = threading.Thread(target=start_stream, args=(q,), daemon=True)
    t.start()
"""

import os
import time
import logging
import collections

import praw
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Subreddits to monitor (+ joins them into one stream)
SUBREDDITS = "soccer+worldcup+football"

# Only pass comments containing at least one of these keywords
MATCH_KEYWORDS = [
    "goal", "score", "scored", "penalty", "worldcup",
    "fifa", "match", "foul", "offside", "referee", "⚽",
]


def _get_reddit_client() -> praw.Reddit:
    """
    Initialise and return a read-only Reddit client using
    credentials from the .env file.
    """
    client_id     = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    user_agent    = os.getenv("REDDIT_USER_AGENT", "WorldCupSentimentTracker/1.0")

    if not client_id or not client_secret:
        raise EnvironmentError(
            "REDDIT_CLIENT_ID or REDDIT_CLIENT_SECRET not set. "
            "Copy .env.example → .env and fill in your credentials."
        )

    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent,
    )


def _is_relevant(text: str) -> bool:
    """
    Returns True if the comment contains at least one match keyword.
    Filters out unrelated comments from the subreddit stream.
    """
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in MATCH_KEYWORDS)


def start_stream(queue: collections.deque, reconnect_delay: int = 10):
    """
    Streams comments from World Cup subreddits in real time.
    Blocking function — run in a daemon thread.
    Reconnects automatically on network errors.

    Args:
        queue:            Shared deque to push comment dicts into.
        reconnect_delay:  Seconds to wait before reconnecting on error.
    """
    reddit = _get_reddit_client()
    subreddit = reddit.subreddit(SUBREDDITS)

    logger.info("Connected to Reddit. Streaming comments from r/%s", SUBREDDITS)

    while True:
        try:
            # skip_existing=True means we only get NEW comments from this point
            for comment in subreddit.stream.comments(skip_existing=True):
                text = comment.body

                # Skip deleted/removed comments
                if not text or text in ("[deleted]", "[removed]"):
                    continue

                # Only keep match-relevant comments
                if not _is_relevant(text):
                    continue

                queue.append({
                    "id":        comment.id,
                    "text":      text,
                    "subreddit": str(comment.subreddit),
                    "timestamp": time.time(),
                })

        except Exception as exc:
            logger.error(
                "Stream error: %s — reconnecting in %ds", exc, reconnect_delay
            )
            time.sleep(reconnect_delay)


def start_match_thread_stream(queue: collections.deque, thread_url: str, reconnect_delay: int = 10):
    """
    Streams comments from a SPECIFIC Reddit match thread.
    Use this during a live match for a much cleaner, higher-volume signal.

    Find the match thread URL on r/soccer during the game, e.g.:
    https://www.reddit.com/r/soccer/comments/abc123/match_thread_brazil_vs_france/

    Args:
        queue:            Shared deque to push comment dicts into.
        thread_url:       Full URL of the Reddit match thread.
        reconnect_delay:  Seconds to wait before reconnecting on error.
    """
    reddit = _get_reddit_client()

    logger.info("Streaming match thread: %s", thread_url)

    while True:
        try:
            submission = reddit.submission(url=thread_url)
            for comment in submission.stream.comments(skip_existing=True):
                text = comment.body

                if not text or text in ("[deleted]", "[removed]"):
                    continue

                # Match thread comments are all relevant — no keyword filter needed
                queue.append({
                    "id":        comment.id,
                    "text":      text,
                    "subreddit": str(comment.subreddit),
                    "timestamp": time.time(),
                })

        except Exception as exc:
            logger.error(
                "Match thread stream error: %s — reconnecting in %ds", exc, reconnect_delay
            )
            time.sleep(reconnect_delay)


# ── Mock stream for development ───────────────────────────────────────────────

DEMO_COMMENTS = [
    "GOAL!! Brazil scores what a strike! ⚽ #WorldCup",
    "That was clearly offside, VAR needs to check this",
    "France looking dangerous every time they attack",
    "GOAAAAAL Argentina!! Messi does it again! Unbelievable!",
    "Terrible defending from England, this is embarrassing",
    "Best World Cup in years, the atmosphere is electric",
    "Penalty awarded! This is so controversial...",
    "VAR overturns the goal, absolute heartbreak for the fans",
    "What a save! The goalkeeper has been man of the match",
    "GOAL!! Germany equalises! What a game this is! ⚽",
    "The referee is having a nightmare today",
    "Incredible passing from Spain, they are on another level",
    "This match is so boring, nothing is happening",
    "Best goal of the tournament so far easily",
    "Penalty scored! 2-1 and the crowd goes absolutely wild",
]


def start_mock_stream(queue: collections.deque, interval: float = 2.0):
    """
    Pushes fake Reddit-style comments into the queue at a fixed interval.
    Use this to develop and test without Reddit API credentials.

    Args:
        queue:    Shared deque to push comment dicts into.
        interval: Seconds between each fake comment.
    """
    import random
    i = 0
    logger.info("Mock stream started. Pushing a comment every %.1fs", interval)

    while True:
        queue.append({
            "id":        i,
            "text":      random.choice(DEMO_COMMENTS),
            "subreddit": "soccer",
            "timestamp": time.time(),
        })
        i += 1
        time.sleep(interval) 