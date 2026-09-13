from typing import Any


class FetchBatch(list):
    """List-compatible fetch result with completeness and per-source health."""

    def __init__(self, rows=(), *, complete=True, sources=None, rejected_count=0):
        super().__init__(rows)
        self.complete = complete
        self.sources: list[dict[str, Any]] = sources or []
        self.rejected_count = rejected_count
