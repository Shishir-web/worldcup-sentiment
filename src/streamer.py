"""
src/streamer.py
---------------
Connects to the Twitter v2 Filtered Stream API via Tweepy and
pushes matching tweets into a shared thread-safe deque.
 
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
import threading
import collections
import tweepy
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# -- Keywords that define "a World Cup Tweet" -----------
TRACK_KEYWORDS = [
    "world cup",
    "fifa world cup",
    "fifa wc",
    "fifa w cup",
    "fifa w-cup",
    "fifa w_cup", "goal","penalty", "offside", "red card", "yellow card", "substitution", "goalkeeper", "referee", "coach", "manager", "player", "team", "match", "tournament", "stadium", "fans", "crowd", "celebration", "victory", "defeat", "draw", "score", "scoreline", "halftime", "fulltime", "extra time", "penalty shootout", "group stage", "knockout stage", "finals"
    "GOAL",
    "PENALTY",
    "OFFSIDE",
    "RED CARD","⚽","🟥"," 🟨"
]

# One rule per Tweepy add_rules() call.  Adjust the operators as you like.
# Full operator reference: https://developer.twitter.com/en/docs/twitter-api/tweets/filtered-stream/integrate/build-a-rule 
STREAM_RULES = [
    tweepy.StreamRule(
        "(WorldCup or FIFA or FIFAWC or FIFAWCup or FIFAW-Cup or FIFAW_Cup or goal or penalty or offside or red card or yellow card or substitution or goalkeeper or referee or coach or manager or player or team or match or tournament or stadium or fans or crowd or celebration or victory or defeat or draw or score or scoreline or halftime or fulltime or extra time or penalty shootout or group stage or knockout stage or finals) lang:en -is:retweet -is:reply -is:quote",
        tag="worldcup_en"
    ),
    ]

class _SentimentStream(tweepy.StreamingClient):
    """Tweepy v4 StreamingClient subclass.  Pushes raw tweet text into *queue*."""

    def __init__(self, bearer_token, queue: collections.deque, **kwargs):
        super().__init__(bearer_token, **kwargs)
        self.queue = queue

    # Called for every tweet that matches the rules
    def on_tweet(self, tweet: tweepy.Tweet):
        text = tweet.text
        if text:
            self.queue.append(
                {
                    "id": tweet.id,
                    "text": text,
                    "timestamp": time.time(),
                }
            )

    def on_errors(self, errors):
        logger.error(f"Stream error: {errors}")
        
    def on_exception(self, exception):
        logger.error(f"Stream exception: {exception}")
        
def _setup_stream(client: _SentimentStream):
    """Deletes existing rules and adds new ones."""
    existing_rules = client.get_rules().data or []
    if existing_rules:
        ids = [r.id for r in existing_rules]
        client.delete_rules(ids)
        logger.info("Deleted existing rules.", len(ids))
    client.add_rules(STREAM_RULES)
    logger.info("Stream rules set: %s", [r.value for r in STREAM_RULES])

def start_stream(queue: collections.deque, reconnect_delay: int =10):
    """ Blocking function – run in a daemon thread.
    Reconnects automatically on network errors."""    
    
    bearer_token = os.getenv("TWITTER_BEARER_TOKEN")
    if not bearer_token:
        raise EnvironmentError("TWITTER_BEARER_TOKEN not set. "
                               "Copy .env.example to .env and fill in your Twitter API credentials."
        
        )
    while True:
        try:
            client = _SentimentStream(
                bearer_token=bearer_token,
                queue=queue,
                wait_on_rate_limit=True,
            )
            _setup_stream(client)
            logger.info("Stream connected. Waiting for tweets...")
            # tweet_fields we actually need are minimal (text is the default)
            client.filter(tweet_fields=["id", "text"])
        except tweepy.errors.TweepyException as exc:
            logger.error("TweepyException: %s - reconnecting in %ds", exc, reconnect_delay)
            time.sleep(reconnect_delay)
        except Exception as exc:
            logger.exception("TweepyException: %s - reconnecting in %ds", exc, reconnect_delay)
            time.sleep(reconnect_delay)


# --- Demo / Offline mock -----------------------

DEMO_TWEETS = [
     "GOAL!! 🇧🇷 Brazil scores! What an incredible strike! #WorldCup ⚽",
    "That was offside, come on referee! #FIFA #WC2026",
    "France looking dangerous every time they get the ball forward",
    "GOAAAAAAL Argentina!! Messi does it again! 🔥⚽ #WorldCup",
    "Terrible defending. This game is a disaster for England",
    "Best World Cup in years honestly. The atmosphere is electric!",
    "Penalty awarded! This is controversial... #FIFA",
    "VAR overturns the goal. Heartbreak for the fans",
    "What a save! The goalkeeper has been outstanding all tournament",
    "GOAL!! Germany equalises! We have a game on our hands! ⚽⚽",
]

def start_mock_stream(queue: collection.deque, interval: float = 2.0):
    """
    Pushes fake tweets into *queue* so you can develop & test without API access.
    Run in a daemon thread just like start_stream(). 
    """
    import random
    i = 0
    while True:
        queue.append(
            {
                "id": i,
                "text": random.choice(DEMO_TWEETS),
                "timestamp": time.time(),
            }
        )
        i += 1
        time.sleep(interval)
