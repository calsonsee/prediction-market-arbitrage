import json
from datetime import datetime, timezone
from pathlib import Path

from models import MarketSnapshot, NormalizedBook, OrderBookLevel, Outcome

SAMPLE_PATH = Path(__file__).parent / "mock_data" / "kalshi_orderbook_sample.json"


def _parse_bids(raw_levels: list[list[str]]) -> list[OrderBookLevel]:
    levels = [OrderBookLevel(price=float(p), size=float(s)) for p, s in raw_levels]
    return sorted(levels, key=lambda l: l.price, reverse=True)


def _asks_from_opposite_bids(opposite_bids: list[OrderBookLevel]) -> list[OrderBookLevel]:
    # A bid for one side at price p is an ask for the other side at 1 - p (same size).
    asks = [OrderBookLevel(price=round(1 - b.price, 4), size=b.size) for b in opposite_bids]
    return sorted(asks, key=lambda l: l.price)


def snapshot_from_orderbook(ticker: str, raw: dict, label: str = "") -> MarketSnapshot:
    fetched_at = datetime.now(timezone.utc)
    book = raw["orderbook_fp"]
    yes_bids = _parse_bids(book["yes_dollars"])
    no_bids = _parse_bids(book["no_dollars"])

    def make_book(outcome: Outcome, bids: list[OrderBookLevel], opposite_bids: list[OrderBookLevel]) -> NormalizedBook:
        return NormalizedBook(
            venue="kalshi",
            outcome=outcome,
            bids=bids,
            asks=_asks_from_opposite_bids(opposite_bids),
            timestamp=fetched_at,
        )

    return MarketSnapshot(
        venue="kalshi",
        external_market_id=ticker,
        yes_book=make_book("yes", yes_bids, no_bids),
        no_book=make_book("no", no_bids, yes_bids),
        timestamp=fetched_at,
        label=label,
    )


def load_sample_snapshot(path: Path = SAMPLE_PATH) -> MarketSnapshot:
    raw = json.loads(path.read_text())
    return snapshot_from_orderbook("MOCK-NBA-GAME-TICKER", raw, label="Mock NBA game (sample data)")


if __name__ == "__main__":
    snap = load_sample_snapshot()
    print(snap.label, snap.external_market_id, snap.timestamp, sep="\n")
    for book in (snap.yes_book, snap.no_book):
        print(f"\n{book.outcome.upper()} book ({len(book.bids)} bids, {len(book.asks)} asks)")
        print("  bids:", [(l.price, l.size) for l in book.bids])
        print("  asks:", [(l.price, l.size) for l in book.asks])
    print("\nyes_ask + no_bid =", round(snap.yes_book.asks[0].price + snap.no_book.bids[0].price, 4))
    print("yes_ask + no_ask =", round(snap.yes_book.asks[0].price + snap.no_book.asks[0].price, 4))
