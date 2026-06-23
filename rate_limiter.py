import time
import threading
from collections import deque
from typing import Optional

class RateLimiter:
    """
    Token bucket rate limiter that tracks requests per minute, per day, and tokens per minute.
    Configured for Google Gemini Free Tier limits:
    - 5 RPM (requests per minute)
    - 20 RPD (requests per day)  
    - 250,000 TPM (tokens per minute)
    """
    
    def __init__(self, rpm: int = 4, rpd: int = 15, tpm: int = 200000):
        # Set limits slightly below Google's to be safe
        self.rpm_limit = rpm  # 4 instead of 5
        self.rpd_limit = rpd  # 15 instead of 20
        self.tpm_limit = tpm  # 200k instead of 250k
        
        self.minute_window = 60
        self.day_window = 86400
        
        self.requests_minute = deque()
        self.requests_day = deque()
        self.tokens_minute = deque()
        
        self.lock = threading.Lock()
    
    def _cleanup_old_entries(self, current_time: float):
        """Remove entries older than the time windows."""
        minute_cutoff = current_time - self.minute_window
        day_cutoff = current_time - self.day_window
        
        while self.requests_minute and self.requests_minute[0] < minute_cutoff:
            self.requests_minute.popleft()
        
        while self.requests_day and self.requests_day[0] < day_cutoff:
            self.requests_day.popleft()
        
        while self.tokens_minute and self.tokens_minute[0][0] < minute_cutoff:
            self.tokens_minute.popleft()
    
    def acquire(self, tokens: int = 1, output_buffer: int = 1000) -> bool:
        """
        Attempt to acquire permission to make a request.
        Returns True if allowed, raises RateLimitError if limit exceeded.
        """
        with self.lock:
            current_time = time.time()
            self._cleanup_old_entries(current_time)
            
            # Check RPM limit
            if len(self.requests_minute) >= self.rpm_limit:
                oldest_request = self.requests_minute[0]
                wait_time = oldest_request + self.minute_window - current_time
                raise RateLimitError(
                    f"Rate limit exceeded: {len(self.requests_minute)}/{self.rpm_limit} requests per minute. "
                    f"Wait {wait_time:.1f} seconds."
                )
            
            # Check RPD limit
            if len(self.requests_day) >= self.rpd_limit:
                oldest_request = self.requests_day[0]
                wait_time = oldest_request + self.day_window - current_time
                raise RateLimitError(
                    f"Daily limit exceeded: {len(self.requests_day)}/{self.rpd_limit} requests per day. "
                    f"Wait {wait_time/3600:.1f} hours."
                )
            
            # Check TPM limit
            total_tokens = sum(t for _, t in self.tokens_minute) + tokens + output_buffer
            if total_tokens > self.tpm_limit:
                raise RateLimitError(
                    f"Token limit exceeded: {total_tokens}/{self.tpm_limit} tokens per minute."
                )
            
            # Record this request
            self.requests_minute.append(current_time)
            self.requests_day.append(current_time)
            self.tokens_minute.append((current_time, tokens + output_buffer))
            
            return True
    
    def get_status(self) -> dict:
        """Returns current usage statistics."""
        with self.lock:
            current_time = time.time()
            self._cleanup_old_entries(current_time)
            
            total_tokens = sum(t for _, t in self.tokens_minute)
            
            return {
                "rpm": f"{len(self.requests_minute)}/{self.rpm_limit}",
                "rpd": f"{len(self.requests_day)}/{self.rpd_limit}",
                "tpm": f"{total_tokens}/{self.tpm_limit}",
                "remaining_requests_minute": self.rpm_limit - len(self.requests_minute),
                "remaining_requests_day": self.rpd_limit - len(self.requests_day),
            }

class RateLimitError(Exception):
    """Raised when rate limit is exceeded."""
    pass

# Global rate limiter instance - configured for FREE TIER
api_rate_limiter = RateLimiter(rpm=4, rpd=15, tpm=200000)