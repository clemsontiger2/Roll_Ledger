"""Tests for the futures contract roll ledger core logic."""

import pytest
from roll_ledger import RollLedger, RollEntry


def make_es_ledger() -> RollLedger:
    """Create an ES ledger with a realistic multi-roll scenario."""
    ledger = RollLedger(instrument="ES", contract_multiplier=50.0)
    # Roll 1: Buy ESH25 at 5000, roll out at 5050 (+50 pts = +$2500)
    ledger.add_initial_entry(
        contract_symbol="ESH25",
        entry_date="2025-01-15",
        entry_price=5000.0,
        quantity=1,
        direction="LONG",
    )
    # Roll into ESM25 at 5060 (contango gap of 10 pts)
    ledger.roll_contract(
        exit_price=5050.0,
        exit_date="2025-03-14",
        new_contract_symbol="ESM25",
        new_entry_price=5060.0,
    )
    return ledger


class TestRollEntry:
    def test_long_realized_pnl(self):
        entry = RollEntry(
            roll_number=1,
            contract_symbol="ESH25",
            entry_date="2025-01-15",
            entry_price=5000.0,
            exit_date="2025-03-14",
            exit_price=5050.0,
            quantity=1,
            direction="LONG",
        )
        assert entry.realized_pnl_per_contract == 50.0
        assert entry.realized_pnl(50.0) == 2500.0  # 50 pts * $50
        assert not entry.is_active

    def test_short_realized_pnl(self):
        entry = RollEntry(
            roll_number=1,
            contract_symbol="CLH25",
            entry_date="2025-01-15",
            entry_price=75.0,
            exit_date="2025-02-14",
            exit_price=70.0,
            quantity=2,
            direction="SHORT",
        )
        assert entry.realized_pnl_per_contract == 5.0  # 75 - 70
        assert entry.realized_pnl(1000.0) == 10000.0  # 5 * 1000 * 2

    def test_active_entry_has_no_realized(self):
        entry = RollEntry(
            roll_number=1,
            contract_symbol="ESH25",
            entry_date="2025-01-15",
            entry_price=5000.0,
            quantity=1,
            direction="LONG",
        )
        assert entry.is_active
        assert entry.realized_pnl_per_contract is None
        assert entry.realized_pnl(50.0) is None

    def test_unrealized_pnl_long(self):
        entry = RollEntry(
            roll_number=1,
            contract_symbol="ESH25",
            entry_date="2025-01-15",
            entry_price=5000.0,
            quantity=2,
            direction="LONG",
        )
        assert entry.unrealized_pnl_per_contract(5100.0) == 100.0
        assert entry.unrealized_pnl(5100.0, 50.0) == 10000.0  # 100 * 50 * 2

    def test_unrealized_pnl_short(self):
        entry = RollEntry(
            roll_number=1,
            contract_symbol="ESH25",
            entry_date="2025-01-15",
            entry_price=5000.0,
            quantity=1,
            direction="SHORT",
        )
        assert entry.unrealized_pnl_per_contract(4900.0) == 100.0
        assert entry.unrealized_pnl(4900.0, 50.0) == 5000.0


class TestRollLedger:
    def test_initial_entry(self):
        ledger = RollLedger(instrument="ES", contract_multiplier=50.0)
        ledger.add_initial_entry(
            contract_symbol="ESH25",
            entry_date="2025-01-15",
            entry_price=5000.0,
        )
        assert len(ledger.rolls) == 1
        assert ledger.active_roll is not None
        assert ledger.active_roll.contract_symbol == "ESH25"
        assert ledger.total_realized_pnl == 0.0

    def test_cannot_add_initial_entry_twice(self):
        ledger = RollLedger(instrument="ES", contract_multiplier=50.0)
        ledger.add_initial_entry("ESH25", "2025-01-15", 5000.0)
        with pytest.raises(ValueError):
            ledger.add_initial_entry("ESM25", "2025-03-15", 5100.0)

    def test_roll_contract(self):
        ledger = make_es_ledger()
        assert len(ledger.rolls) == 2
        assert len(ledger.closed_rolls) == 1
        assert ledger.active_roll.contract_symbol == "ESM25"
        assert ledger.total_realized_pnl == 2500.0  # 50 pts * $50

    def test_breakeven_after_profitable_roll(self):
        """After a profitable roll, breakeven should be BELOW current entry."""
        ledger = make_es_ledger()
        breakeven = ledger.breakeven_price()
        # Breakeven = 5060 - (2500 / (50 * 1)) = 5060 - 50 = 5010
        assert breakeven == pytest.approx(5010.0)

    def test_breakeven_after_losing_roll(self):
        """After a losing roll, breakeven should be ABOVE current entry."""
        ledger = RollLedger(instrument="ES", contract_multiplier=50.0)
        ledger.add_initial_entry("ESH25", "2025-01-15", 5000.0)
        # Lose 30 pts on roll 1
        ledger.roll_contract(
            exit_price=4970.0,
            exit_date="2025-03-14",
            new_contract_symbol="ESM25",
            new_entry_price=4980.0,
        )
        # Realized: -30 * 50 = -$1500
        assert ledger.total_realized_pnl == pytest.approx(-1500.0)
        breakeven = ledger.breakeven_price()
        # Breakeven = 4980 - (-1500 / 50) = 4980 + 30 = 5010
        assert breakeven == pytest.approx(5010.0)

    def test_true_pnl(self):
        ledger = make_es_ledger()
        # Current price = 5100
        # Unrealized: (5100 - 5060) * 50 * 1 = $2000
        # Realized: $2500
        # True P&L: $4500
        true = ledger.true_pnl(5100.0)
        assert true == pytest.approx(4500.0)

    def test_true_pnl_per_contract(self):
        ledger = make_es_ledger()
        # True P&L per contract in points:
        # Unrealized per contract: 5100 - 5060 = 40
        # Total realized per contract: 50
        # True P&L per contract: 90
        per = ledger.true_pnl_per_contract(5100.0)
        assert per == pytest.approx(90.0)

    def test_multiple_rolls(self):
        """Track across 3 rolls with varying results."""
        ledger = RollLedger(instrument="NQ", contract_multiplier=20.0)
        ledger.add_initial_entry("NQH25", "2025-01-10", 17000.0, quantity=2)

        # Roll 1: +200 pts
        ledger.roll_contract(17200.0, "2025-03-14", "NQM25", 17220.0)
        assert ledger.total_realized_pnl == pytest.approx(200.0 * 20.0 * 2)  # $8000

        # Roll 2: -50 pts
        ledger.roll_contract(17170.0, "2025-06-13", "NQU25", 17180.0)
        roll2_pnl = (17170.0 - 17220.0) * 20.0 * 2  # -50 * 20 * 2 = -$2000
        assert ledger.total_realized_pnl == pytest.approx(8000.0 + (-2000.0))  # $6000

        # Breakeven = 17180 - (6000 / (20 * 2)) = 17180 - 150 = 17030
        assert ledger.breakeven_price() == pytest.approx(17030.0)

    def test_close_position(self):
        ledger = make_es_ledger()
        ledger.close_position(5100.0, "2025-06-13")
        assert ledger.active_roll is None
        # All rolls closed: first roll +$2500, second roll (5100-5060)*50 = $2000
        assert ledger.total_realized_pnl == pytest.approx(4500.0)

    def test_close_without_active_raises(self):
        ledger = RollLedger(instrument="ES", contract_multiplier=50.0)
        with pytest.raises(ValueError):
            ledger.close_position(5000.0, "2025-01-15")

    def test_roll_without_active_raises(self):
        ledger = RollLedger(instrument="ES", contract_multiplier=50.0)
        with pytest.raises(ValueError):
            ledger.roll_contract(5000.0, "2025-01-15", "ESM25", 5010.0)

    def test_short_direction_multi_roll(self):
        ledger = RollLedger(instrument="CL", contract_multiplier=1000.0)
        ledger.add_initial_entry("CLH25", "2025-01-10", 75.0, direction="SHORT")
        # Price drops to 72, roll (profit of 3 pts for SHORT)
        ledger.roll_contract(72.0, "2025-02-14", "CLJ25", 72.5)
        assert ledger.total_realized_pnl == pytest.approx(3000.0)  # 3 * 1000

        # Breakeven for SHORT = 72.5 - (3000 / 1000) = 72.5 - 3 = 69.5?
        # No: breakeven = entry - realized/(mult*qty) = 72.5 - 3000/(1000*1) = 69.5
        # But for SHORT, profitable when price < breakeven
        # Actually the formula: breakeven = 72.5 - 3.0 = 69.5
        # With cushion of $3000, the short is profitable as long as price is below 72.5+3 = 75.5
        # Wait, let's re-derive:
        # True P&L (SHORT) = (entry - current) * mult * qty + realized
        # = (72.5 - current) * 1000 + 3000
        # Break even when True P&L = 0:
        # 0 = (72.5 - BE) * 1000 + 3000
        # (72.5 - BE) * 1000 = -3000
        # 72.5 - BE = -3
        # BE = 75.5
        # Using our formula: BE = entry - realized/(mult*qty) = 72.5 - 3000/1000 = 69.5
        # Hmm, that gives 69.5 which is wrong for a short.
        #
        # Actually re-check the formula. For the formula to be universal:
        # True P&L (LONG) = (current - entry) * M * Q + realized = 0
        #   => current = entry - realized/(M*Q) = breakeven  ✓
        #
        # True P&L (SHORT) = (entry - current) * M * Q + realized = 0
        #   => entry - current = -realized/(M*Q)
        #   => current = entry + realized/(M*Q) = 72.5 + 3 = 75.5
        #
        # So the breakeven formula differs by direction. Our current code uses:
        # breakeven = entry - realized/(M*Q) which is correct for LONG only.
        # For SHORT it should be entry + realized/(M*Q).
        #
        # This is a bug! Let's just verify current behavior and fix it.
        breakeven = ledger.breakeven_price()
        # Currently returns 72.5 - 3 = 69.5 (wrong for SHORT)
        # Should be 75.5
        assert breakeven == pytest.approx(75.5)


class TestCsvRoundTrip:
    def test_roundtrip(self):
        ledger = make_es_ledger()
        csv_text = ledger.to_csv_string()
        restored = RollLedger.from_csv_string(csv_text)

        assert restored.instrument == ledger.instrument
        assert restored.contract_multiplier == ledger.contract_multiplier
        assert len(restored.rolls) == len(ledger.rolls)

        for orig, rest in zip(ledger.rolls, restored.rolls):
            assert rest.roll_number == orig.roll_number
            assert rest.contract_symbol == orig.contract_symbol
            assert rest.entry_date == orig.entry_date
            assert rest.entry_price == orig.entry_price
            assert rest.exit_date == orig.exit_date
            assert rest.exit_price == orig.exit_price
            assert rest.quantity == orig.quantity
            assert rest.direction == orig.direction

    def test_roundtrip_with_notes(self):
        ledger = RollLedger(instrument="NQ", contract_multiplier=20.0)
        ledger.add_initial_entry("NQH25", "2025-01-10", 17000.0, notes="Initial position, bullish setup")
        csv_text = ledger.to_csv_string()
        restored = RollLedger.from_csv_string(csv_text)
        assert restored.rolls[0].notes == "Initial position, bullish setup"

    def test_roundtrip_bytes(self):
        ledger = make_es_ledger()
        data = ledger.to_csv_bytes()
        restored = RollLedger.from_csv_bytes(data)
        assert restored.instrument == "ES"
        assert len(restored.rolls) == 2

    def test_cumulative_pnl_series(self):
        ledger = make_es_ledger()
        series = ledger.cumulative_pnl_series()
        assert len(series) == 3  # entry1, exit1/roll, entry2
        assert series[0]["cum_pnl"] == 0.0
        assert series[1]["cum_pnl"] == pytest.approx(2500.0)
        assert series[2]["cum_pnl"] == pytest.approx(2500.0)  # same at new entry
