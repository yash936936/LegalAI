import time
import threading
from datetime import datetime, timedelta
from typing import List, Tuple

class RateLimiter:
    def __init__(self, rpm: int, rpd: int, tpm: int):
        self.rpm_limit = rpm
        self.rpd_limit = rpd
        self.tpm_limit = tpm
        
        self._lock = threading.Lock()
        self._req_timestamps: List[float] = []
        self._token_timestamps: List[Tuple[float, int]] = []
        self._daily_count = 0
        self._daily_reset = self._next_midnight()

    def _next_midnight(self) -> datetime:
        now = datetime.now()
        return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    def acquire(self, estimated_input_tokens: int, estimated_output_tokens: int = 1000):
        total_est_tokens = estimated_input_tokens + estimated_output_tokens
        with self._lock:
            now = time.time()
            self._cleanup(now)

            if self._daily_count >= self.rpd_limit:
                reset_time = self._daily_reset.strftime("%I:%M %p")
                raise RateLimitError(f"🚫 Daily request limit reached. Resets at {reset_time}.")

            if len(self._req_timestamps) >= self.rpm_limit:
                oldest = self._req_timestamps[0]
                wait_sec = 60 - (now - oldest)
                if wait_sec > 0:
                    raise RateLimitError(f"⏳ RPM limit reached. Please wait {int(wait_sec)}s.")

            current_tokens = sum(t[1] for t in self._token_timestamps)
            if current_tokens + total_est_tokens > self.tpm_limit:
                raise RateLimitError("⚠️ TPM limit reached. Please try again in a minute.")

            self._req_timestamps.append(now)
            self._token_timestamps.append((now, total_est_tokens))
            self._daily_count += 1

    def _cleanup(self, now: float):
        self._req_timestamps = [t for t in self._req_timestamps if now - t < 60]
        self._token_timestamps = [(t, tok) for t, tok in self._token_timestamps if now - t < 60]
        if datetime.now() >= self._daily_reset:
            self._daily_count = 0
            self._daily_reset = self._next_midnight()

class RateLimitError(Exception):
    pass

api_rate_limiter = RateLimiter(rpm=4, rpd=18, tpm=200000)
