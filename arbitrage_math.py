import math
from dataclasses import dataclass

from models import MarketSnapshot, OrderBookLevel, Venue


@dataclass(frozen=True)
class FeeModel:
    rate: float
    round_up_to_cent: bool = False

    def fee(self, weighted_p_1mp: float) -> float:
        """Fee for an order, given sum(size * p * (1 - p)) over the filled levels."""
        raw = self.rate * weighted_p_1mp
        return math.ceil(round(raw * 100, 9)) / 100 if self.round_up_to_cent else raw


# Taker rates as of Sep 2026 (Polymarket sports 0.05, Kalshi 0.07). Verify before trading real money.
DEFAULT_FEES: dict[Venue, FeeModel] = {
    "polymarket": FeeModel(rate=0.05),
    "kalshi": FeeModel(rate=0.07, round_up_to_cent=True),
}


@dataclass
class Opportunity:
    kind: str  # "in-venue" or "cross-venue"
    yes_venue: Venue
    no_venue: Venue
    top_of_book_gross_edge: float  # 1 - (best YES ask + best NO ask), before fees and depth
    quantity: float  # pairs (YES+NO) worth taking, walking the book
    cost: float  # total price paid for both legs, excluding fees
    fees: float
    net_profit: float  # quantity * $1 payout - cost - fees

    @property
    def is_profitable(self) -> bool:
        return self.quantity > 0 and self.net_profit > 0

    @property
    def roi(self) -> float:
        capital = self.cost + self.fees
        return self.net_profit / capital if capital else 0.0


def _pair_fee_per_share(p: float, fee_model: FeeModel) -> float:
    # Rounding is ignored here; it is applied once per order at the end.
    return fee_model.rate * p * (1 - p)


def _walk_books(
    yes_asks: list[OrderBookLevel], no_asks: list[OrderBookLevel], yes_fee: FeeModel, no_fee: FeeModel
) -> tuple[float, float, float, float]:
    """Take (YES, NO) pairs level by level while each marginal pair is net-profitable.

    Returns (quantity, cost, yes_fee_weight, no_fee_weight) where the weights are sum(size * p * (1 - p)).
    """
    yes_left = [[l.price, l.size] for l in yes_asks]
    no_left = [[l.price, l.size] for l in no_asks]
    i = j = 0
    qty = cost = yes_w = no_w = 0.0

    while i < len(yes_left) and j < len(no_left):
        (py, sy), (pn, sn) = yes_left[i], no_left[j]
        marginal = 1 - py - pn - _pair_fee_per_share(py, yes_fee) - _pair_fee_per_share(pn, no_fee)
        if marginal <= 0:
            break
        take = min(sy, sn)
        qty += take
        cost += take * (py + pn)
        yes_w += take * py * (1 - py)
        no_w += take * pn * (1 - pn)
        yes_left[i][1] -= take
        no_left[j][1] -= take
        if yes_left[i][1] <= 1e-12:
            i += 1
        if no_left[j][1] <= 1e-12:
            j += 1
    return qty, cost, yes_w, no_w


def evaluate_pair(
    yes_snap: MarketSnapshot, no_snap: MarketSnapshot, fees: dict[Venue, FeeModel] = DEFAULT_FEES
) -> Opportunity:
    """Buy YES from yes_snap and NO from no_snap; the snapshots may be the same venue."""
    yes_asks, no_asks = yes_snap.yes_book.asks, no_snap.no_book.asks
    yes_fee, no_fee = fees[yes_snap.venue], fees[no_snap.venue]

    top_edge = 1 - (yes_asks[0].price + no_asks[0].price) if yes_asks and no_asks else float("nan")
    qty, cost, yes_w, no_w = _walk_books(yes_asks, no_asks, yes_fee, no_fee)
    total_fees = yes_fee.fee(yes_w) + no_fee.fee(no_w) if qty else 0.0

    return Opportunity(
        kind="in-venue" if yes_snap.venue == no_snap.venue else "cross-venue",
        yes_venue=yes_snap.venue,
        no_venue=no_snap.venue,
        top_of_book_gross_edge=top_edge,
        quantity=qty,
        cost=cost,
        fees=total_fees,
        net_profit=qty - cost - total_fees,
    )


def scan(
    polymarket: MarketSnapshot, kalshi: MarketSnapshot, fees: dict[Venue, FeeModel] = DEFAULT_FEES
) -> list[Opportunity]:
    """Evaluate all four YES/NO venue combinations, best net profit first.

    Cross-venue results assume YES means the same outcome on both venues.
    """
    combos = [(polymarket, polymarket), (kalshi, kalshi), (polymarket, kalshi), (kalshi, polymarket)]
    results = [evaluate_pair(y, n, fees) for y, n in combos]
    return sorted(results, key=lambda o: o.net_profit, reverse=True)


if __name__ == "__main__":
    from datetime import datetime, timezone

    from kalshi_client import load_sample_snapshot
    from models import NormalizedBook

    now = datetime.now(timezone.utc)
    lv = OrderBookLevel
    # Hand-built Polymarket book, priced to create a cross-venue gap against the Kalshi mock data.
    pm = MarketSnapshot(
        venue="polymarket",
        external_market_id="HAND-BUILT",
        yes_book=NormalizedBook("polymarket", "yes", [], [lv(0.50, 100), lv(0.53, 200)], now),
        no_book=NormalizedBook("polymarket", "no", [], [lv(0.52, 150), lv(0.55, 300)], now),
        timestamp=now,
        label="Hand-built Polymarket book",
    )
    kal = load_sample_snapshot()

    for o in scan(pm, kal):
        print(
            f"{o.kind:<12} YES@{o.yes_venue:<10} NO@{o.no_venue:<10} "
            f"top-edge={o.top_of_book_gross_edge:+.4f} qty={o.quantity:>6.1f} "
            f"cost={o.cost:>7.2f} fees={o.fees:>5.2f} net={o.net_profit:+7.2f} roi={o.roi:+.2%} "
            f"{'<-- PROFITABLE' if o.is_profitable else ''}"
        )
