import re
import time
import logging
import collections
from dataclasses import dataclass
from threading import Lock
from typing import List, Optional

import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch.nn.functional as F

logger = logging.getLogger(__name__)

MODEL_NAME = "cardiffnlp/twitter-roberta-base-sentiment-latest"
GOAL_KEYWORDS = frozenset(["goal", "scores", "scored", "goaaaal", "⚽", "gooool"])
BATCH_SIZE = 16


@dataclass
class SentimentPoint:
    timestamp: float
    score: float
    tweet_count: int
    is_goal_event: bool = False


class SentimentAnalyser:
    def __init__(self, queue, window_seconds=30, history_minutes=90):
        self.queue = queue
        self.window_seconds = window_seconds
        self.history_minutes = history_minutes
        self._lock = Lock()
        self._history = []
        self._goal_events = []

        logger.info("Loading model %s ...", MODEL_NAME)
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        self.model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
        self.model.eval()
        logger.info("Model ready.")

    def get_history(self):
        with self._lock:
            cutoff = time.time() - self.history_minutes * 60
            return [p for p in self._history if p.timestamp >= cutoff]

    def get_goal_events(self):
        with self._lock:
            cutoff = time.time() - self.history_minutes * 60
            return [t for t in self._goal_events if t >= cutoff]

    def process_batch(self):
        now = time.time()
        batch = []
        while self.queue:
            try:
                batch.append(self.queue.popleft())
            except IndexError:
                break

        if not batch:
            return

        texts = [item["text"] for item in batch]
        scores = self._score_texts(texts)
        avg_score = sum(scores) / len(scores)
        goal_hit = self._detect_goal(texts)

        point = SentimentPoint(
            timestamp=now,
            score=round(avg_score, 4),
            tweet_count=len(batch),
            is_goal_event=goal_hit,
        )

        with self._lock:
            self._history.append(point)
            if goal_hit:
                self._goal_events.append(now)

    def _preprocess(self, text):
        text = re.sub(r"http\S+", "http", text)
        text = re.sub(r"@\w+", "@user", text)
        return text

    def _score_texts(self, texts):
        cleaned = [self._preprocess(t) for t in texts]
        scores = []
        for i in range(0, len(cleaned), BATCH_SIZE):
            chunk = cleaned[i:i + BATCH_SIZE]
            enc = self.tokenizer(chunk, return_tensors="pt", truncation=True, padding=True, max_length=128)
            with torch.no_grad():
                logits = self.model(**enc).logits
            probs = F.softmax(logits, dim=-1).numpy()
            for row in probs:
                scores.append(float(-row[0] + row[2]))
        return scores

    def _detect_goal(self, texts):
        hits = sum(1 for t in texts if any(kw in t.lower() for kw in GOAL_KEYWORDS))
        return hits / len(texts) > 0.25


_analyser_instance = None


def get_analyser(queue=None, **kwargs):
    global _analyser_instance
    if _analyser_instance is None:
        if queue is None:
            raise ValueError("Pass the tweet queue on first call to get_analyser().")
        _analyser_instance = SentimentAnalyser(queue, **kwargs)
    return _analyser_instance