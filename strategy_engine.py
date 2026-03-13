# ─── STRATEGY ENGINE ─────────────────────────────────────────────────────────
from typing import Dict, List

class StrategyEngine:

    @staticmethod
    def decide(symbol: str, ta: Dict) -> Dict:
        """
        Ejecuta múltiples estrategias y toma una decisión por votación.
        """
        if not ta:
            return {"action": "HOLD", "confidence": 0, "signals": ["No TA data"]}

        votes = []
        signals = []

        rsi_vote, rsi_sig = StrategyEngine.rsi_reversal(ta)
        trend_vote, trend_sig = StrategyEngine.trend_follow(ta)
        breakout_vote, breakout_sig = StrategyEngine.breakout(symbol, ta)

        votes += [rsi_vote, trend_vote, breakout_vote]
        signals += rsi_sig + trend_sig + breakout_sig

        buy = votes.count("BUY")
        sell = votes.count("SELL")

        if buy > sell and buy >= 2:
            action = "BUY"
        elif sell > buy and sell >= 2:
            action = "SELL"
        else:
            action = "HOLD"

        confidence = int((max(buy, sell) / len(votes)) * 100)

        return {
            "action": action,
            "confidence": confidence,
            "votes": votes,
            "signals": signals
        }

    # ─── STRATEGY 1 — RSI MEAN REVERSION ─────────────────────────────────────
    @staticmethod
    def rsi_reversal(ta: Dict):

        rsi = ta.get("rsi")
        signals = []

        if rsi is None:
            return "HOLD", signals

        if rsi < 30:
            signals.append(f"RSI {rsi:.1f} oversold → BUY")
            return "BUY", signals

        if rsi > 70:
            signals.append(f"RSI {rsi:.1f} overbought → SELL")
            return "SELL", signals

        return "HOLD", signals


    # ─── STRATEGY 2 — TREND FOLLOW ───────────────────────────────────────────
    @staticmethod
    def trend_follow(ta: Dict):

        ma7 = ta.get("ma7")
        ma21 = ta.get("ma21")
        ma50 = ta.get("ma50")

        signals = []

        if not (ma7 and ma21 and ma50):
            return "HOLD", signals

        if ma7 > ma21 > ma50:
            signals.append("Trend bullish MA7>MA21>MA50")
            return "BUY", signals

        if ma7 < ma21 < ma50:
            signals.append("Trend bearish MA7<MA21<MA50")
            return "SELL", signals

        return "HOLD", signals


    # ─── STRATEGY 3 — BREAKOUT ───────────────────────────────────────────────
    @staticmethod
    def breakout(symbol: str, ta: Dict):

        price = ta.get("price")
        high = ta.get("high_24h")
        low = ta.get("low_24h")

        signals = []

        if not price or not high or not low:
            return "HOLD", signals

        if price >= high * 0.999:
            signals.append("24h breakout ↑")
            return "BUY", signals

        if price <= low * 1.001:
            signals.append("24h breakdown ↓")
            return "SELL", signals

        return "HOLD", signals
