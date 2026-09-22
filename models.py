from dataclasses import dataclass
from datetime import datetime
from typing import Literal

Venue = Literal["polymarket", "kalshi"]
Outcome = Literal["yes", "no"]


@dataclass
class OrderBookLevel:
    price: float
    size: float


@dataclass
class NormalizedBook:
    venue: Venue
    outcome: Outcome
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    timestamp: datetime


@dataclass
class MarketSnapshot:
    venue: Venue
    external_market_id: str
    yes_book: NormalizedBook
    no_book: NormalizedBook
    timestamp: datetime
    label: str = ""
