"""
app.py
------
Entry point.  Starts the tweet stream in a background thread,
then launches the Dash dashboard.

    python app.py               # uses live Twitter API
    python app.py --mock        # uses fake tweets (no API key needed)
"""

import argparse
import collections
import logging
import threading

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="World Cup Sentiment Tracker")
    parser.add_argument(
        "--mock",
        action="store_true",
        default=False,
        help="Use fake tweets instead of the live Twitter API (no credentials needed).",
    )
    parser.add_argument("--port", type=int, default=8050, help="Dash server port (default 8050)")
    parser.add_argument("--debug", action="store_true", default=False, help="Enable Dash debug mode")
    args = parser.parse_args()

    # Shared tweet queue (thread-safe deque with a cap to bound memory)
    tweet_queue: collections.deque = collections.deque(maxlen=2000)

    # ── Start the stream thread ───────────────────────────────────────────────
    if args.mock:
        from src.streamer import start_mock_stream
        logger.info("Starting MOCK tweet stream (no API credentials required).")
        stream_fn = lambda: start_mock_stream(tweet_queue, interval=1.5)
    else:
        from src.streamer import start_stream
        logger.info("Starting LIVE Twitter stream (requires TWITTER_BEARER_TOKEN in .env).")
        stream_fn = lambda: start_stream(tweet_queue)

    stream_thread = threading.Thread(target=stream_fn, daemon=True, name="tweet-stream")
    stream_thread.start()

    # ── Initialise the analyser ───────────────────────────────────────────────
    from src.analyser import get_analyser
    analyser = get_analyser(tweet_queue)

    # ── Build and run the Dash app ────────────────────────────────────────────
    from src.dashboard import build_app
    app = build_app(analyser)

    logger.info("Dashboard running at http://localhost:%d", args.port)
    app.run(debug=args.debug, port=args.port)


if __name__ == "__main__":
    main()