"""
MACROPARITY - Currency Fair Value Scanner
Combines macro fundamentals with price positioning across multiple timeframes.

Setup:
    pip install streamlit pandas yfinance

Run:
    streamlit run app.py
"""

import streamlit as st
import pandas as pd
import os
from datetime import datetime, timedelta, date

try:
    import yfinance as yf
    YF_OK = True
except ImportError:
    YF_OK = False

st.set_page_config(page_title="MacroParity", page_icon="🧭", layout="wide")

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
F_MACRO = os.path.join(DATA_DIR, "macro.csv")
F_BANKS = os.path.join(DATA_DIR, "banks.csv")
F_POS = os.path.join(DATA_DIR, "positions.csv")

# ============================================================
# DEFAULTS (as of end of July 2026)
# ============================================================
DEFAULT_MACRO = {
    "USD": {"rate": 3.75, "inflation": 3.5, "current_acc": -3.3, "outlook":  0.25},
    "EUR": {"rate": 2.25, "inflation": 2.8, "current_acc":  2.5, "outlook":  0.25},
    "GBP": {"rate": 3.75, "inflation": 2.6, "current_acc": -2.7, "outlook":  0.25},
    "JPY": {"rate": 1.00, "inflation": 1.7, "current_acc":  3.6, "outlook":  0.50},
    "CHF": {"rate": 0.00, "inflation": 0.5, "current_acc":  5.5, "outlook":  0.0},
    "AUD": {"rate": 3.60, "inflation": 3.7, "current_acc": -1.5, "outlook":  0.0},
    "NZD": {"rate": 2.50, "inflation": 4.1, "current_acc": -4.5, "outlook":  0.50},
    "CAD": {"rate": 2.25, "inflation": 2.8, "current_acc": -1.0, "outlook":  0.0},
}

DEFAULT_BANKS = {
    "USD": {"bank": "Fed", "last_meeting": "2026-07-29", "decision": "Hold 3.50-3.75",
            "vote": "9-3", "tone": "Hawkish",
            "note": "Three members dissented for a hike. Warsh dropped forward guidance entirely.",
            "next_meeting": "2026-09-16"},
    "EUR": {"bank": "ECB", "last_meeting": "2026-06-17", "decision": "Hike to 2.25",
            "vote": "-", "tone": "Hawkish",
            "note": "Raised 25bp in June. Market prices one more hike by year-end.",
            "next_meeting": "2026-09-10"},
    "GBP": {"bank": "BoE", "last_meeting": "2026-07-30", "decision": "Hold 3.75",
            "vote": "6-3", "tone": "Hawkish",
            "note": "Greene, Mann and Pill voted for 4.00. Inflation fell to 2.6 but BoE expects it to rise. Cuts remain distant, hike is a live risk.",
            "next_meeting": "2026-09-17"},
    "JPY": {"bank": "BoJ", "last_meeting": "2026-07-31", "decision": "Hold 1.00",
            "vote": "8-1", "tone": "Hawkish",
            "note": "Takata dissented for 1.25. Warned underlying inflation may exceed 2%. Ex-subsidies core already above target. Reuters poll: 70% expect at least 1.50 by Q2 2027.",
            "next_meeting": "2026-09-18"},
    "CHF": {"bank": "SNB", "last_meeting": "2026-06-18", "decision": "Hold 0.00",
            "vote": "-", "tone": "Neutral",
            "note": "Holding at zero. Inflation 0.5%, FX intervention remains an option.",
            "next_meeting": "2026-09-24"},
    "AUD": {"bank": "RBA", "last_meeting": "2026-07-07", "decision": "Hold 3.60",
            "vote": "-", "tone": "Neutral",
            "note": "Inflation at 3.7% sits above the target band but RBA remains cautious.",
            "next_meeting": "2026-08-11"},
    "NZD": {"bank": "RBNZ", "last_meeting": "2026-07-08", "decision": "Hike to 2.50",
            "vote": "-", "tone": "Hawkish",
            "note": "Raised 25bp in July. Swaps price another hike in September. Inflation 4.1% but largely fuel-driven; ex-fuel closer to 2.9%.",
            "next_meeting": "2026-08-19"},
    "CAD": {"bank": "BoC", "last_meeting": "2026-07-15", "decision": "Hold 2.25",
            "vote": "-", "tone": "Neutral",
            "note": "Held in July. Inflation at 2.8%.",
            "next_meeting": "2026-09-09"},
}

CURRENCIES = list(DEFAULT_MACRO.keys())
WINDOWS = {"1Y": 365, "5Y": 365 * 5, "10Y": 365 * 10}
MIN_GAP = 0.30

# Conventional market quoting order (base currency first)
QUOTE_ORDER = ["EUR", "GBP", "AUD", "NZD", "USD", "CAD", "CHF", "JPY"]


def market_pair(a, b):
    """Return (base, quote) in conventional market order."""
    ia = QUOTE_ORDER.index(a) if a in QUOTE_ORDER else 99
    ib = QUOTE_ORDER.index(b) if b in QUOTE_ORDER else 99
    return (a, b) if ia < ib else (b, a)


# ============================================================
# STORAGE
# ============================================================
def load_csv(path, default):
    if os.path.exists(path):
        try:
            return pd.read_csv(path, index_col=0).to_dict("index")
        except Exception:
            pass
    return {k: v.copy() for k, v in default.items()}


def save_csv(path, data):
    pd.DataFrame(data).T.to_csv(path)


def load_positions():
    if os.path.exists(F_POS):
        try:
            return pd.read_csv(F_POS)
        except Exception:
            pass
    return pd.DataFrame(columns=["Pair", "Side", "Entry", "Size", "Date", "Note"])


# ============================================================
# SCORING
# ============================================================
def z_score(s):
    sd = s.std()
    return s * 0 if (sd == 0 or pd.isna(sd)) else (s - s.mean()) / sd


def compute_scores(data, w_real, w_outlook, w_ca):
    df = pd.DataFrame(data).T
    for c in ["rate", "inflation", "current_acc", "outlook"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df.index.name = "Currency"
    df["real_rate"] = df["rate"] - df["inflation"]
    df["fwd_real"] = df["real_rate"] + df["outlook"]
    total = (w_real + w_outlook + w_ca) or 1
    df["SCORE"] = (
        z_score(df["fwd_real"]) * w_real
        + z_score(df["outlook"]) * w_outlook
        + z_score(df["current_acc"]) * w_ca
    ) / total
    return df.sort_values("SCORE", ascending=False)


def days_until(d):
    try:
        return (datetime.strptime(str(d), "%Y-%m-%d").date() - date.today()).days
    except Exception:
        return None


@st.cache_data(ttl=900, show_spinner=False)
def fetch_prices(symbols):
    """Download 10y daily history for a list of Yahoo FX tickers."""
    if not YF_OK or not symbols:
        return {}
    out = {}
    try:
        raw = yf.download(
            " ".join(symbols), period="10y", interval="1d",
            progress=False, auto_adjust=True, group_by="ticker",
        )
    except Exception:
        return {}
    if raw is None or len(raw) == 0:
        return {}

    now = datetime.now()
    for sym in symbols:
        try:
            if len(symbols) == 1:
                sub = raw
            else:
                if sym not in raw.columns.get_level_values(0):
                    continue
                sub = raw[sym]
            sub = sub.dropna(subset=["Close"])
            if len(sub) < 60:
                continue

            price = float(sub["Close"].iloc[-1])
            rec = {"price": price, "bars": len(sub)}
            for label, days in WINDOWS.items():
                cutoff = now - timedelta(days=days)
                w = sub[sub.index >= cutoff]
                if len(w) < 30:
                    rec[label] = None
                    continue
                hi = float(w["High"].max()) if "High" in w else float(w["Close"].max())
                lo = float(w["Low"].min()) if "Low" in w else float(w["Close"].min())
                span = hi - lo
                rec[label] = {
                    "hi": hi, "lo": lo,
                    "pos": (price - lo) / span * 100 if span > 0 else 50.0,
                    "mid": (hi + lo) / 2,
                    "p35": lo + span * 0.35,
                    "p65": lo + span * 0.65,
                    "years": round(len(w) / 252, 1),
                }
            out[sym] = rec
        except Exception:
            continue
    return out


def regime(p1, p5, p10):
    if p1 is None or p5 is None:
        return "NO DATA", ""
    if p10 is None:
        p10 = p5
    short_low, short_high = p1 < 35, p1 > 65
    long_high = (p5 > 65) or (p10 > 65)
    long_low = (p5 < 35) and (p10 < 35)
    if short_low and long_high:
        return "CONFLICT", "Near 1Y lows but high in the 5Y/10Y range"
    if short_high and long_low:
        return "CONFLICT", "Near 1Y highs but low in the 5Y/10Y range"
    if short_low and long_low:
        return "DEEP LOW", "Low across both short and long horizons"
    if short_high and long_high:
        return "DEEP HIGH", "High across both short and long horizons"
    if short_low:
        return "1Y LOW", "Low on the 1Y range, neutral longer term"
    if short_high:
        return "1Y HIGH", "High on the 1Y range, neutral longer term"
    return "NEUTRAL", "Mid-range"


def verdict(side, p1, reg, gap):
    if p1 is None:
        return "NO DATA", "Price data unavailable"
    if reg == "CONFLICT":
        return "TRAP", "Short and long horizons disagree. Avoid scaling in."
    if gap < MIN_GAP:
        return "WEAK", f"Macro gap ({gap:.2f}) is within noise. No divergence to trade."
    if side == "LONG":
        if p1 <= 35:
            return "ENTRY ZONE", "Macro favours the base currency and price sits low in range."
        if p1 >= 65:
            return "LATE", "Macro favours the base currency but price already ran."
        return "WAIT", "Price is mid-range."
    if p1 >= 65:
        return "ENTRY ZONE", "Macro favours the quote currency and price sits high in range."
    if p1 <= 35:
        return "LATE", "Macro favours the quote currency but price already fell."
    return "WAIT", "Price is mid-range."


# ============================================================
# UI
# ============================================================
st.title("🧭 MacroParity")
st.caption("Currency fair value scanner — macro fundamentals meet price positioning")

if not YF_OK:
    st.error("yfinance not installed. Run: pip install yfinance")

st.sidebar.header("Weights")
w_real = st.sidebar.slider("Forward real rate", 0.0, 1.0, 0.50, 0.05)
w_out = st.sidebar.slider("Rate path (outlook)", 0.0, 1.0, 0.30, 0.05)
w_ca = st.sidebar.slider("Current account", 0.0, 1.0, 0.20, 0.05)
st.sidebar.markdown("---")
excluded = st.sidebar.multiselect("Exclude currencies", CURRENCIES, default=[])
st.sidebar.markdown("---")
st.sidebar.caption(
    "This tool shows data and positioning. It does not provide investment advice."
)

macro = load_csv(F_MACRO, DEFAULT_MACRO)
banks = load_csv(F_BANKS, DEFAULT_BANKS)
active = {k: v for k, v in macro.items() if k not in excluded}
df = compute_scores(active, w_real, w_out, w_ca)

tab1, tab2, tab3, tab4 = st.tabs(["Scanner", "Central Banks", "Positions", "Data"])

# ---------------- TAB 4: DATA ----------------
with tab4:
    st.subheader("Macro inputs")
    st.caption("Sources: tradingeconomics.com/country-list — update monthly (25th suggested)")

    mdf = pd.DataFrame(macro).T
    mdf.index.name = "Currency"
    mdf = mdf.rename(columns={
        "rate": "Policy Rate (%)", "inflation": "Inflation (%)",
        "current_acc": "Current Acc (% GDP)", "outlook": "Expected Rate Change",
    })
    med = st.data_editor(mdf, width="stretch", num_rows="fixed", key="macro_ed")

    if st.button("Save macro data"):
        new = {}
        for c in med.index:
            new[c] = {
                "rate": med.loc[c, "Policy Rate (%)"],
                "inflation": med.loc[c, "Inflation (%)"],
                "current_acc": med.loc[c, "Current Acc (% GDP)"],
                "outlook": med.loc[c, "Expected Rate Change"],
            }
        save_csv(F_MACRO, new)
        st.success("Saved. Reload to apply.")

    st.markdown("---")
    st.subheader("Central bank notes")
    st.caption("Rationale behind the outlook column. Update after each decision.")

    bdf = pd.DataFrame(banks).T
    bdf.index.name = "Currency"
    bdf = bdf.rename(columns={
        "bank": "Bank", "last_meeting": "Last Meeting", "decision": "Decision",
        "vote": "Vote", "tone": "Tone", "note": "Note", "next_meeting": "Next Meeting",
    })
    bed = st.data_editor(
        bdf, width="stretch", num_rows="fixed", key="banks_ed",
        column_config={
            "Tone": st.column_config.SelectboxColumn(options=["Hawkish", "Neutral", "Dovish"]),
            "Note": st.column_config.TextColumn(width="large"),
        },
    )

    if st.button("Save bank notes"):
        nb = {}
        for c in bed.index:
            nb[c] = {
                "bank": bed.loc[c, "Bank"], "last_meeting": bed.loc[c, "Last Meeting"],
                "decision": bed.loc[c, "Decision"], "vote": bed.loc[c, "Vote"],
                "tone": bed.loc[c, "Tone"], "note": bed.loc[c, "Note"],
                "next_meeting": bed.loc[c, "Next Meeting"],
            }
        save_csv(F_BANKS, nb)
        st.success("Saved. Reload to apply.")

# ---------------- TAB 2: CENTRAL BANKS ----------------
with tab2:
    st.subheader("Policy stance and calendar")
    rows = []
    for c, b in banks.items():
        rows.append({
            "Currency": c, "Bank": b.get("bank"), "Tone": b.get("tone"),
            "Last Decision": b.get("decision"), "Vote": b.get("vote"),
            "Last Meeting": b.get("last_meeting"), "Next Meeting": b.get("next_meeting"),
            "Days": days_until(b.get("next_meeting")),
        })
    cal = pd.DataFrame(rows).sort_values("Days", na_position="last")

    def tone_color(v):
        if v == "Hawkish":
            return "background-color: #1e4620; color: #d4edda"
        if v == "Dovish":
            return "background-color: #4a1c1c; color: #f8d7da"
        return ""

    st.dataframe(cal.style.map(tone_color, subset=["Tone"]), width="stretch", hide_index=True)

    soon = cal[(cal["Days"].notna()) & (cal["Days"] <= 14) & (cal["Days"] >= 0)]
    if len(soon) > 0:
        st.warning(
            "**Meetings within 14 days:** "
            + ", ".join(f"{r['Bank']} ({int(r['Days'])}d)" for _, r in soon.iterrows())
        )

    st.markdown("---")
    for c in df.index:
        if c not in banks:
            continue
        b = banks[c]
        d = days_until(b.get("next_meeting"))
        dtxt = f" · next {b.get('next_meeting')} ({d}d)" if d is not None else ""
        with st.expander(f"{c} — {b.get('bank')} · {b.get('tone')} · score {df.loc[c,'SCORE']:.2f}"):
            st.write(f"**{b.get('decision')}** on {b.get('last_meeting')} · vote {b.get('vote')}{dtxt}")
            st.write(b.get("note"))
            st.caption(
                f"Model inputs — rate {macro.get(c,{}).get('rate')}%, "
                f"inflation {macro.get(c,{}).get('inflation')}%, "
                f"outlook {macro.get(c,{}).get('outlook')}"
            )

# ---------------- TAB 1: SCANNER ----------------
with tab1:
    st.subheader("Currency ranking")
    show = df[["rate", "inflation", "real_rate", "outlook", "fwd_real", "current_acc", "SCORE"]].round(2)
    show.columns = ["Rate", "Infl", "Real", "Outlook", "Fwd Real", "CA", "SCORE"]
    show["Tone"] = [banks.get(c, {}).get("tone", "-") for c in show.index]
    show["Next Mtg"] = [banks.get(c, {}).get("next_meeting", "-") for c in show.index]
    st.dataframe(show.style.background_gradient(subset=["SCORE"], cmap="RdYlGn"), width="stretch")

    if st.button("Run scan", type="primary"):
        st.session_state["scan"] = True

    if st.session_state.get("scan") and YF_OK:
        pairs = []
        cur = list(df.index)
        for i, a in enumerate(cur):
            for b in cur[i + 1:]:
                base, quote = market_pair(a, b)
                gap = df.loc[base, "SCORE"] - df.loc[quote, "SCORE"]
                side = "LONG" if gap > 0 else "SHORT"
                pairs.append({"base": base, "quote": quote, "gap": abs(gap), "side": side})

        symbols = [f"{p['base']}{p['quote']}=X" for p in pairs]
        with st.spinner("Fetching prices..."):
            prices = fetch_prices(symbols)

        rows = []
        for p in pairs:
            sym = f"{p['base']}{p['quote']}=X"
            if sym not in prices or not prices[sym].get("1Y"):
                continue
            d = prices[sym]
            pos = {k: (d[k]["pos"] if d.get(k) else None) for k in WINDOWS}
            reg, reg_note = regime(pos["1Y"], pos["5Y"], pos["10Y"])
            vd, vd_note = verdict(p["side"], pos["1Y"], reg, p["gap"])

            d1 = d.get("1Y", {})
            if d1:
                window_end = d1["p35"] if p["side"] == "LONG" else d1["p65"]
                late_line = d1["p65"] if p["side"] == "LONG" else d1["p35"]
            else:
                window_end = late_line = None

            db = days_until(banks.get(p["base"], {}).get("next_meeting"))
            dq = days_until(banks.get(p["quote"], {}).get("next_meeting"))
            dl = [x for x in [db, dq] if x is not None and x >= 0]

            rows.append({
                "Pair": f"{p['base']}{p['quote']}",
                "Side": p["side"],
                "VERDICT": vd,
                "Gap": round(p["gap"], 3),
                "Price": round(d["price"], 5),
                "Entry Limit": round(window_end, 5) if window_end else None,
                "Target": round(late_line, 5) if late_line else None,
                "1Y %": round(pos["1Y"], 1) if pos["1Y"] is not None else None,
                "5Y %": round(pos["5Y"], 1) if pos["5Y"] is not None else None,
                "10Y %": round(pos["10Y"], 1) if pos["10Y"] is not None else None,
                "Next Mtg": min(dl) if dl else None,
                "Regime": reg,
                "1Y Low": round(d1.get("lo", 0), 5) if d1 else None,
                "1Y Mid": round(d1.get("mid", 0), 5) if d1 else None,
                "1Y High": round(d1.get("hi", 0), 5) if d1 else None,
                "Note": vd_note,
            })

        if rows:
            s = pd.DataFrame(rows)

            def priority(r):
                p1 = r["1Y %"] if r["1Y %"] is not None else 50
                return r["Gap"] * ((100 - p1) / 100 if r["Side"] == "LONG" else p1 / 100)

            s["Priority"] = s.apply(priority, axis=1)
            s = s.sort_values("Priority", ascending=False).reset_index(drop=True)
            st.session_state["res"] = s

            COLS = ["Pair", "Side", "VERDICT", "Gap", "Price", "Entry Limit", "Target",
                    "1Y %", "5Y %", "10Y %", "Next Mtg"]

            st.markdown("### Entry zone")
            st.caption("Macro direction and price positioning agree.")
            ez = s[s["VERDICT"] == "ENTRY ZONE"]
            if len(ez) > 0:
                st.dataframe(ez[COLS], width="stretch", hide_index=True)
                near = ez[ez["Next Mtg"].notna() & (ez["Next Mtg"] <= 10)]
                if len(near) > 0:
                    st.warning(
                        "Central bank meeting within 10 days for: " + ", ".join(near["Pair"])
                    )
            else:
                st.info("Nothing in this category right now.")

            st.markdown("### Trap")
            st.caption("Short and long horizons disagree — scaling in is risky here.")
            tr = s[s["VERDICT"] == "TRAP"]
            if len(tr) > 0:
                st.dataframe(tr[COLS], width="stretch", hide_index=True)
            else:
                st.info("Nothing in this category right now.")

            st.markdown("### All pairs")
            st.dataframe(s[COLS + ["Regime"]], width="stretch", hide_index=True)
        else:
            st.warning("No data returned. Try again in a moment.")

    if "res" in st.session_state:
        st.markdown("---")
        st.subheader("Pair detail")
        s = st.session_state["res"]
        pick = st.selectbox("Select pair", s["Pair"].tolist())
        r = s[s["Pair"] == pick].iloc[0]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Price", r["Price"])
        c2.metric("1Y position", f"{r['1Y %']}%")
        c3.metric("5Y position", f"{r['5Y %']}%")
        c4.metric("10Y position", f"{r['10Y %']}%")

        msg = f"**{r['VERDICT']}** · macro side: {r['Side']} (gap {r['Gap']})\n\n{r['Note']}"
        if r["VERDICT"] == "ENTRY ZONE":
            st.success(msg)
        elif r["VERDICT"] == "TRAP":
            st.error(msg)
        elif r["VERDICT"] == "LATE":
            st.warning(msg)
        else:
            st.info(msg)

        if r["Next Mtg"] is not None and r["Next Mtg"] <= 14:
            st.warning(f"Central bank meeting in {int(r['Next Mtg'])} days.")

        if r["Entry Limit"] is not None:
            direction = "above" if r["Side"] == "SHORT" else "below"
            st.markdown(
                f"Price is **{r['Price']}**. The entry window stays open while price is "
                f"{direction} **{r['Entry Limit']}** (the 35/65 band edge). "
                f"**{r['Target']}** marks where the macro gap is considered priced in — "
                f"a natural profit-taking area."
            )

        st.dataframe(pd.DataFrame([{
            "1Y Low": r["1Y Low"], "Entry Limit": r["Entry Limit"],
            "1Y Mid": r["1Y Mid"], "Target": r["Target"], "1Y High": r["1Y High"],
        }]), width="stretch", hide_index=True)

# ---------------- TAB 3: POSITIONS ----------------
with tab3:
    st.subheader("Your positions")
    st.caption("Enter open positions to check them against the macro backdrop.")

    pos = load_positions()
    ped = st.data_editor(
        pos, width="stretch", num_rows="dynamic", key="pos_ed",
        column_config={
            "Pair": st.column_config.TextColumn(help="e.g. EURGBP"),
            "Side": st.column_config.SelectboxColumn(options=["LONG", "SHORT"]),
            "Entry": st.column_config.NumberColumn(format="%.5f"),
            "Size": st.column_config.NumberColumn(format="%.2f"),
        },
    )
    if st.button("Save positions"):
        ped.to_csv(F_POS, index=False)
        st.success("Saved.")

    if len(ped) > 0 and "res" in st.session_state:
        st.markdown("---")
        s = st.session_state["res"]
        for _, p in ped.iterrows():
            sym = str(p.get("Pair", "")).strip().upper()
            if not sym:
                continue
            row = s[s["Pair"].str.upper() == sym]
            if len(row) == 0:
                st.info(f"**{sym}** — not found in the last scan.")
                continue
            r = row.iloc[0]
            aligned = str(p.get("Side", "")).upper() == r["Side"]
            head = f"**{sym} {p.get('Side')}** · entry {p.get('Entry')} · size {p.get('Size')}"
            body = (
                f"Macro side: {r['Side']} (gap {r['Gap']}) · price {r['Price']} · "
                f"1Y {r['1Y %']}%, 10Y {r['10Y %']}% · verdict: {r['VERDICT']}"
            )
            if r["Gap"] < MIN_GAP:
                st.info(f"{head}\n\n{body}\n\nMacro divergence is weak — no clear backdrop either way.")
            elif aligned:
                st.success(f"{head}\n\n{body}\n\nMacro backdrop supports this side.")
            else:
                st.error(f"{head}\n\n{body}\n\nMacro backdrop works against this side.")
    elif len(ped) > 0:
        st.info("Run a scan first, then come back.")

st.markdown("---")
st.caption(
    "MacroParity shows where currencies stand on macro fundamentals and where price sits "
    "in its historical range. Divergences can persist for months or years — this is a "
    "research tool, not investment advice. Price data via Yahoo Finance."
)
