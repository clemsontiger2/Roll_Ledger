"""
Futures Contract Roll Ledger — Streamlit App

Updated with Plotly interactive charts, robust error handling, and smart
quarterly defaults for the roll signal.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date

from roll_ledger import RollLedger, RollEntry
from futures_instruments import (
    INSTRUMENTS,
    get_instrument,
    instrument_display_list,
    symbol_from_display,
    fetch_price_for_instrument,
    MONTH_NAMES,
    MONTH_CODES,
    month_from_name,
    build_contract_symbol,
    fetch_roll_volume,
)

# ── Page Config ────────────────────────────────────────────────────────

st.set_page_config(page_title="Futures Roll Ledger", layout="wide")


# ── Helper: Safe Data Fetch ───────────────────────────────────────────

def safe_fetch_price(symbol, date_obj):
    """Prevent app crash on connection error or missing data."""
    try:
        return fetch_price_for_instrument(symbol, date_obj)
    except Exception as e:
        st.error(f"Data fetch error: {e}")
        return None


# ── Session State Initialization ───────────────────────────────────────

if "ledger" not in st.session_state:
    st.session_state.ledger = None

# Transfer pending fetched prices into widget keys BEFORE widgets render.
# This avoids the StreamlitAPIException from writing to a widget-owned key
# after the widget has already been instantiated in the same script run.
_PENDING_TRANSFERS = {
    "_pending_init_price": "init_entry_price",
    "_pending_current_price": "current_price",
    "_pending_roll_exit_price": "roll_exit_price",
    "_pending_new_entry_price": "new_entry_price",
    "_pending_close_exit_price": "close_exit_price",
}
for _src, _dst in _PENDING_TRANSFERS.items():
    if _src in st.session_state:
        st.session_state[_dst] = st.session_state.pop(_src)


def set_ledger(ledger: RollLedger):
    st.session_state.ledger = ledger


# ── Sidebar: Create / Import Ledger ───────────────────────────────────

with st.sidebar:
    st.title("Ledger Controls")

    tab_new, tab_import = st.tabs(["New", "Import"])

    with tab_new:
        selected_display = st.selectbox("Instrument", instrument_display_list())
        selected_symbol = symbol_from_display(selected_display)
        selected_inst = get_instrument(selected_symbol)

        col_m, col_y = st.columns(2)
        with col_m:
            init_month_name = st.selectbox("Month", MONTH_NAMES, index=2)
        with col_y:
            init_year = st.number_input("Year", value=date.today().year, step=1)

        init_symbol = build_contract_symbol(
            selected_symbol, month_from_name(init_month_name), init_year
        )
        st.info(f"Contract: **{init_symbol}**")

        with st.form("init_form"):
            init_direction = st.selectbox("Direction", ["LONG", "SHORT"])
            init_date = st.date_input("Entry Date")
            init_price = st.number_input(
                "Entry Price", min_value=0.0, step=0.25,
                format="%.4f", key="init_entry_price",
            )
            init_qty = st.number_input("Quantity", min_value=1, value=1)
            init_notes = st.text_input("Notes")

            c1, c2 = st.columns(2)
            with c1:
                fetch_btn = st.form_submit_button("Fetch Price")
            with c2:
                create_btn = st.form_submit_button("Create")

        if fetch_btn:
            p = safe_fetch_price(selected_symbol, init_date)
            if p:
                st.session_state["_pending_init_price"] = p
                st.rerun()

        if create_btn:
            if not selected_symbol or init_price <= 0:
                st.error("Select an instrument and enter a positive entry price.")
            else:
                ledger = RollLedger(selected_symbol, selected_inst.multiplier)
                ledger.add_initial_entry(
                    init_symbol, str(init_date), init_price, init_qty,
                    init_direction, init_notes,
                )
                set_ledger(ledger)
                st.success("Ledger Created!")
                st.rerun()

    with tab_import:
        uploaded = st.file_uploader("Upload CSV", type=["csv"])
        if uploaded:
            try:
                csv_text = uploaded.getvalue().decode("utf-8")
                set_ledger(RollLedger.from_csv_string(csv_text))
                st.success("Loaded!")
            except Exception as e:
                st.error(f"Error: {e}")

    # Export
    if st.session_state.ledger:
        st.markdown("---")
        st.download_button(
            "Save Ledger to CSV",
            st.session_state.ledger.to_csv_bytes(),
            f"{st.session_state.ledger.instrument}_ledger.csv",
            "text/csv",
        )

# ── Main Dashboard ────────────────────────────────────────────────────

ledger = st.session_state.ledger

if not ledger:
    st.info("Create or Import a ledger from the sidebar to get started.")
    st.stop()

st.title(f"{ledger.instrument} Performance Tracker")

# ── Metrics & Live Price ──────────────────────────────────────────────

active = ledger.active_roll
col1, col2, col3 = st.columns([1, 1, 2])

with col1:
    current_price = st.number_input(
        "Current Price", value=active.entry_price if active else 0.0,
        format="%.4f", key="current_price",
    )
    if st.button("Fetch Live Price"):
        p = safe_fetch_price(ledger.instrument, date.today())
        if p:
            st.session_state["_pending_current_price"] = p
            st.rerun()

with col2:
    st.metric("Active Contract", active.contract_symbol if active else "Closed")
    if active:
        be = ledger.breakeven_price()
        if be is not None:
            diff = (
                current_price - be
                if active.direction == "LONG"
                else be - current_price
            )
            st.metric("Breakeven", f"{be:,.4f}", delta=f"{diff:,.2f} cushion")

with col3:
    if active:
        tpnl = ledger.true_pnl(current_price)
        rpnl = ledger.total_realized_pnl
        c1, c2 = st.columns(2)
        c1.metric("True Net P&L", f"${tpnl:,.2f}" if tpnl is not None else "N/A")
        c2.metric("Banked (Realized)", f"${rpnl:,.2f}")

# ── Trade Actions ─────────────────────────────────────────────────────

st.markdown("---")
st.subheader("Trade Actions")

if active:
    ac1, ac2 = st.columns(2)

    with ac1:
        with st.expander("Roll Position (Close Old -> Open New)", expanded=True):
            # New contract month/year selectors
            _roll_col_m, _roll_col_y = st.columns(2)
            with _roll_col_m:
                roll_month_name = st.selectbox(
                    "New Contract Month", MONTH_NAMES, key="roll_contract_month",
                )
            with _roll_col_y:
                roll_year = st.number_input(
                    "New Contract Year", min_value=2000, max_value=2099,
                    value=date.today().year, step=1, key="roll_contract_year",
                )
            roll_month_num = month_from_name(roll_month_name)
            new_symbol = build_contract_symbol(
                ledger.instrument, roll_month_num, roll_year
            )
            st.caption(f"New Contract: **{new_symbol}**")

            with st.form("roll_form"):
                roll_exit_price = st.number_input(
                    "Exit Price (Old)", min_value=0.0, step=0.25,
                    format="%.4f", key="roll_exit_price",
                )
                new_entry_price = st.number_input(
                    "Entry Price (New)", min_value=0.0, step=0.25,
                    format="%.4f", key="new_entry_price",
                )
                roll_date = st.date_input("Roll Date")
                new_qty = st.number_input(
                    "New Quantity", min_value=1, value=active.quantity,
                )
                roll_notes = st.text_input("Notes")

                c1, c2 = st.columns(2)
                with c1:
                    fetch_roll = st.form_submit_button("Fetch Prices")
                with c2:
                    roll_submit = st.form_submit_button("Confirm Roll")

            if fetch_roll:
                p = safe_fetch_price(ledger.instrument, roll_date)
                if p:
                    st.session_state["_pending_roll_exit_price"] = p
                    st.session_state["_pending_new_entry_price"] = p
                    st.rerun()

            if roll_submit:
                if roll_exit_price <= 0 or new_entry_price <= 0:
                    st.error("Provide valid exit and entry prices.")
                else:
                    ledger.roll_contract(
                        exit_price=roll_exit_price,
                        exit_date=str(roll_date),
                        new_contract_symbol=new_symbol,
                        new_entry_price=new_entry_price,
                        new_entry_date=str(roll_date),
                        new_quantity=new_qty,
                        notes=roll_notes,
                    )
                    set_ledger(ledger)
                    st.success(f"Rolled to {new_symbol}!")
                    st.rerun()

    with ac2:
        with st.expander("Close Position (Flat)"):
            with st.form("close_form"):
                close_price = st.number_input(
                    "Exit Price", min_value=0.0, step=0.25,
                    format="%.4f", key="close_exit_price",
                )
                close_date = st.date_input("Close Date")

                c1, c2 = st.columns(2)
                with c1:
                    fetch_close = st.form_submit_button("Fetch Price")
                with c2:
                    close_submit = st.form_submit_button("Close Position")

            if fetch_close:
                p = safe_fetch_price(ledger.instrument, close_date)
                if p:
                    st.session_state["_pending_close_exit_price"] = p
                    st.rerun()

            if close_submit:
                if close_price <= 0:
                    st.error("Provide a valid exit price.")
                else:
                    ledger.close_position(close_price, str(close_date))
                    set_ledger(ledger)
                    st.success("Position Closed!")
                    st.rerun()
else:
    st.info("No active position. Create a new ledger or import one from the sidebar.")

# ── Liquidity Roll Signal ─────────────────────────────────────────────

if active:
    st.markdown("---")
    st.subheader("Liquidity Roll Signal")

    # Parse front month from active contract symbol (e.g. "ESH26" -> month=3, year=2026)
    _code_to_month = {v: k for k, v in MONTH_CODES.items()}
    _active_sym = active.contract_symbol
    _front_month_code = _active_sym[-3] if len(_active_sym) >= 3 else None
    _front_year_2d = _active_sym[-2:] if len(_active_sym) >= 3 else None
    _front_month = _code_to_month.get(_front_month_code) if _front_month_code else None
    _front_year = (
        2000 + int(_front_year_2d)
        if _front_year_2d and _front_year_2d.isdigit()
        else None
    )

    # Smart default: next quarterly month (H->M->U->Z->H)
    _quarterly = ["H", "M", "U", "Z"]
    _default_back_idx = 0
    _default_back_year = _front_year or date.today().year
    if _front_month_code in _quarterly:
        _q_idx = _quarterly.index(_front_month_code)
        _next_q = _quarterly[(_q_idx + 1) % 4]
        _next_q_month = _code_to_month[_next_q]  # int month number
        _default_back_idx = _next_q_month - 1     # 0-based index into MONTH_NAMES
        if _next_q == "H" and _front_month_code == "Z":
            _default_back_year += 1

    sig_col1, sig_col2, sig_col3 = st.columns([1, 1, 2])

    with sig_col1:
        st.info(f"Current: **{_active_sym}**")

    with sig_col2:
        back_month_name = st.selectbox(
            "Roll To Month", MONTH_NAMES, index=_default_back_idx,
            key="signal_back_month",
        )
        back_year = st.number_input(
            "Roll To Year", min_value=2000, max_value=2099,
            value=_default_back_year, step=1, key="signal_back_year",
        )

    back_month_num = month_from_name(back_month_name)
    back_symbol = build_contract_symbol(ledger.instrument, back_month_num, back_year)

    with sig_col3:
        st.write("")
        if _front_month and _front_year and st.button(
            "Check Liquidity Crossover", key="check_roll_signal"
        ):
            with st.spinner("Analyzing Volume..."):
                vol_data = fetch_roll_volume(
                    instrument=ledger.instrument,
                    front_month=_front_month,
                    front_year=_front_year,
                    back_month=back_month_num,
                    back_year=back_year,
                )

            if vol_data is None:
                st.error(
                    f"Could not fetch volume for {_active_sym} vs {back_symbol}. "
                    f"Tickers might be missing on Yahoo Finance."
                )
            else:
                vm1, vm2, vm3 = st.columns(3)
                with vm1:
                    st.metric(
                        f"Front Vol ({vol_data.front_ticker})",
                        f"{vol_data.latest_front_vol:,}",
                    )
                with vm2:
                    st.metric(
                        f"Back Vol ({vol_data.back_ticker})",
                        f"{vol_data.latest_back_vol:,}",
                    )
                with vm3:
                    st.metric(
                        "Volume Ratio",
                        f"{vol_data.ratio:.2f}x",
                        delta="ROLL NOW" if vol_data.ratio > 1.0 else "HOLD",
                        delta_color="normal" if vol_data.ratio > 1.0 else "off",
                    )

                # Volume crossover chart
                vol_chart_df = pd.DataFrame({
                    "Date": vol_data.dates,
                    "Front": vol_data.front_volume,
                    "Back": vol_data.back_volume,
                }).set_index("Date")
                st.line_chart(vol_chart_df)

# ── Cumulative P&L Chart (Plotly) ─────────────────────────────────────

st.markdown("---")
st.subheader("Cumulative P&L Curve")

series = ledger.cumulative_pnl_series()
if series:
    df_chart = pd.DataFrame(series)

    # Append current unrealized data point
    if active and current_price > 0:
        live_pnl = ledger.true_pnl(current_price)
        if live_pnl is not None:
            df_chart = pd.concat([
                df_chart,
                pd.DataFrame([{
                    "date": pd.Timestamp.now().strftime("%Y-%m-%d"),
                    "cum_pnl": live_pnl,
                    "event": "current (unrealized)",
                    "contract": active.contract_symbol,
                    "roll_number": active.roll_number,
                }]),
            ], ignore_index=True)

    df_chart["date"] = pd.to_datetime(df_chart["date"])

    fig = px.line(
        df_chart,
        x="date",
        y="cum_pnl",
        markers=True,
        hover_data=["contract", "event"],
        title="True Account Value (Sawtooth Normalized)",
        labels={"cum_pnl": "Profit/Loss ($)", "date": "Date"},
    )
    fig.update_layout(hovermode="x unified")

    # Profit/loss background zones
    if not df_chart.empty:
        y_max = max(df_chart["cum_pnl"].max(), 100) * 1.2
        y_min = min(df_chart["cum_pnl"].min(), -100) * 1.2
        fig.add_hrect(y0=0, y1=y_max, fillcolor="green", opacity=0.05, line_width=0)
        fig.add_hrect(y0=y_min, y1=0, fillcolor="red", opacity=0.05, line_width=0)

    st.plotly_chart(fig, use_container_width=True)

# ── Roll History ──────────────────────────────────────────────────────

st.markdown("---")
st.subheader("History")

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
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
else:
    st.caption("No history.")

# ── Formula Reference ─────────────────────────────────────────────────

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
