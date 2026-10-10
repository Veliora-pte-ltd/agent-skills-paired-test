"""Order helpers."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Order:
    id: int
    customer_id: int
    total_minor: int
    currency: str = "GBP"
    status: str = "pending"

    def total_display(self) -> str:
        pounds, pence = divmod(self.total_minor, 100)
        return f"{self.currency} {pounds}.{pence:02d}"


def order_total(line_amounts_minor: list[int]) -> int:
    """Sum line amounts (in minor units, e.g. pence)."""
    return sum(line_amounts_minor)


# Deprecated alias kept for 1.x callers.
sum_lines = order_total
