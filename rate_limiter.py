# rate_limiter.py
"""
Local, in-process rate limiter for the Gemini API free tier.

This file did not exist in the original repo even though agent_graph.py
imported it directly:

    from rate_limiter import api_rate_limiter, RateLimitError

That caused a guaranteed ModuleNotFoundError on startup. This implementation
tracks RPM / RPD / TPM per model bucket so the free tier's separate limits
for gemini-2.5-flash and gemini-2.5-flash-lite are respected independently.

Free-tier numbers change periodically — verify current values at
https://ai.google.dev/gemini-api/docs/rate-limits and adjust the constants
in agent_graph.py / evaluator.py if Google changes them.
"""

import time
import threading
from collections import deque


class RateLimitError(Exception):
    """Raised when the local guard predicts the call would hit a 429."""
    pass


class ApiRateLimiter:
    """
    Sliding-window limiter for Requests-Per-Minute (RPM),
    Requests-Per-Day (RPD), and Tokens-Per-Minute (TPM).
    Thread-safe — Streamlit can serve multiple sessions concurrently.
    """

    def __init__(self, name: str, rpm: int, rpd: int, tpm: int):
        self.name = name
        self.rpm, self.rpd, self.tpm = rpm, rpd, tpm
        self._req_times = deque()       # request timestamps, rolling 60s
        self._day_times = deque()       # request timestamps, rolling 24h
        self._token_log = deque()       # (timestamp, tokens), rolling 60s
        self._lock = threading.Lock()

    def _prune(self, now: float):
        while self._req_times and now - self._req_times[0] > 60:
            self._req_times.popleft()
        while self._day_times and now - self._day_times[0] > 86400:
            self._day_times.popleft()
        while self._token_log and now - self._token_log[0][0] > 60:
            self._token_log.popleft()

    def acquire(self, input_tokens: int, output_buffer: int = 1000):
        """
        Reserve capacity for one call. Raises RateLimitError if the daily
        quota is gone (no point retrying), or a generic Exception carrying
        "429"/"RESOURCE_EXHAUSTED" if the per-minute window is full (the
        retry_with_backoff decorator in agent_graph.py knows to back off
        and retry on that signal).
        """
        with self._lock:
            now = time.time()
            self._prune(now)

            if len(self._day_times) >= self.rpd:
                raise RateLimitError(
                    f"[{self.name}] Daily request quota (RPD={self.rpd}) exhausted."
                )

            current_tpm = sum(t for _, t in self._token_log) + input_tokens + output_buffer
            if len(self._req_times) >= self.rpm or current_tpm > self.tpm:
                raise Exception(
                    f"429 RESOURCE_EXHAUSTED: local rate guard tripped for '{self.name}' "
                    f"(RPM {len(self._req_times)}/{self.rpm}, TPM ~{current_tpm}/{self.tpm})"
                )

            self._req_times.append(now)
            self._day_times.append(now)
            self._token_log.append((now, input_tokens + output_buffer))

    def get_status(self) -> str:
        with self._lock:
            now = time.time()
            self._prune(now)
            tpm_used = sum(t for _, t in self._token_log)
            return (f"[{self.name}] RPM {len(self._req_times)}/{self.rpm} | "
                    f"RPD {len(self._day_times)}/{self.rpd} | "
                    f"TPM ~{tpm_used}/{self.tpm}")


# ── Free-tier buckets ─────────────────────────────────────────────────────
# Conservative defaults below the documented free-tier ceilings, leaving
# headroom for clock-skew / burst. Tune via env vars if your project's
# AI Studio quota panel shows different numbers.
import os

api_rate_limiter = ApiRateLimiter(
    name="gemini-2.5-flash",
    rpm=int(os.getenv("GEMINI_FLASH_RPM", 4)),
    rpd=int(os.getenv("GEMINI_FLASH_RPD", 18)),
    tpm=int(os.getenv("GEMINI_FLASH_TPM", 200_000)),
)

lite_rate_limiter = ApiRateLimiter(
    name="gemini-2.5-flash-lite",
    rpm=int(os.getenv("GEMINI_LITE_RPM", 4)),
    rpd=int(os.getenv("GEMINI_LITE_RPD", 18)),
    tpm=int(os.getenv("GEMINI_LITE_TPM", 200_000)),
)