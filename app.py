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
import sys
from pathlib import Path

# Ensure the project root is on sys.path so local package imports work correctly.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="World Cup Sentiment Tracker")
    parser.add_argument(
        "--mock",
        action="store_true",
        default=False,
        help="Use fake tweets instead of the liveTwitter API (no credentials needed).",
    )
    parser.add_argument("--port", type=int, default=8050, help="Port for the Dash app (default: 8050)")
    parser.add_argument("--debug", action="store_true", default=False, help="Run Dash in debug mode (auto-reload on code changes)")
    args = parser.parse_args()

    #Shared tweet queue between streamer and analyser
    tweet_queue: collections.deque = collections.deque(maxlen=2000)

    # Start the streamer in a background thread
    if args.mock:
        try:
            from src.streamer import start_mock_stream
        except ModuleNotFoundError:
            from streamer import start_mock_stream
        logger.info("Starting mock tweet stream (no API credentials required).")
        stream_fn = lambda: start_mock_stream(tweet_queue)
    else:
        try:
            from src.streamer import start_stream
        except ModuleNotFoundError:
            from streamer import start_stream
        logger.info("Starting live tweet stream (requires TWITTER_BEARER_TOKEN in .env).")
        stream_fn = lambda: start_stream(tweet_queue)

    stream_thread = threading.Thread(target=stream_fn, daemon=True, name="TweetStreamThread")
    stream_thread.start()

    # --Initialise the analyser---------------------------------
    try:
        from src.analyser import get_analyser
    except ModuleNotFoundError:
        from analyser import get_analyser
    analyser = get_analyser(tweet_queue)

    # --Build and run the Dash app--------------------------------
    try:
        from src.dashboard import build_app
    except ModuleNotFoundError:
        from dashboard import build_app
    app = build_app(analyser)

    logger.info("Starting Dash app on http://localhost:%d", args.port)
    app.run(debug=args.debug, port=args.port)

if __name__ == "__main__":
    main()