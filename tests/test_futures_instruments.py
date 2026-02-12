"""Tests for the futures instruments catalog and price fetching."""

import pytest
from futures_instruments import (
    INSTRUMENTS,
    get_instrument,
    instrument_display_list,
    symbol_from_display,
    fetch_price_for_instrument,
    MONTH_CODES,
    MONTH_NAMES,
    build_contract_symbol,
    month_from_name,
    build_yahoo_contract_ticker,
    fetch_roll_volume,
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


class TestContractSymbolBuilder:
    def test_es_march_2025(self):
        assert build_contract_symbol("ES", 3, 2025) == "ESH25"

    def test_mes_june_2026(self):
        assert build_contract_symbol("MES", 6, 2026) == "MESM26"

    def test_nq_december_2025(self):
        assert build_contract_symbol("NQ", 12, 2025) == "NQZ25"

    def test_cl_january_2030(self):
        assert build_contract_symbol("CL", 1, 2030) == "CLF30"

    def test_gc_september_2025(self):
        assert build_contract_symbol("GC", 9, 2025) == "GCU25"

    def test_all_month_codes(self):
        expected = {
            1: "F", 2: "G", 3: "H", 4: "J", 5: "K", 6: "M",
            7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z",
        }
        for month_num, code in expected.items():
            sym = build_contract_symbol("ES", month_num, 2025)
            assert sym == f"ES{code}25"

    def test_month_names_count(self):
        assert len(MONTH_NAMES) == 12

    def test_month_from_name_roundtrip(self):
        for i, name in enumerate(MONTH_NAMES, start=1):
            assert month_from_name(name) == i

    def test_month_from_name_to_symbol(self):
        month_num = month_from_name("March (H)")
        assert build_contract_symbol("ES", month_num, 2025) == "ESH25"

    def test_two_digit_year_padding(self):
        # Year 2005 -> "05" not "5"
        assert build_contract_symbol("ES", 3, 2005) == "ESH05"


class TestYahooContractTicker:
    def test_es_cme(self):
        assert build_yahoo_contract_ticker("ES", 3, 2026) == "ESH26.CME"

    def test_zb_cbot(self):
        assert build_yahoo_contract_ticker("ZB", 6, 2026) == "ZBM26.CBT"

    def test_cl_nymex(self):
        assert build_yahoo_contract_ticker("CL", 12, 2025) == "CLZ25.NYM"

    def test_gc_comex(self):
        assert build_yahoo_contract_ticker("GC", 4, 2026) == "GCJ26.CMX"

    def test_unknown_instrument_returns_none(self):
        assert build_yahoo_contract_ticker("FAKE", 1, 2025) is None

    def test_mes_micro_cme(self):
        assert build_yahoo_contract_ticker("MES", 9, 2026) == "MESU26.CME"


class TestRollVolume:
    def test_fetch_es_volume(self):
        """Fetch volume data for ES front/back months (requires network)."""
        data = fetch_roll_volume("ES", 3, 2026, 6, 2026, period="5d")
        assert data is not None
        assert data.front_ticker == "ESH26.CME"
        assert data.back_ticker == "ESM26.CME"
        assert data.latest_front_vol >= 0
        assert data.latest_back_vol >= 0
        assert data.ratio >= 0
        assert len(data.dates) > 0

    def test_unknown_instrument_returns_none(self):
        data = fetch_roll_volume("FAKE", 1, 2025, 3, 2025)
        assert data is None


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
