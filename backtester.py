#!/usr/bin/env python3

"""
ORACLE BOT BACKTESTER
Simula trades usando datos históricos de Binance
"""

import requests
import time
from datetime import datetime

from strategy_engine import StrategyEngine
from oracle_bot import TechnicalAnalysis


BINANCE = "https://api.binance.com"


# ───────────────── DATA LOADER ─────────────────

def load_klines(symbol="BTCUSDT", interval="1h", limit=1000):

    print(f"Cargando datos {symbol}...")

    r = requests.get(
        f"{BINANCE}/api/v3/klines",
        params={
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        },
        timeout=10
    )

    return r.json()


# ───────────────── BACKTEST ENGINE ─────────────────

class Backtester:

    def __init__(self, symbol="BTCUSDT", capital=1000):

        self.symbol = symbol
        self.initial_capital = capital
        self.capital = capital

        self.position = None
        self.trades = []

    def run(self):

        klines = load_klines(self.symbol)

        for i in range(60, len(klines)):

            window = klines[:i]

            ta = TechnicalAnalysis.from_klines(window)

            if not ta:
                continue

            price = float(window[-1][4])

            decision = StrategyEngine.decide(self.symbol, ta)

            action = decision["action"]

            self.process(action, price)

        self.report()

    # ───────────────── TRADE SIMULATION ─────────────────

    def process(self, action, price):

        if action == "BUY" and self.position is None:

            size = self.capital * 0.1

            self.position = {
                "entry": price,
                "size": size
            }

            print(f"BUY {price}")

        elif action == "SELL" and self.position:

            entry = self.position["entry"]
            size = self.position["size"]

            pnl_pct = (price - entry) / entry
            pnl = size * pnl_pct

            self.capital += pnl

            self.trades.append(pnl)

            print(f"SELL {price}  PnL {pnl:.2f}")

            self.position = None

    # ───────────────── REPORT ─────────────────

    def report(self):

        total = sum(self.trades)

        wins = [t for t in self.trades if t > 0]

        if self.trades:
            winrate = len(wins) / len(self.trades) * 100
        else:
            winrate = 0

        print("\n──────── BACKTEST RESULT ────────")

        print("Symbol:", self.symbol)
        print("Trades:", len(self.trades))
        print("Winrate:", f"{winrate:.1f}%")
        print("Total PnL:", f"${total:.2f}")
        print("Final capital:", f"${self.capital:.2f}")


# ───────────────── RUN ─────────────────

if __name__ == "__main__":

    bt = Backtester("BTCUSDT", 1000)

    bt.run()
