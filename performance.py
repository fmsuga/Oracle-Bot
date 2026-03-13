# ─── PERFORMANCE ANALYZER ────────────────────────────────────────────────────

class PerformanceAnalyzer:

    @staticmethod
    def stats(history):

        if not history:
            return {
                "trades": 0,
                "winrate": 0,
                "pnl": 0
            }

        wins = [t for t in history if t["pnl_usd"] > 0]

        total_pnl = sum(t["pnl_usd"] for t in history)
        winrate = len(wins) / len(history) * 100

        return {
            "trades": len(history),
            "winrate": winrate,
            "pnl": total_pnl
        }
