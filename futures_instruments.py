"""
Futures instrument catalog and Yahoo Finance price fetching.

Each instrument maps to its contract multiplier ($/point) and the
Yahoo Finance continuous-contract ticker used for price lookups.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import yfinance as yf


@dataclass(frozen=True)
class FuturesInstrument:
    symbol: str
    name: str
    multiplier: float
    yahoo_ticker: str
    exchange: str
    category: str


# ── Instrument Catalog ─────────────────────────────────────────────────

INSTRUMENTS: dict[str, FuturesInstrument] = {}


def _add(symbol: str, name: str, multiplier: float, yahoo: str, exchange: str, category: str):
    INSTRUMENTS[symbol] = FuturesInstrument(symbol, name, multiplier, yahoo, exchange, category)


# Equity Index — Standard
_add("ES",  "E-mini S&P 500",           50.0,    "ES=F",  "CME",  "Equity Index")
_add("NQ",  "E-mini Nasdaq 100",        20.0,    "NQ=F",  "CME",  "Equity Index")
_add("YM",  "E-mini Dow ($5)",           5.0,    "YM=F",  "CBOT", "Equity Index")
_add("RTY", "E-mini Russell 2000",      50.0,    "RTY=F", "CME",  "Equity Index")
_add("EMD", "E-mini S&P MidCap 400",   100.0,    "EMD=F", "CME",  "Equity Index")

# Equity Index — Micro
_add("MES", "Micro E-mini S&P 500",      5.0,   "MES=F", "CME",  "Micro Equity Index")
_add("MNQ", "Micro E-mini Nasdaq 100",   2.0,   "MNQ=F", "CME",  "Micro Equity Index")
_add("MYM", "Micro E-mini Dow ($0.50)",  0.5,   "MYM=F", "CBOT", "Micro Equity Index")
_add("M2K", "Micro E-mini Russell 2000", 5.0,   "M2K=F", "CME",  "Micro Equity Index")

# Energy — Standard
_add("CL",  "Crude Oil (WTI)",        1000.0,    "CL=F",  "NYMEX", "Energy")
_add("NG",  "Natural Gas",           10000.0,    "NG=F",  "NYMEX", "Energy")
_add("RB",  "RBOB Gasoline",         42000.0,    "RB=F",  "NYMEX", "Energy")
_add("HO",  "Heating Oil",           42000.0,    "HO=F",  "NYMEX", "Energy")

# Energy — Micro
_add("MCL", "Micro WTI Crude Oil",     100.0,   "MCL=F", "NYMEX", "Micro Energy")
_add("MNG", "Micro Natural Gas",      1000.0,   "MNG=F", "NYMEX", "Micro Energy")

# Metals — Standard
_add("GC",  "Gold",                     100.0,   "GC=F",  "COMEX", "Metals")
_add("SI",  "Silver",                  5000.0,   "SI=F",  "COMEX", "Metals")
_add("HG",  "Copper",                25000.0,    "HG=F",  "COMEX", "Metals")
_add("PL",  "Platinum",                 50.0,    "PL=F",  "NYMEX", "Metals")
_add("PA",  "Palladium",               100.0,    "PA=F",  "NYMEX", "Metals")

# Metals — Micro
_add("MGC", "Micro Gold",               10.0,   "MGC=F", "COMEX", "Micro Metals")
_add("SIL", "Micro Silver",           1000.0,   "SIL=F", "COMEX", "Micro Metals")

# Treasuries
_add("ZB",  "30-Year Treasury Bond",  1000.0,   "ZB=F",  "CBOT", "Treasuries")
_add("ZN",  "10-Year Treasury Note",  1000.0,   "ZN=F",  "CBOT", "Treasuries")
_add("ZF",  "5-Year Treasury Note",   1000.0,   "ZF=F",  "CBOT", "Treasuries")
_add("ZT",  "2-Year Treasury Note",   2000.0,   "ZT=F",  "CBOT", "Treasuries")
_add("UB",  "Ultra Treasury Bond",    1000.0,   "UB=F",  "CBOT", "Treasuries")

# Currencies
_add("6E",  "Euro FX",              125000.0,    "6E=F",  "CME", "Currencies")
_add("6J",  "Japanese Yen",       12500000.0,    "6J=F",  "CME", "Currencies")
_add("6B",  "British Pound",         62500.0,    "6B=F",  "CME", "Currencies")
_add("6A",  "Australian Dollar",    100000.0,    "6A=F",  "CME", "Currencies")
_add("6C",  "Canadian Dollar",      100000.0,    "6C=F",  "CME", "Currencies")
_add("6S",  "Swiss Franc",          125000.0,    "6S=F",  "CME", "Currencies")

# Micro Currencies
_add("M6E", "Micro Euro FX",         12500.0,   "M6E=F", "CME", "Micro Currencies")
_add("M6A", "Micro AUD/USD",         10000.0,   "M6A=F", "CME", "Micro Currencies")

# Grains
_add("ZC",  "Corn",                     50.0,   "ZC=F",  "CBOT", "Grains")
_add("ZS",  "Soybeans",                 50.0,   "ZS=F",  "CBOT", "Grains")
_add("ZW",  "Wheat",                    50.0,   "ZW=F",  "CBOT", "Grains")
_add("ZM",  "Soybean Meal",            100.0,   "ZM=F",  "CBOT", "Grains")
_add("ZL",  "Soybean Oil",             600.0,   "ZL=F",  "CBOT", "Grains")

# Softs / Livestock
_add("KC",  "Coffee",                37500.0,   "KC=F",  "ICE",  "Softs")
_add("SB",  "Sugar #11",              1120.0,   "SB=F",  "ICE",  "Softs")
_add("CT",  "Cotton",                50000.0,   "CT=F",  "ICE",  "Softs")
_add("CC",  "Cocoa",                    10.0,   "CC=F",  "ICE",  "Softs")
_add("LE",  "Live Cattle",             400.0,   "LE=F",  "CME",  "Livestock")
_add("HE",  "Lean Hogs",               400.0,   "HE=F",  "CME",  "Livestock")

# VIX
_add("VX",  "VIX Futures",            1000.0,   "VX=F",  "CFE",  "Volatility")


def get_instrument(symbol: str) -> Optional[FuturesInstrument]:
    return INSTRUMENTS.get(symbol.upper())


def instrument_display_list() -> list[str]:
    """Return formatted display strings for use in a dropdown, grouped by category."""
    items = []
    for sym, inst in INSTRUMENTS.items():
        items.append(f"{sym} — {inst.name} (${inst.multiplier:,.2f}/pt)")
    return items


def symbol_from_display(display: str) -> str:
    """Extract the symbol from a display string like 'ES — E-mini S&P 500 ($50.00/pt)'."""
    return display.split(" — ")[0].strip()


# ── Yahoo Finance Price Fetching ───────────────────────────────────────

def fetch_close_price(yahoo_ticker: str, target_date: date) -> Optional[float]:
    """
    Fetch the closing price for a futures contract on or near a target date.

    Yahoo Finance may not have data on weekends/holidays, so we look at a
    window around the target date and return the closest available close.
    """
    # Fetch a window: 5 days before through 1 day after to handle weekends/holidays
    start = target_date - timedelta(days=5)
    end = target_date + timedelta(days=2)

    try:
        ticker = yf.Ticker(yahoo_ticker)
        hist = ticker.history(start=str(start), end=str(end))

        if hist.empty:
            return None

        # Normalize index to date-only for comparison
        hist.index = hist.index.tz_localize(None).normalize()

        target_ts = pd.Timestamp(target_date)

        # Exact match first
        if target_ts in hist.index:
            return float(hist.loc[target_ts, "Close"])

        # Otherwise return the closest date that is <= target_date
        before = hist[hist.index <= target_ts]
        if not before.empty:
            return float(before.iloc[-1]["Close"])

        # Fallback: closest date at all
        return float(hist.iloc[-1]["Close"])

    except Exception:
        return None


def fetch_price_for_instrument(symbol: str, target_date: date) -> Optional[float]:
    """Fetch close price for a known instrument symbol on a given date."""
    inst = get_instrument(symbol)
    if inst is None:
        return None
    return fetch_close_price(inst.yahoo_ticker, target_date)


# Need pandas for Timestamp usage in fetch_close_price
import pandas as pd
