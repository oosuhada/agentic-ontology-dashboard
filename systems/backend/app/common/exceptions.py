"""Cross-cutting exceptions that are not owned by a business domain."""


class RateLimitExceeded(RuntimeError):
    def __init__(self, *, bucket: str, retry_after: int) -> None:
        super().__init__(f"rate limit exceeded for {bucket}")
        self.bucket = bucket
        self.retry_after = max(1, retry_after)
