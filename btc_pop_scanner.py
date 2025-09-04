
#!/usr/bin/env python3
"""
btc_pop_scanner.py (premium USD normalization)
----------------------------------------------
Adds --prem-min and --prem-max (USD) filters and a flag --premium-in-btc to
convert native premiums (BTC) to USD using current BTC spot.

Examples:
  USD-native premiums (Deribit-style):
    python btc_pop_scanner.py --dte-max 7 --prem-min 50 --prem-max 100

  Premiums quoted in BTC (set the flag to convert to USD first):
    python btc_pop_scanner.py --dte-max 7 --premium-in-btc --prem-min 50 --prem-max 100
"""

import argparse
import datetime as dt
import math
import sys
from typing import Dict, Any, List, Tuple

import requests
import pandas as pd

DERIBIT = "https://www.deribit.com/api/v2"


def phi(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def lognormal_pop_threshold(S0: float, sigma: float, T_years: float, threshold: float, direction: str) -> float:
    if S0 <= 0 or sigma <= 0 or T_years <= 0 or threshold <= 0:
        return float('nan')
    z = (math.log(threshold / S0) + 0.5 * sigma * sigma * T_years) / (sigma * math.sqrt(T_years))
    p_le = phi(z)
    return p_le if direction == 'le' else (1.0 - p_le)


def parse_instrument(instr: str) -> Tuple[dt.date, float, str]:
    try:
        parts = instr.split("-")
        d = parts[1]
        strike = float(parts[2])
        opt_type = parts[3].upper()
        expiry = dt.datetime.strptime(d, "%d%b%y").date()
        return expiry, strike, opt_type
    except Exception:
        return None, None, None


def get_btc_spot() -> float:
    r = requests.get(f"{DERIBIT}/public/ticker", params={"instrument_name": "BTC-PERPETUAL"}, timeout=15)
    r.raise_for_status()
    data = r.json().get("result", {})
    for key in ("index_price", "mark_price", "last_price"):
        if key in data and data[key]:
            return float(data[key])
    return float(data.get("last_price", "nan"))


def get_instruments() -> List[Dict[str, Any]]:
    r = requests.get(f"{DERIBIT}/public/get_instruments",
                     params={"currency": "BTC", "kind": "option", "expired": "false"},
                     timeout=30)
    r.raise_for_status()
    return r.json()["result"]


def get_ticker(instr: str) -> Dict[str, Any]:
    r = requests.get(f"{DERIBIT}/public/ticker", params={"instrument_name": instr}, timeout=15)
    r.raise_for_status()
    return r.json()["result"]


def estimate_mid(result: Dict[str, Any]) -> float:
    bid = result.get("best_bid")
    ask = result.get("best_ask")
    mark = result.get("mark_price")
    if bid is not None and ask is not None and bid > 0 and ask > 0:
        return 0.5 * (bid + ask)
    if mark is not None and mark > 0:
        return float(mark)
    last = result.get("last_price")
    return float(last) if last is not None else float("nan")


def main():
    ap = argparse.ArgumentParser(description="BTC OTM Option POP Scanner (Deribit) with Premium USD Filter")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--dte-max", type=int, help="Max days to expiry (e.g., 7)")
    group.add_argument("--expiry", type=str, help="Specific expiry date YYYY-MM-DD to include only that date")
    ap.add_argument("--side", choices=["calls", "puts", "both"], default="both", help="Which side(s) to show")
    ap.add_argument("--delta-band", nargs=2, type=float, metavar=("MIN","MAX"),
                    help="Filter by absolute delta band (e.g., 0.10 0.30)")
    ap.add_argument("--prem-min", type=float, default=None, help="Minimum premium filter in USD (e.g., 50)")
    ap.add_argument("--prem-max", type=float, default=None, help="Maximum premium filter in USD (e.g., 100)")
    ap.add_argument("--premium-in-btc", action="store_true",
                    help="Treat fetched premium as BTC and convert to USD via spot before filtering/displaying")
    ap.add_argument("--limit", type=int, default=200, help="Max rows to print")
    ap.add_argument("--sort", type=str, default="pop_delta",
                    choices=["pop_delta","pop_logN","iv","dte","strike","premium_usd","premium_native","breakeven"],
                    help="Sort by column")
    ap.add_argument("--desc", action="store_true", help="Sort descending")
    ap.add_argument("--export", type=str, help="Export CSV filename")
    args = ap.parse_args()

    today = dt.date.today()

    try:
        S0 = get_btc_spot()
    except Exception as e:
        print(f"Error fetching BTC spot: {e}", file=sys.stderr)
        sys.exit(2)

    try:
        instruments = get_instruments()
    except Exception as e:
        print(f"Error fetching instruments: {e}", file=sys.stderr)
        sys.exit(2)

    rows = []
    for ins in instruments:
        name = ins.get("instrument_name")
        expiry, strike, opt_type = parse_instrument(name)
        if not expiry:
            continue

        if args.expiry:
            try:
                wanted = dt.datetime.strptime(args.expiry, "%Y-%m-%d").date()
                if expiry != wanted:
                    continue
            except Exception:
                print("Invalid --expiry format, expected YYYY-MM-DD", file=sys.stderr)
                sys.exit(2)
        elif args.dte_max is not None:
            dte = (expiry - today).days
            if dte < 0 or dte > args.dte_max:
                continue

        if args.side == "calls" and opt_type != "C":
            continue
        if args.side == "puts" and opt_type != "P":
            continue

        try:
            t = get_ticker(name)
        except Exception:
            continue

        delta = t.get("greeks", {}).get("delta")
        mark_iv = t.get("mark_iv")
        premium_native = estimate_mid(t)  # as fetched (native units, usually USD on Deribit)

        # Convert premium to USD if user indicates native is BTC
        if args.premium_in_btc:
            premium_usd = premium_native * S0 if premium_native == premium_native else float('nan')
        else:
            premium_usd = premium_native  # assume already USD

        # Apply USD filter
        if args.prem_min is not None and (premium_usd != premium_usd or premium_usd < args.prem_min):
            continue
        if args.prem_max is not None and (premium_usd != premium_usd or premium_usd > args.prem_max):
            continue

        dte = max((expiry - today).days, 0)
        T_years = max(dte / 365.0, 1e-6)

        if args.delta_band:
            dmin, dmax = args.delta_band
            if delta is None:
                continue
            if abs(delta) < dmin or abs(delta) > dmax:
                continue

        pop_delta = float('nan')
        pop_logN = float('nan')
        breakeven = float('nan')
        sigma = None

        if mark_iv is not None and mark_iv > 0:
            sigma = float(mark_iv)

        if delta is not None:
            pop_delta = 1.0 - abs(float(delta))

        # Breakeven must use the same currency as strike/spot: USD.
        # If premium_native is BTC, we use premium_usd for breakeven math.
        if sigma and premium_usd and premium_usd > 0 and S0 and S0 > 0:
            if opt_type == "C":
                breakeven = strike + premium_usd
                pop_logN = lognormal_pop_threshold(S0, sigma, T_years, breakeven, direction="le")
            else:
                breakeven = max(strike - premium_usd, 1e-6)
                pop_logN = lognormal_pop_threshold(S0, sigma, T_years, breakeven, direction="ge")

        rows.append({
            "instrument": name,
            "type": "C" if opt_type == "C" else "P",
            "expiry": expiry.isoformat(),
            "dte": dte,
            "spot": S0,
            "strike": strike,
            "iv": sigma if sigma is not None else float('nan'),
            "delta": float(delta) if delta is not None else float('nan'),
            "premium_native": float(premium_native) if premium_native is not None else float('nan'),
            "premium_usd": float(premium_usd) if premium_usd == premium_usd else float('nan'),
            "breakeven": float(breakeven) if breakeven == breakeven else float('nan'),
            "pop_delta": float(pop_delta) if pop_delta == pop_delta else float('nan'),
            "pop_logN": float(pop_logN) if pop_logN == pop_logN else float('nan'),
        })

    if not rows:
        print("No options found with the given filters.")
        sys.exit(0)

    df = pd.DataFrame(rows)
    df = df.sort_values(by=args.sort, ascending=not args.desc, na_position="last")
    if args.limit:
        df_print = df.head(args.limit).copy()
    else:
        df_print = df

    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 200)
    print(df_print.to_string(index=False,
                             formatters={
                                 "iv": "{:.2%}".format,
                                 "delta": "{:.3f}".format,
                                 "premium_native": "{:.8f}".format,
                                 "premium_usd": "{:.2f}".format,
                                 "pop_delta": "{:.2%}".format,
                                 "pop_logN": "{:.2%}".format,
                             }))

    if args.export:
        df.to_csv(args.export, index=False)
        print(f"\nSaved full scan to {args.export}")
        print("Tip: Load in Excel/Sheets and filter by POP, DTE, IV, etc.")


if __name__ == "__main__":
    main()
