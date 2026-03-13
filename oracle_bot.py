#!/usr/bin/env python3

"""
ORACLE BOT — FINAL VERSION
Paper trading crypto bot
"""

import time
import requests
from datetime import datetime

# ───────── CONFIG ─────────

class Config:

    PAIRS = ["BTCUSDT","ETHUSDT","SOLUSDT"]
    
    ORDER_USD = 10
    
    START_BALANCE = 1000
    
    MAX_OPEN_TRADES = 2

    STOP_LOSS_PCT = 3
    TAKE_PROFIT_PCT = 5

    ANALYSIS_INTERVAL = 300

BINANCE = "https://api.binance.com"


# ───────── LOGGER ─────────

def log(tag,msg):

    ts=datetime.now().strftime("%H:%M:%S")

    print(f"{ts} [{tag}] {msg}")


# ───────── BINANCE CLIENT ─────────

class BinanceClient:

    def get_price(self,symbol):

        try:

            r=requests.get(
                f"{BINANCE}/api/v3/ticker/price",
                params={"symbol":symbol},
                timeout=5
            )

            return float(r.json()["price"])

        except:

            return None


    def get_klines(self,symbol,interval="1h",limit=100):

        try:

            r=requests.get(
                f"{BINANCE}/api/v3/klines",
                params={
                    "symbol":symbol,
                    "interval":interval,
                    "limit":limit
                },
                timeout=5
            )

            return r.json()

        except:

            return []


# ───────── TECHNICAL ANALYSIS ─────────

class TechnicalAnalysis:

    @staticmethod
    def from_klines(klines):

        if len(klines) < 30:
            return {}

        closes=[float(k[4]) for k in klines]

        highs=[float(k[2]) for k in klines]

        lows=[float(k[3]) for k in klines]

        vols=[float(k[5]) for k in klines]

        rsi=TechnicalAnalysis.rsi(closes)

        ma7=TechnicalAnalysis.ma(closes,7)
        ma21=TechnicalAnalysis.ma(closes,21)
        ma50=TechnicalAnalysis.ma(closes,50)

        vol_avg=sum(vols[-20:])/20
        vol_ratio=vols[-1]/vol_avg if vol_avg>0 else 1

        return {

            "rsi":rsi,
            "ma7":ma7,
            "ma21":ma21,
            "ma50":ma50,
            "price":closes[-1],
            "high_24h":max(highs[-24:]),
            "low_24h":min(lows[-24:]),
            "vol_ratio":vol_ratio
        }


    @staticmethod
    def rsi(prices,period=14):

        if len(prices)<period+1:
            return None

        gains=0
        losses=0

        for i in range(1,period+1):

            d=prices[i]-prices[i-1]

            if d>0:
                gains+=d
            else:
                losses+=abs(d)

        avg_gain=gains/period
        avg_loss=losses/period

        if avg_loss==0:
            return 100

        rs=avg_gain/avg_loss

        return 100-(100/(1+rs))


    @staticmethod
    def ma(prices,period):

        if len(prices)<period:
            return None

        return sum(prices[-period:])/period


# ───────── STRATEGY ENGINE ─────────

class StrategyEngine:

    @staticmethod
    def decide(symbol,ta):

        if not ta:
            return "HOLD"

        votes=[]

        rsi=ta["rsi"]
        ma7=ta["ma7"]
        ma21=ta["ma21"]
        ma50=ta["ma50"]

        price=ta["price"]

        high=ta["high_24h"]
        low=ta["low_24h"]

        # RSI strategy

        if rsi:

            if rsi<30:
                votes.append("BUY")

            elif rsi>70:
                votes.append("SELL")

        # Trend strategy

        if ma7 and ma21 and ma50:

            if ma7>ma21>ma50:
                votes.append("BUY")

            elif ma7<ma21<ma50:
                votes.append("SELL")

        # Breakout strategy

        if price>=high*0.999:
            votes.append("BUY")

        elif price<=low*1.001:
            votes.append("SELL")

        buy=votes.count("BUY")
        sell=votes.count("SELL")

        if buy>=2:
            return "BUY"

        if sell>=2:
            return "SELL"

        return "HOLD"


# ───────── TRADE MANAGER ─────────

class TradeManager:

    def __init__(self):

        self.open_trades = {}

        self.history = []

        self.balance = Config.START_BALANCE



    def can_open(self,symbol):

        return len(self.open_trades)<Config.MAX_OPEN_TRADES and symbol not in self.open_trades


    def open_trade(self,symbol,price):

        stop=price*(1-Config.STOP_LOSS_PCT/100)
        target=price*(1+Config.TAKE_PROFIT_PCT/100)

        self.open_trades[symbol]={

            "entry":price,
            "stop":stop,
            "target":target,
            "usdt":Config.ORDER_USD
        }

        log("TRADE",f"OPEN {symbol} @ {price:.2f}")


    def check_exit(self,symbol,price):

        t=self.open_trades.get(symbol)

        if not t:
            return None

        if price<=t["stop"]:
            return "STOP"

        if price>=t["target"]:
            return "TP"

        return None


    def close_trade(self,symbol,price,reason):

        t=self.open_trades.pop(symbol)

        pnl_pct=(price-t["entry"])/t["entry"]*100
        pnl_usd=t["usdt"]*pnl_pct/100

        self.history.append(pnl_usd)
        self.balance += pnl_usd


        log("TRADE",f"CLOSE {symbol} {pnl_pct:+.2f}% ${pnl_usd:+.2f} ({reason})")


    def stats(self):

        trades = len(self.history)

        if trades == 0:

            return f"""
    ──────── BOT STATUS ────────

    Capital inicial: ${Config.START_BALANCE:.2f}
    Capital actual:  ${self.balance:.2f}

    Trades cerrados: 0
    Trades abiertos: {len(self.open_trades)}
    """

        wins = [t for t in self.history if t > 0]

        winrate = len(wins) / trades * 100

        pnl_total = self.balance - Config.START_BALANCE

        pnl_pct = pnl_total / Config.START_BALANCE * 100

        return f"""
    ──────── BOT STATUS ────────

    Capital inicial: ${Config.START_BALANCE:.2f}
    Capital actual:  ${self.balance:.2f}

    Ganancia total:  ${pnl_total:+.2f} ({pnl_pct:+.2f}%)

    Trades cerrados: {trades}
    Winrate:         {winrate:.1f}%
    Trades abiertos: {len(self.open_trades)}
    """



# ───────── ORACLE BOT ─────────

class OracleBot:

    def __init__(self):

        self.binance=BinanceClient()

        self.trades=TradeManager()


    def analyze_pair(self,symbol):

        klines=self.binance.get_klines(symbol)

        price=self.binance.get_price(symbol)

        if not klines or not price:

            log("DATA",f"{symbol} no data")

            return

        ta=TechnicalAnalysis.from_klines(klines)

        ta["price"]=price

        decision=StrategyEngine.decide(symbol,ta)

        log("AI",f"{symbol} → {decision}")

        if decision=="BUY":

            if self.trades.can_open(symbol):

                self.trades.open_trade(symbol,price)

        elif decision=="SELL":

            if symbol in self.trades.open_trades:

                self.trades.close_trade(symbol,price,"signal")


    def check_positions(self):

        for symbol in list(self.trades.open_trades.keys()):

            price=self.binance.get_price(symbol)

            if not price:
                continue

            reason=self.trades.check_exit(symbol,price)

            if reason:

                self.trades.close_trade(symbol,price,reason)


    def run(self):

        cycle=0

        while True:

            cycle+=1

            print(f"\n──── CYCLE {cycle} ────")

            print(self.trades.stats())

            self.check_positions()

            for symbol in Config.PAIRS:

                self.analyze_pair(symbol)

                time.sleep(1)

            log("BOT",f"sleep {Config.ANALYSIS_INTERVAL}s")

            time.sleep(Config.ANALYSIS_INTERVAL)


# ───────── MAIN ─────────

if __name__=="__main__":

    bot=OracleBot()

    try:

        bot.run()

    except KeyboardInterrupt:

        print("\nBot detenido")
