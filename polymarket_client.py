import json
from datetime import datetime, timezone

import requests

from models import MarketSnapshot, NormalizedBook, OrderBookLevel, Outcome

GAMMA_URL = "https://gamma-api.polymarket.com"
CLOB_URL = "https://clob.polymarket.com"
TIMEOUT_SECONDS = 10


def _get_market_metadata(slug: str) -> dict:
    resp = requests.get(f"{GAMMA_URL}/markets/slug/{slug}", timeout=TIMEOUT_SECONDS)
    resp.raise_for_status()
    return resp.json()


def _parse_levels(raw_levels: list[dict]) -> list[OrderBookLevel]:
    return [OrderBookLevel(price=float(lvl["price"]), size=float(lvl["size"])) for lvl in raw_levels]


def _fetch_book(token_id: str, outcome: Outcome) -> NormalizedBook:
    resp = requests.get(f"{CLOB_URL}/book", params={"token_id": token_id}, timeout=TIMEOUT_SECONDS)
    resp.raise_for_status()
    raw = resp.json()
    return NormalizedBook(
        venue="polymarket",
        outcome=outcome,
        # The live API returns both sides worst-first, contrary to its docs, so sort explicitly.
        bids=sorted(_parse_levels(raw["bids"]), key=lambda l: l.price, reverse=True),
        asks=sorted(_parse_levels(raw["asks"]), key=lambda l: l.price),
        timestamp=datetime.fromtimestamp(int(raw["timestamp"]) / 1000, tz=timezone.utc),
    )


def fetch_market_snapshot(slug: str) -> MarketSnapshot:
    started_at = datetime.now(timezone.utc)
    meta = _get_market_metadata(slug)

    # Gamma returns these two fields as JSON-encoded strings, not arrays.
    outcomes = json.loads(meta["outcomes"])
    token_ids = json.loads(meta["clobTokenIds"])
    if len(outcomes) != 2 or len(token_ids) != 2:
        raise ValueError(f"Expected a two-outcome market, got outcomes={outcomes}")

    # First outcome -> "yes", second -> "no"; real names are kept in the label.
    yes_book = _fetch_book(token_ids[0], "yes")
    no_book = _fetch_book(token_ids[1], "no")

    return MarketSnapshot(
        venue="polymarket",
        external_market_id=meta["conditionId"],
        yes_book=yes_book,
        no_book=no_book,
        timestamp=started_at,
        label=f"{meta['question']} (yes={outcomes[0]}, no={outcomes[1]})",
    )


if __name__ == "__main__":
    snap = fetch_market_snapshot("nba-stephen-curry-to-leave-warriors")
    print(snap.label, snap.external_market_id, snap.timestamp, sep="\n")
    for book in (snap.yes_book, snap.no_book):
        print(f"\n{book.outcome.upper()} book @ {book.timestamp} ({len(book.bids)} bids, {len(book.asks)} asks)")
        print("  best bid:", book.bids[0] if book.bids else None)
        print("  best ask:", book.asks[0] if book.asks else None)
    if snap.yes_book.asks and snap.no_book.asks:
        print("\nyes_ask + no_ask =", round(snap.yes_book.asks[0].price + snap.no_book.asks[0].price, 4))
