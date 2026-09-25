import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pandas as pd
import requests
import streamlit as st

from arbitrage_math import FeeModel, Opportunity, evaluate_pair, scan, size_position
from kalshi_client import load_sample_snapshot
from models import MarketSnapshot, NormalizedBook, OrderBookLevel
from polymarket_client import GAMMA_URL, TIMEOUT_SECONDS, fetch_market_snapshot

st.set_page_config(page_title="ARB TERMINAL", page_icon="📈", layout="wide")

st.markdown(
    """
    <style>
    .block-container {padding-top: 2rem;}
    h1, h2, h3 {letter-spacing: 0.04em;}
    div[data-testid="stMetric"] {
        background: #121821; border: 1px solid #1f2a37; border-left: 3px solid #00d68f;
        border-radius: 4px; padding: 14px 18px;
    }
    div[data-testid="stMetricLabel"] p {text-transform: uppercase; letter-spacing: 0.08em; color: #7d8b99;}
    div[data-testid="stMetricValue"] {color: #00d68f;}
    .clock {text-align: right; color: #7d8b99; font-size: 0.9rem; padding-top: 0.6rem;}
    .clock b {color: #d7dee7; font-size: 1.3rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=10, show_spinner=False)
def fetch_live_snapshots(limit: int, per_event: int = 3) -> tuple[list[MarketSnapshot], int]:
    """Pull live two-outcome NBA markets from Polymarket. Returns (snapshots, failed_count)."""
    events = requests.get(
        f"{GAMMA_URL}/events",
        params={"active": "true", "closed": "false", "tag_slug": "nba", "limit": 100,
                "order": "volume24hr", "ascending": "false"},
        timeout=TIMEOUT_SECONDS,
    ).json()

    slugs: list[str] = []
    for event in events:
        taken = 0
        for m in event.get("markets", []):
            two_outcomes = len(json.loads(m.get("outcomes") or "[]")) == 2
            if two_outcomes and m.get("enableOrderBook") and m.get("active") and not m.get("closed") \
                    and m.get("clobTokenIds") and taken < per_event:
                slugs.append(m["slug"])
                taken += 1
    slugs = slugs[:limit]

    def safe_fetch(slug: str) -> MarketSnapshot | None:
        try:
            return fetch_market_snapshot(slug)
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(safe_fetch, slugs))
    snaps = [s for s in results if s is not None]
    return snaps, len(results) - len(snaps)


def demo_polymarket_snapshot() -> MarketSnapshot:
    now = datetime.now(timezone.utc)
    lv = OrderBookLevel
    return MarketSnapshot(
        venue="polymarket",
        external_market_id="HAND-BUILT",
        yes_book=NormalizedBook("polymarket", "yes", [], [lv(0.50, 100), lv(0.53, 200)], now),
        no_book=NormalizedBook("polymarket", "no", [], [lv(0.52, 150), lv(0.55, 300)], now),
        timestamp=now,
        label="hand-built Polymarket book",
    )


with st.sidebar:
    st.header("PARAMETERS")
    st.subheader("Filters")
    min_edge = st.slider("Min net edge (%)", 0.0, 10.0, 0.5, 0.1, help="Hide opportunities with net ROI below this.")
    show_all = st.checkbox("Show non-profitable rows", value=False)
    st.subheader("Sizing")
    bankroll = st.number_input("Bankroll ($)", min_value=10.0, value=1000.0, step=100.0)
    kelly_mult = st.slider("Kelly fraction", 0.05, 1.0, 0.25, 0.05, help="1.0 = full Kelly; lower is safer.")
    max_frac = st.slider("Max bankroll per trade (%)", 1, 100, 25) / 100
    st.subheader("Execution risk")
    leg_fail = st.slider("Leg-in failure probability (%)", 0.0, 60.0, 5.0, 0.5) / 100
    unwind = st.slider("Unwind loss on failed leg (%)", 0.0, 100.0, 10.0, 1.0) / 100
    st.subheader("Fees (taker)")
    pm_fee = st.number_input("Polymarket rate", 0.0, 0.2, 0.05, 0.01, format="%.2f")
    kal_fee = st.number_input("Kalshi rate", 0.0, 0.2, 0.07, 0.01, format="%.2f")
    st.subheader("Data")
    n_markets = st.slider("Live markets to scan", 1, 30, 8)
    include_demo = st.checkbox("Include DEMO cross-venue data", value=True,
                               help="Hand-built Polymarket book vs. the Kalshi mock file. Not live.")
    auto = st.checkbox("Auto-refresh", value=False)
    interval = st.slider("Refresh every (s)", 10, 120, 30, disabled=not auto)

fees = {"polymarket": FeeModel(pm_fee), "kalshi": FeeModel(kal_fee, round_up_to_cent=True)}

head_l, head_r = st.columns([3, 1])
head_l.title("ARB TERMINAL")
head_l.caption("POLYMARKET × KALSHI · NBA MARKETS · PREDICTION-MARKET ARBITRAGE")


@st.fragment(run_every=1)
def clock() -> None:
    now = datetime.now(timezone.utc)
    st.markdown(f'<div class="clock">UTC<br><b>{now:%Y-%m-%d %H:%M:%S}</b></div>', unsafe_allow_html=True)


with head_r:
    clock()


def build_table() -> tuple[pd.DataFrame, int, int]:
    live, failed = fetch_live_snapshots(n_markets)
    entries: list[tuple[str, Opportunity]] = [(s.label, evaluate_pair(s, s, fees)) for s in live]
    scanned = len(live)
    if include_demo:
        demo_pm, kal = demo_polymarket_snapshot(), load_sample_snapshot()
        entries += [(f"DEMO · {o.kind} · YES@{o.yes_venue} / NO@{o.no_venue}", o) for o in scan(demo_pm, kal, fees)]
        scanned += 1

    rows = []
    for name, opp in entries:
        s = size_position(opp, bankroll, leg_fail, unwind, kelly_mult, max_frac)
        rows.append({
            "Market": name,
            "Type": opp.kind,
            "Top edge %": opp.top_of_book_gross_edge * 100,
            "Net edge %": opp.roi * 100 if opp.quantity else 0.0,
            "Net profit $": opp.net_profit,
            "Max pairs": opp.quantity,
            "Full Kelly": s.kelly_fraction,
            "Deploy %": s.applied_fraction * 100,
            "Capital $": s.capital,
            "Size (pairs)": s.pairs,
            "E[profit] $": s.expected_profit,
            "Limit": s.limited_by,
        })
    df = pd.DataFrame(rows)
    return df, scanned, failed


@st.fragment(run_every=interval if auto else None)
def dashboard() -> None:
    df, scanned, failed = build_table()
    visible = df if show_all else df[(df["Net edge %"] >= min_edge) & (df["Size (pairs)"] > 0)]
    visible = visible.sort_values("Net edge %", ascending=False)

    k1, k2, k3 = st.columns(3)
    k1.metric("Markets scanned", scanned, help="Live Polymarket markets plus the DEMO group if enabled.")
    if visible.empty:
        k2.metric("Max net edge", "—")
        k3.metric("Optimal sizing", "—")
    else:
        best = visible.iloc[0]
        k2.metric("Max net edge", f"{best['Net edge %']:.2f}%", f"${best['Net profit $']:.2f} at max depth")
        k3.metric("Optimal sizing", f"${best['Capital $']:,.2f}",
                  f"{best['Size (pairs)']:.0f} pairs · {best['Deploy %']:.1f}% of bankroll")

    st.markdown("&nbsp;")
    st.subheader("OPPORTUNITIES")
    if visible.empty:
        st.info("No opportunities above the current filters. Lower the min net edge, or tick "
                "'Show non-profitable rows' in the sidebar to see every market evaluated.")
    else:
        st.dataframe(
            visible, hide_index=True, width="stretch",
            column_config={
                "Top edge %": st.column_config.NumberColumn(format="%.2f"),
                "Net edge %": st.column_config.NumberColumn(format="%.2f"),
                "Net profit $": st.column_config.NumberColumn(format="$%.2f"),
                "Max pairs": st.column_config.NumberColumn(format="%.0f"),
                "Full Kelly": st.column_config.NumberColumn(format="%.2f"),
                "Deploy %": st.column_config.NumberColumn(format="%.1f"),
                "Capital $": st.column_config.NumberColumn(format="$%.2f"),
                "Size (pairs)": st.column_config.NumberColumn(format="%.1f"),
                "E[profit] $": st.column_config.NumberColumn(format="$%.2f"),
            },
        )
    st.caption(f"Last refresh {datetime.now(timezone.utc):%H:%M:%S} UTC · {scanned} scanned · {failed} failed to load"
               " · Kalshi data is mock (no API key)")


dashboard()
