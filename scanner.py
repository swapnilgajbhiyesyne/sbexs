import datetime as dt
import math
import sys
from typing import Dict, Any, List, Tuple, Optional
import requests
import pandas as pd

DERIBIT = "https://www.deribit.com/api/v2"

class BTCOptionsScanner:
    """Bitcoin Options Scanner for Deribit"""
    
    def __init__(self):
        self.btc_spot = None
    
    def phi(self, x: float) -> float:
        """Standard normal cumulative distribution function"""
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
    
    def lognormal_pop_threshold(self, S0: float, sigma: float, T_years: float, threshold: float, direction: str) -> float:
        """Calculate probability of profit using lognormal distribution"""
        if S0 <= 0 or sigma <= 0 or T_years <= 0 or threshold <= 0:
            return float('nan')
        z = (math.log(threshold / S0) + 0.5 * sigma * sigma * T_years) / (sigma * math.sqrt(T_years))
        p_le = self.phi(z)
        return p_le if direction == 'le' else (1.0 - p_le)
    
    def parse_instrument(self, instr: str) -> Tuple[Optional[dt.date], Optional[float], Optional[str]]:
        """Parse Deribit instrument name"""
        try:
            parts = instr.split("-")
            d = parts[1]
            strike = float(parts[2])
            opt_type = parts[3].upper()
            expiry = dt.datetime.strptime(d, "%d%b%y").date()
            return expiry, strike, opt_type
        except Exception:
            return None, None, None
    
    def get_btc_spot(self) -> float:
        """Get current BTC spot price from Deribit"""
        r = requests.get(f"{DERIBIT}/public/ticker", params={"instrument_name": "BTC-PERPETUAL"}, timeout=15)
        r.raise_for_status()
        data = r.json().get("result", {})
        for key in ("index_price", "mark_price", "last_price"):
            if key in data and data[key]:
                return float(data[key])
        return float(data.get("last_price", "nan"))
    
    def get_instruments(self) -> List[Dict[str, Any]]:
        """Get all BTC options instruments from Deribit"""
        r = requests.get(f"{DERIBIT}/public/get_instruments",
                         params={"currency": "BTC", "kind": "option", "expired": "false"},
                         timeout=30)
        r.raise_for_status()
        return r.json()["result"]
    
    def get_ticker(self, instr: str) -> Dict[str, Any]:
        """Get ticker data for a specific instrument"""
        r = requests.get(f"{DERIBIT}/public/ticker", params={"instrument_name": instr}, timeout=15)
        r.raise_for_status()
        return r.json()["result"]
    
    def estimate_mid(self, result: Dict[str, Any]) -> float:
        """Estimate mid price from ticker data"""
        bid = result.get("best_bid")
        ask = result.get("best_ask")
        mark = result.get("mark_price")
        if bid is not None and ask is not None and bid > 0 and ask > 0:
            return 0.5 * (bid + ask)
        if mark is not None and mark > 0:
            return float(mark)
        last = result.get("last_price")
        return float(last) if last is not None else float("nan")
    
    def scan(self, dte_max=None, expiry=None, side='both', delta_band=None, prem_min=None, 
             prem_max=None, premium_in_btc=False, limit=200, sort='pop_delta', desc=True) -> Dict[str, Any]:
        """
        Scan BTC options with given parameters
        
        Args:
            dte_max: Maximum days to expiry
            expiry: Specific expiry date (YYYY-MM-DD)
            side: 'calls', 'puts', or 'both'
            delta_band: Tuple of (min_delta, max_delta)
            prem_min: Minimum premium in USD
            prem_max: Maximum premium in USD
            premium_in_btc: Whether premiums are quoted in BTC
            limit: Maximum number of results to return
            sort: Column to sort by
            desc: Sort descending if True
            
        Returns:
            Dictionary with scan results
        """
        today = dt.date.today()
        
        # Get BTC spot price
        try:
            self.btc_spot = self.get_btc_spot()
        except Exception as e:
            raise Exception(f"Error fetching BTC spot price: {str(e)}")
        
        # Get instruments
        try:
            instruments = self.get_instruments()
        except Exception as e:
            raise Exception(f"Error fetching instruments: {str(e)}")
        
        rows = []
        
        for ins in instruments:
            name = ins.get("instrument_name")
            if not name:
                continue
            expiry_date, strike, opt_type = self.parse_instrument(name)
            if not expiry_date or strike is None:
                continue
            
            # Filter by expiry
            if expiry:
                try:
                    wanted = dt.datetime.strptime(expiry, "%Y-%m-%d").date()
                    if expiry_date != wanted:
                        continue
                except Exception:
                    raise Exception("Invalid expiry format, expected YYYY-MM-DD")
            elif dte_max is not None:
                dte = (expiry_date - today).days
                if dte < 0 or dte > dte_max:
                    continue
            
            # Filter by option type
            if side == "calls" and opt_type != "C":
                continue
            if side == "puts" and opt_type != "P":
                continue
            
            # Get ticker data
            try:
                ticker = self.get_ticker(name)
            except Exception:
                continue
            
            delta = ticker.get("greeks", {}).get("delta")
            mark_iv = ticker.get("mark_iv")
            premium_native = self.estimate_mid(ticker)
            
            # Convert premium to USD if needed
            if premium_in_btc:
                premium_usd = premium_native * self.btc_spot if premium_native == premium_native else float('nan')
            else:
                premium_usd = premium_native
            
            # Apply premium filters
            if prem_min is not None and (premium_usd != premium_usd or premium_usd < prem_min):
                continue
            if prem_max is not None and (premium_usd != premium_usd or premium_usd > prem_max):
                continue
            
            dte = max((expiry_date - today).days, 0)
            T_years = max(dte / 365.0, 1e-6)
            
            # Filter by delta band
            if delta_band:
                dmin, dmax = delta_band
                if delta is None:
                    continue
                if abs(delta) < dmin or abs(delta) > dmax:
                    continue
            
            # Calculate probabilities
            pop_delta = float('nan')
            pop_logN = float('nan')
            breakeven = float('nan')
            sigma = None
            
            if mark_iv is not None and mark_iv > 0:
                sigma = float(mark_iv)
            
            if delta is not None:
                pop_delta = 1.0 - abs(float(delta))
            
            # Calculate breakeven and lognormal POP
            if sigma and premium_usd and premium_usd > 0 and self.btc_spot and self.btc_spot > 0:
                if opt_type == "C":
                    breakeven = strike + premium_usd
                    pop_logN = self.lognormal_pop_threshold(self.btc_spot, sigma, T_years, breakeven, direction="le")
                else:
                    breakeven = max(strike - premium_usd, 1e-6)
                    pop_logN = self.lognormal_pop_threshold(self.btc_spot, sigma, T_years, breakeven, direction="ge")
            
            rows.append({
                "instrument": name,
                "type": "C" if opt_type == "C" else "P",
                "expiry": expiry_date.isoformat(),
                "dte": dte,
                "spot": self.btc_spot,
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
            return {
                'data': [],
                'btc_spot': self.btc_spot,
                'total_count': 0
            }
        
        # Sort results
        df = pd.DataFrame(rows)
        df = df.sort_values(by=sort, ascending=not desc, na_position="last")
        
        # Apply limit
        if limit:
            df = df.head(limit)
        
        return {
            'data': df.to_dict('records'),
            'btc_spot': self.btc_spot,
            'total_count': len(rows)
        }
