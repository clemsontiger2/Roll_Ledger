"""Tests for the futures instruments catalog and price fetching."""

import pytest
from futures_instruments import (
    INSTRUMENTS,
    get_instrument,
    instrument_display_list,
    symbol_from_display,
    fetch_price_for_instrument,
)


class TestInstrumentCatalog:
    def test_es_exists(self):
        inst = get_instrument("ES")
        assert inst is not None
        assert inst.multiplier == 50.0
        assert inst.yahoo_ticker == "ES=F"
        assert inst.category == "Equity Index"

    def test_micro_es_exists(self):
        inst = get_instrument("MES")
        assert inst is not None
        assert inst.multiplier == 5.0
        assert inst.yahoo_ticker == "MES=F"
        assert inst.category == "Micro Equity Index"

    def test_micro_nq_exists(self):
        inst = get_instrument("MNQ")
        assert inst is not None
        assert inst.multiplier == 2.0

    def test_micro_gold_exists(self):
        inst = get_instrument("MGC")
        assert inst is not None
        assert inst.multiplier == 10.0

    def test_case_insensitive_lookup(self):
        assert get_instrument("es") is not None
        assert get_instrument("Es") is not None

    def test_unknown_instrument(self):
        assert get_instrument("FAKE") is None

    def test_all_instruments_have_required_fields(self):
        for sym, inst in INSTRUMENTS.items():
            assert inst.symbol == sym
            assert inst.name
            assert inst.multiplier > 0
            assert inst.yahoo_ticker.endswith("=F")
            assert inst.exchange
            assert inst.category

    def test_display_list_format(self):
        items = instrument_display_list()
        assert len(items) == len(INSTRUMENTS)
        # Each should contain " — " and "$/pt"
        for item in items:
            assert " — " in item
            assert "/pt)" in item

    def test_symbol_from_display_roundtrip(self):
        for display in instrument_display_list():
            sym = symbol_from_display(display)
            assert sym in INSTRUMENTS

    def test_micro_contracts_included(self):
        micro_symbols = ["MES", "MNQ", "MYM", "M2K", "MCL", "MGC", "SIL", "MNG"]
        for sym in micro_symbols:
            assert sym in INSTRUMENTS, f"Micro contract {sym} missing from catalog"

    def test_multiplier_micro_vs_standard(self):
        """Micro contracts should have 1/10th the multiplier of their standard counterpart."""
        assert get_instrument("MES").multiplier == get_instrument("ES").multiplier / 10
        assert get_instrument("MNQ").multiplier == get_instrument("NQ").multiplier / 10
        assert get_instrument("MCL").multiplier == get_instrument("CL").multiplier / 10
        assert get_instrument("MGC").multiplier == get_instrument("GC").multiplier / 10


class TestPriceFetching:
    def test_fetch_es_historical(self):
        """Fetch a known historical ES price (requires network)."""
        from datetime import date
        price = fetch_price_for_instrument("ES", date(2025, 1, 15))
        assert price is not None
        assert price > 0
        # ES was around 5900-6000 in Jan 2025
        assert 4000 < price < 8000

    def test_fetch_unknown_instrument_returns_none(self):
        from datetime import date
        price = fetch_price_for_instrument("FAKE_INSTRUMENT", date(2025, 1, 15))
        assert price is None
