"""
Futures Contract Roll Ledger — Streamlit App

A tool for tracking futures positions across contract rolls, normalizing
the saw-toothed price chart into a continuous performance line via an
Adjusted Cost Basis (Breakeven Price).
"""

import streamlit as st
import pandas as pd
from roll_ledger import RollLedger, RollEntry
from futures_instruments import (
    INSTRUMENTS,
    get_instrument,
    instrument_display_list,
    symbol_from_display,
    fetch_price_for_instrument,
)

# ── Page Config ────────────────────────────────────────────────────────

st.set_page_config(page_title="Futures Roll Ledger", layout="wide")
st.title("Futures Contract Roll Ledger")
st.caption(
    "Track your true P&L across contract rolls. "
    "Normalizes the saw-toothed futures price chart into a single continuous performance line."
)

# ── Session State Initialization ───────────────────────────────────────

if "ledger" not in st.session_state:
    st.session_state.ledger = None


def get_ledger() -> RollLedger | None:
    return st.session_state.ledger


def set_ledger(ledger: RollLedger):
    st.session_state.ledger = ledger


# ── Sidebar: Create / Import Ledger ───────────────────────────────────

with st.sidebar:
    st.header("Ledger Setup")

    tab_new, tab_import = st.tabs(["New Ledger", "Import CSV"])

    with tab_new:
        st.subheader("Create New Ledger")

        # Instrument dropdown (outside form so changes update multiplier instantly)
        display_options = instrument_display_list()
        selected_display = st.selectbox(
            "Instrument",
            options=display_options,
            index=0,
            key="instrument_select",
        )
        selected_symbol = symbol_from_display(selected_display)
        selected_inst = get_instrument(selected_symbol)
        if selected_inst:
            st.caption(
                f"{selected_inst.exchange} | Multiplier: "
                f"${selected_inst.multiplier:,.2f}/pt"
            )

        with st.form("new_ledger_form"):
            st.markdown("---")
            st.subheader("Initial Entry")
            init_symbol = st.text_input(
                "Contract Symbol", placeholder="ESH25, NQM25..."
            )
            init_direction = st.selectbox("Direction", ["LONG", "SHORT"])
            init_date = st.date_input("Entry Date")
            init_price = st.number_input(
                "Entry Price", min_value=0.0, step=0.25, format="%.4f",
                key="init_entry_price",
            )
            fetch_init = st.form_submit_button("Fetch Price from Yahoo Finance")
            init_qty = st.number_input(
                "Quantity", min_value=1, value=1, step=1
            )
            init_notes = st.text_input("Notes (optional)", key="init_notes")

            submitted = st.form_submit_button("Create Ledger")

        if fetch_init and selected_inst:
            with st.spinner(f"Fetching {selected_inst.yahoo_ticker} close for {init_date}..."):
                price = fetch_price_for_instrument(selected_symbol, init_date)
            if price is not None:
                st.session_state["init_entry_price"] = price
                st.rerun()
            else:
                st.error(f"No data found for {selected_inst.yahoo_ticker} on {init_date}.")

        if submitted:
            if not selected_symbol or not init_symbol or init_price <= 0:
                st.error("Select an instrument, enter contract symbol, and a positive entry price.")
            else:
                ledger = RollLedger(
                    instrument=selected_symbol,
                    contract_multiplier=selected_inst.multiplier if selected_inst else 50.0,
                )
                ledger.add_initial_entry(
                    contract_symbol=init_symbol.upper().strip(),
                    entry_date=str(init_date),
                    entry_price=init_price,
                    quantity=init_qty,
                    direction=init_direction,
                    notes=init_notes,
                )
                set_ledger(ledger)
                st.success(f"Ledger created for {selected_symbol}")

    with tab_import:
        st.subheader("Import from CSV")
        uploaded = st.file_uploader("Upload ledger CSV", type=["csv"])
        if uploaded is not None:
            try:
                csv_text = uploaded.getvalue().decode("utf-8")
                ledger = RollLedger.from_csv_string(csv_text)
                set_ledger(ledger)
                st.success(
                    f"Imported ledger: {ledger.instrument} "
                    f"({len(ledger.rolls)} roll{'s' if len(ledger.rolls) != 1 else ''})"
                )
            except Exception as e:
                st.error(f"Failed to parse CSV: {e}")

    # Export
    if get_ledger() is not None:
        st.markdown("---")
        st.subheader("Export")
        csv_bytes = get_ledger().to_csv_bytes()
        st.download_button(
            label="Download Ledger CSV",
            data=csv_bytes,
            file_name=f"{get_ledger().instrument}_roll_ledger.csv",
            mime="text/csv",
        )

# ── Main Area ──────────────────────────────────────────────────────────

ledger = get_ledger()

if ledger is None:
    st.info("Create a new ledger or import a CSV from the sidebar to get started.")
    st.stop()

# ── Summary Metrics ────────────────────────────────────────────────────

st.header(f"{ledger.instrument} Roll Ledger")

active = ledger.active_roll

col_price, col_fetch, col_calc = st.columns([2, 1, 1])

with col_price:
    current_price = st.number_input(
        "Current Market Price",
        min_value=0.0,
        value=active.entry_price if active else 0.0,
        step=0.25,
        format="%.4f",
        key="current_price",
    )

with col_fetch:
    st.write("")  # spacing
    st.write("")
    inst = get_instrument(ledger.instrument)
    if inst and st.button("Fetch Latest Price", key="fetch_current"):
        from datetime import date as date_type
        with st.spinner(f"Fetching {inst.yahoo_ticker}..."):
            price = fetch_price_for_instrument(ledger.instrument, date_type.today())
        if price is not None:
            st.session_state["current_price"] = price
            st.rerun()
        else:
            st.error("Could not fetch price.")

# Compute metrics
breakeven = ledger.breakeven_price()
true_pnl = ledger.true_pnl(current_price)
true_pnl_per = ledger.true_pnl_per_contract(current_price)
total_realized = ledger.total_realized_pnl

with col_calc:
    if active:
        st.metric("Active Contract", active.contract_symbol)

num_rolls = len(ledger.closed_rolls)

m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric(
        "Breakeven Price",
        f"{breakeven:,.4f}" if breakeven is not None else "N/A",
        help="Price above (LONG) or below (SHORT) which the total position is profitable",
    )
with m2:
    st.metric(
        "True P&L (Total $)",
        f"${true_pnl:,.2f}" if true_pnl is not None else "N/A",
        delta=f"${true_pnl:,.2f}" if true_pnl is not None else None,
    )
with m3:
    st.metric(
        "Total Realized P&L",
        f"${total_realized:,.2f}",
        help="Cumulative P&L from all closed rolls",
    )
with m4:
    st.metric(
        "Rolls Completed",
        num_rolls,
    )

if active and true_pnl_per is not None:
    direction_label = "above" if active.direction == "LONG" else "below"
    if breakeven is not None:
        diff = current_price - breakeven if active.direction == "LONG" else breakeven - current_price
        if diff >= 0:
            st.success(
                f"Position is profitable. Current price is {abs(diff):,.4f} pts "
                f"{direction_label} breakeven ({breakeven:,.4f})."
            )
        else:
            st.warning(
                f"Position is underwater. Need {abs(diff):,.4f} pts to reach "
                f"breakeven ({breakeven:,.4f})."
            )

# ── Roll History Table ─────────────────────────────────────────────────

st.subheader("Roll History")

if ledger.rolls:
    rows = []
    for r in ledger.rolls:
        realized = r.realized_pnl(ledger.contract_multiplier)
        rows.append({
            "#": r.roll_number,
            "Contract": r.contract_symbol,
            "Direction": r.direction,
            "Qty": r.quantity,
            "Entry Date": r.entry_date,
            "Entry Price": r.entry_price,
            "Exit Date": r.exit_date or "(active)",
            "Exit Price": f"{r.exit_price:,.4f}" if r.exit_price is not None else "(active)",
            "Realized P&L": f"${realized:,.2f}" if realized is not None else "-",
            "Notes": r.notes,
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.write("No rolls recorded yet.")

# ── Cumulative P&L Chart ──────────────────────────────────────────────

series = ledger.cumulative_pnl_series()
if len(series) > 1:
    st.subheader("Cumulative P&L Over Rolls")
    chart_df = pd.DataFrame(series)
    chart_df["date"] = pd.to_datetime(chart_df["date"])

    # Add current unrealized point if active
    if active and current_price > 0:
        from datetime import date as date_type

        unrealized_total = ledger.true_pnl(current_price)
        chart_df = pd.concat([
            chart_df,
            pd.DataFrame([{
                "roll_number": active.roll_number,
                "contract": active.contract_symbol,
                "date": pd.Timestamp.now(),
                "cum_pnl": unrealized_total if unrealized_total is not None else 0,
                "event": "current (unrealized)",
            }])
        ], ignore_index=True)

    st.line_chart(chart_df, x="date", y="cum_pnl")

# ── Actions: Roll Contract / Close Position ────────────────────────────

st.markdown("---")

if active:
    action_col1, action_col2 = st.columns(2)

    with action_col1:
        st.subheader("Roll Into New Contract")
        with st.form("roll_form"):
            roll_exit_price = st.number_input(
                "Exit Price (current contract)",
                min_value=0.0,
                value=0.0,
                step=0.25,
                format="%.4f",
                key="roll_exit_price",
            )
            roll_exit_date = st.date_input("Exit/Roll Date", key="roll_exit_date")
            fetch_roll = st.form_submit_button("Fetch Roll Date Price")
            new_symbol = st.text_input(
                "New Contract Symbol", placeholder="ESM25, ESU25...", key="new_symbol"
            )
            new_price = st.number_input(
                "New Entry Price",
                min_value=0.0,
                value=0.0,
                step=0.25,
                format="%.4f",
                key="new_entry_price",
            )
            new_qty = st.number_input(
                "New Quantity",
                min_value=1,
                value=active.quantity,
                step=1,
                key="new_qty",
            )
            roll_notes = st.text_input("Notes (optional)", key="roll_notes")

            roll_submitted = st.form_submit_button("Execute Roll")

        if fetch_roll:
            roll_inst = get_instrument(ledger.instrument)
            if roll_inst:
                with st.spinner(f"Fetching {roll_inst.yahoo_ticker} close for {roll_exit_date}..."):
                    price = fetch_price_for_instrument(ledger.instrument, roll_exit_date)
                if price is not None:
                    st.session_state["roll_exit_price"] = price
                    st.session_state["new_entry_price"] = price
                    st.rerun()
                else:
                    st.error(f"No data for {roll_inst.yahoo_ticker} on {roll_exit_date}.")

        if roll_submitted:
            if roll_exit_price <= 0 or new_price <= 0 or not new_symbol:
                st.error("Provide valid exit price, new symbol, and new entry price.")
            else:
                ledger.roll_contract(
                    exit_price=roll_exit_price,
                    exit_date=str(roll_exit_date),
                    new_contract_symbol=new_symbol.upper().strip(),
                    new_entry_price=new_price,
                    new_entry_date=str(roll_exit_date),
                    new_quantity=new_qty,
                    notes=roll_notes,
                )
                set_ledger(ledger)
                st.success(
                    f"Rolled from {active.contract_symbol} to {new_symbol.upper()}. "
                    f"Realized P&L on this roll: "
                    f"${active.realized_pnl(ledger.contract_multiplier):,.2f}"
                )
                st.rerun()

    with action_col2:
        st.subheader("Close Position")
        with st.form("close_form"):
            close_price = st.number_input(
                "Exit Price",
                min_value=0.0,
                value=0.0,
                step=0.25,
                format="%.4f",
                key="close_exit_price",
            )
            close_date = st.date_input("Close Date", key="close_date")
            fetch_close = st.form_submit_button("Fetch Close Date Price")

            close_submitted = st.form_submit_button("Close Position")

        if fetch_close:
            close_inst = get_instrument(ledger.instrument)
            if close_inst:
                with st.spinner(f"Fetching {close_inst.yahoo_ticker} close for {close_date}..."):
                    price = fetch_price_for_instrument(ledger.instrument, close_date)
                if price is not None:
                    st.session_state["close_exit_price"] = price
                    st.rerun()
                else:
                    st.error(f"No data for {close_inst.yahoo_ticker} on {close_date}.")

        if close_submitted:
            if close_price <= 0:
                st.error("Provide a valid exit price.")
            else:
                ledger.close_position(
                    exit_price=close_price,
                    exit_date=str(close_date),
                )
                set_ledger(ledger)
                st.success("Position closed.")
                st.rerun()
else:
    st.info("No active position. Create a new ledger or import one from the sidebar.")

# ── Formula Reference (collapsible) ───────────────────────────────────

with st.expander("Formula Reference"):
    st.markdown("""
**Adjusted Cost Basis (Breakeven Price)**

The key insight: when you roll a futures contract, the realized P&L from the
old contract must be carried forward. Otherwise, the "sawtooth" gap between
the old exit price and new entry price makes your true performance invisible.

**Formulas used in this ledger:**

| Metric | Formula |
|--------|---------|
| **Realized P&L (per roll)** | `(Exit Price - Entry Price) * Multiplier * Qty` (LONG) |
| **Total Realized P&L** | Sum of all closed rolls' realized P&L |
| **True P&L** | `(Current Price - Current Entry) * Multiplier * Qty + Total Realized P&L` |
| **Breakeven Price** | `Current Entry - Total Realized P&L / (Multiplier * Qty)` |

- If cumulative realized P&L is **positive**, breakeven is *below* your entry (you have a cushion).
- If cumulative realized P&L is **negative**, breakeven is *above* your entry (you need to recover).
""")
