"""
Futures Contract Roll Ledger

Tracks performance across multiple contract rolls by maintaining an adjusted
cost basis. Futures price charts are "saw-toothed" because contracts expire
and prices jump at each roll. This ledger normalizes that into a single
continuous performance line.

Core formula:
    True P&L = (Current Price - Current Entry) + Sum(Realized P&L from Previous Rolls)
    Breakeven = Current Entry Price - (Total Realized P&L / Contract Multiplier)
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Optional


@dataclass
class RollEntry:
    """A single contract period in the ledger."""

    roll_number: int
    contract_symbol: str
    entry_date: str  # ISO format YYYY-MM-DD
    entry_price: float
    exit_date: Optional[str] = None  # None if this is the active contract
    exit_price: Optional[float] = None
    quantity: int = 1
    direction: str = "LONG"  # LONG or SHORT
    notes: str = ""

    @property
    def is_active(self) -> bool:
        return self.exit_price is None

    @property
    def realized_pnl_per_contract(self) -> Optional[float]:
        """P&L per contract for this roll period (before multiplier)."""
        if self.exit_price is None:
            return None
        if self.direction == "LONG":
            return self.exit_price - self.entry_price
        else:
            return self.entry_price - self.exit_price

    def realized_pnl(self, multiplier: float) -> Optional[float]:
        """Total realized P&L for this roll including multiplier and quantity."""
        per = self.realized_pnl_per_contract
        if per is None:
            return None
        return per * multiplier * self.quantity

    def unrealized_pnl_per_contract(self, current_price: float) -> Optional[float]:
        if not self.is_active:
            return None
        if self.direction == "LONG":
            return current_price - self.entry_price
        else:
            return self.entry_price - current_price

    def unrealized_pnl(self, current_price: float, multiplier: float) -> Optional[float]:
        per = self.unrealized_pnl_per_contract(current_price)
        if per is None:
            return None
        return per * multiplier * self.quantity


@dataclass
class RollLedger:
    """
    A ledger tracking a single futures position across multiple contract rolls.

    Attributes:
        instrument: Underlying instrument name (e.g. "ES", "NQ", "CL")
        contract_multiplier: Dollar value per point (e.g. $50 for ES, $20 for NQ)
        rolls: Ordered list of contract rolls
    """

    instrument: str
    contract_multiplier: float
    rolls: list[RollEntry] = field(default_factory=list)

    @property
    def active_roll(self) -> Optional[RollEntry]:
        for r in reversed(self.rolls):
            if r.is_active:
                return r
        return None

    @property
    def closed_rolls(self) -> list[RollEntry]:
        return [r for r in self.rolls if not r.is_active]

    @property
    def total_realized_pnl(self) -> float:
        """Sum of realized P&L across all closed rolls."""
        total = 0.0
        for r in self.closed_rolls:
            pnl = r.realized_pnl(self.contract_multiplier)
            if pnl is not None:
                total += pnl
        return total

    @property
    def total_realized_pnl_per_contract(self) -> float:
        """Sum of realized P&L per contract (before multiplier) across closed rolls."""
        total = 0.0
        for r in self.closed_rolls:
            per = r.realized_pnl_per_contract
            if per is not None:
                total += per
        return total

    def breakeven_price(self) -> Optional[float]:
        """
        The price at which the entire position (across all rolls) breaks even.

        LONG:  Breakeven = Entry - Realized / (Multiplier * Qty)
          -> Positive realized lowers breakeven (cushion below entry)
        SHORT: Breakeven = Entry + Realized / (Multiplier * Qty)
          -> Positive realized raises breakeven (cushion above entry)
        """
        active = self.active_roll
        if active is None:
            return None
        if active.quantity == 0:
            return None
        adjustment = self.total_realized_pnl / (self.contract_multiplier * active.quantity)
        if active.direction == "LONG":
            return active.entry_price - adjustment
        else:
            return active.entry_price + adjustment

    def true_pnl(self, current_price: float) -> Optional[float]:
        """
        True P&L = (Current Price - Current Entry) * Multiplier * Qty + Total Realized P&L

        This is the normalized, continuous P&L that flattens the sawtooth.
        """
        active = self.active_roll
        if active is None:
            return None
        unrealized = active.unrealized_pnl(current_price, self.contract_multiplier)
        if unrealized is None:
            return None
        return unrealized + self.total_realized_pnl

    def true_pnl_per_contract(self, current_price: float) -> Optional[float]:
        """True P&L per single contract in price points (before multiplier)."""
        active = self.active_roll
        if active is None:
            return None
        unrealized = active.unrealized_pnl_per_contract(current_price)
        if unrealized is None:
            return None
        return unrealized + self.total_realized_pnl_per_contract

    def add_initial_entry(
        self,
        contract_symbol: str,
        entry_date: str,
        entry_price: float,
        quantity: int = 1,
        direction: str = "LONG",
        notes: str = "",
    ) -> RollEntry:
        """Open the first position."""
        if self.rolls:
            raise ValueError("Ledger already has entries. Use roll_contract() to add rolls.")
        entry = RollEntry(
            roll_number=1,
            contract_symbol=contract_symbol,
            entry_date=entry_date,
            entry_price=entry_price,
            quantity=quantity,
            direction=direction,
            notes=notes,
        )
        self.rolls.append(entry)
        return entry

    def roll_contract(
        self,
        exit_price: float,
        exit_date: str,
        new_contract_symbol: str,
        new_entry_price: float,
        new_entry_date: Optional[str] = None,
        new_quantity: Optional[int] = None,
        notes: str = "",
    ) -> RollEntry:
        """
        Close the current contract and open a new one.

        This is where the "roll" happens. The exit_price of the old contract and
        entry_price of the new contract will usually differ (the roll gap).
        The ledger captures that realized P&L so it isn't lost.
        """
        active = self.active_roll
        if active is None:
            raise ValueError("No active contract to roll from.")

        # Close the current contract
        active.exit_price = exit_price
        active.exit_date = exit_date

        # Open the new contract
        new_entry = RollEntry(
            roll_number=active.roll_number + 1,
            contract_symbol=new_contract_symbol,
            entry_date=new_entry_date or exit_date,
            entry_price=new_entry_price,
            quantity=new_quantity if new_quantity is not None else active.quantity,
            direction=active.direction,
            notes=notes,
        )
        self.rolls.append(new_entry)
        return new_entry

    def close_position(self, exit_price: float, exit_date: str) -> None:
        """Close the active contract without rolling into a new one."""
        active = self.active_roll
        if active is None:
            raise ValueError("No active contract to close.")
        active.exit_price = exit_price
        active.exit_date = exit_date

    def cumulative_pnl_series(self) -> list[dict]:
        """
        Build a series of cumulative P&L data points for charting.
        Each closed roll contributes a segment; the active roll is open-ended.
        Returns list of dicts with keys: roll_number, contract, date, cum_pnl, event
        """
        series = []
        cum = 0.0
        for r in self.rolls:
            # Entry point
            series.append({
                "roll_number": r.roll_number,
                "contract": r.contract_symbol,
                "date": r.entry_date,
                "cum_pnl": cum,
                "event": "entry",
            })
            if not r.is_active:
                pnl = r.realized_pnl(self.contract_multiplier)
                cum += pnl if pnl else 0.0
                series.append({
                    "roll_number": r.roll_number,
                    "contract": r.contract_symbol,
                    "date": r.exit_date,
                    "cum_pnl": cum,
                    "event": "exit/roll",
                })
        return series

    # ── CSV Serialization ──────────────────────────────────────────────

    CSV_HEADER_META = ["instrument", "contract_multiplier"]
    CSV_HEADER_ROLLS = [
        "roll_number",
        "contract_symbol",
        "entry_date",
        "entry_price",
        "exit_date",
        "exit_price",
        "quantity",
        "direction",
        "notes",
    ]

    def to_csv_string(self) -> str:
        """Serialize the entire ledger to a CSV string."""
        output = io.StringIO()
        writer = csv.writer(output)

        # Meta row
        writer.writerow(["#meta"] + self.CSV_HEADER_META)
        writer.writerow(["#meta", self.instrument, self.contract_multiplier])
        writer.writerow([])  # blank separator

        # Roll rows
        writer.writerow(self.CSV_HEADER_ROLLS)
        for r in self.rolls:
            writer.writerow([
                r.roll_number,
                r.contract_symbol,
                r.entry_date,
                r.entry_price,
                r.exit_date if r.exit_date else "",
                r.exit_price if r.exit_price is not None else "",
                r.quantity,
                r.direction,
                r.notes,
            ])

        return output.getvalue()

    def to_csv_bytes(self) -> bytes:
        return self.to_csv_string().encode("utf-8")

    @classmethod
    def from_csv_string(cls, csv_text: str) -> "RollLedger":
        """Deserialize a ledger from a CSV string."""
        reader = csv.reader(io.StringIO(csv_text))
        rows = list(reader)

        # Parse meta
        instrument = ""
        multiplier = 1.0
        data_start = 0
        for i, row in enumerate(rows):
            if not row:
                continue
            if row[0] == "#meta" and len(row) > 2:
                # This is the data meta row (not the header)
                try:
                    float(row[2])
                    instrument = row[1]
                    multiplier = float(row[2])
                except ValueError:
                    pass  # This is the header meta row
            elif row[0] == "roll_number":
                data_start = i + 1
                break

        ledger = cls(instrument=instrument, contract_multiplier=multiplier)

        # Parse rolls
        for row in rows[data_start:]:
            if not row or len(row) < 6:
                continue
            ledger.rolls.append(RollEntry(
                roll_number=int(row[0]),
                contract_symbol=row[1],
                entry_date=row[2],
                entry_price=float(row[3]),
                exit_date=row[4] if row[4] else None,
                exit_price=float(row[5]) if row[5] else None,
                quantity=int(row[6]) if len(row) > 6 and row[6] else 1,
                direction=row[7] if len(row) > 7 and row[7] else "LONG",
                notes=row[8] if len(row) > 8 else "",
            ))

        return ledger

    @classmethod
    def from_csv_bytes(cls, data: bytes) -> "RollLedger":
        return cls.from_csv_string(data.decode("utf-8"))
