"""
src/analyser.py
---------------
Loads a HuggingFace model fine-tuned on Twitter sentiment and exposes a
simple scoring function that returns a float in [-1, 1].
 
Model used: cardiffnlp/twitter-roberta-base-sentiment-latest
  • Label 0 → Negative  → maps to -1
  • Label 1 → Neutral   → maps to  0
  • Label 2 → Positive  → maps to +1
 
The analyser also watches the tweet queue for goal-keyword spikes and
records "goal events" with a timestamp for the dashboard annotations.
"""

import re
import time
import logging
import collections
from dataclasses import dataclass, field
from threading import Lock
from typing import List, Optional

import torch  # type: ignore
# Some environments/linters may not resolve the `transformers` package; ignore static import errors.
from transformers import AutoTokenizer, AutoModelForSequenceClassification  # type: ignore
import torch.nn.functional as F  # type: ignore

logger = logging.getLogger(__name__)

MODEL_NAME = "cardiffnlp/twitter-roberta-base-sentiment-latest"

# keywords whose sudden spike in frequency may indicate a "goal event" to annotate on the dashboard
GOAL_KEYWORDS = (["goal", "scores", "scored","goaaaal", "⚽", "GOAL"])

#How many tweets in one batch to classify at once (tune to your GPU/CPU)
BATCH_SIZE = 16

@dataclass
class SentimentPoint:
    timestamp: float
    score: float # in [-1, 1]
    tweet_count: int
    is_goal_event: bool = False

class SentimentAnalyser:
    """ Thread-safe class that:
      1. Drains the tweet queue in batches
      2. Runs HuggingFace inference
      3. Stores a rolling history of SentimentPoints
      4. Detects goal spikes
    """

    def __init__(
            self,
            queue: collections.deque,
            window_seconds: int = 30,
            history_minutes: int = 90,
    ):
        self.queue = queue
        self.window_seconds = window_seconds
        self.history_minutes = history_minutes

        self.lock = Lock()
        self.history: List[SentimentPoint] = []
        self.goal_events: List[float] = []  # timestamps of detected goal events
        self._last_batch_time = time.time()


        # Load model and tokenizer once in the constructor
        logger.info("Loading model %s...", MODEL_NAME)
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        self.model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
        self.model.eval()  # set to eval mode for inference
        logger.info("Model ready.")

    # ---Public API for the dashboard to get the current sentiment history and goal events---

    def get_history(self) -> List[SentimentPoint]:
        with self._lock:
            cutoff = time.time() - self.history_minutes * 60
            return [p for p in self.history if p.timestamp >= cutoff]
        
    def get_goal_events(self) -> List[float]:
        with self._lock:
            cutoff = time.time() - self.history_minutes * 60
            return [t for t in self.goal_events if t >= cutoff]
        
    def process_batch(self):
        """
        Drain tweets accumulated since last call, classify them, and
        append a new SentimentPoint to history.  Call from the Dash
        interval callback (or a background thread).
        """
        now = time.time()
        # Drain queue
        batch = []
        while self.queue:
            try:
                batch.append(self.queue.peopleleft())
            except IndexError:
                break

        if not batch:
            return
        
        texts = [item["text"] for item in batch]
        scores = self._score_texts(texts)
        avg_score = sum(scores) / len(scores)

        # Goal detection: does this batch contain a spike in goal-related keywords?
        goal_hit = self._detect_goal(texts)

        point = SentimentPoint(
            timestamp=now,
            score=round(avg_score, 4),
            tweet_count=len(batch),
            is_goal_event=goal_hit,
        )

        with self.lock:
            self.history.append(point)
            if goal_hit:
                self.goal_events.append(now)


        logger.debug(
            "Batch: %d tweets | avg score: %.3f | goal: %s",
            len(batch), avg_score, goal_hit,                    
        )

    # ---Inference----------------------------------------
    
    def _preprocess(self, text: str) -> str:
        """Minimal cleaning: replace URLs and @mentions (as the model card suggests)."""
        text = re.sub(r"http\S+", "http", text)
        text = re.sub(r"@\w+", "@user", text)
        return text
    
    def _score_texts(self, texts: List[str]) -> List[float]:
        cleaned = [self._preprocess(t) for t in texts]
        scores = []
        for i in range(0, len(cleaned), BATCH_SIZE):
            chunk = cleaned[i:i+BATCH_SIZE]
            enc = self.tokenizer(
                chunk,
                return_tensors="pt",
                truncation=True,
                padding=True,
                max_length=128,
            )
            with torch.no_grad():
                logits = self.model(**enc).logits
            probs = F.softmax(logits, dim=-1).numpy()
            # neg=-1, neu=0, pos=+1
            for row in probs:
                scores.append(float(-row[0] + row[2]))
        return scores
    
    # ---Goal detection----------------------------------

    def _detect_goal(self, texts: List[str]) -> bool:
        """
        Returns True if more than 25% of tweets in this batch contain
        goal-related keywords — a rough proxy for a real-time goal event.
        """
        hits = sum(
            1 for t in texts
            if any(kw in t.lower() for kw in GOAL_KEYWORDS)
        )
        return hits / len(texts) > 0.25
    
# -- Convenience singleton factory ----------------------------------

_analyser_instance: Optional[SentimentAnalyser] = None

def get_analyser(queue: Optional[collections.deque] = None, **kwargs) -> SentimentAnalyser:
    """ Return the module-level singleton analyser.
    Pass *queue* on first call to initialise it.  Subsequent calls ignore *queue* and return the same instance.
    """
    global _analyser
    if _analyser is None:
        if queue is None:
            raise ValueError("Pass the tweet queue on first call to get_analyser().")
        _analyser = SentimentAnalyser(queue, **kwargs)
    return _analyser
