#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════╗
║           ORACLE BOT v2 — Market Scanner             ║
║  Escanea top 30 USDT por volumen cada ciclo          ║
║  Análisis: RSI · MA · Bollinger · MACD · Momentum    ║
╚══════════════════════════════════════════════════════╝
"""

import time
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed


# ───────────────────────────────────────────────────────
#  CONFIG
# ───────────────────────────────────────────────────────

class Config:

    # ── Universo de mercado ────────────────────────────
    TOP_N_PAIRS       = 30
    MIN_VOLUME_USD    = 5_000_000

    EXCLUDE = {
        "USDCUSDT","BUSDUSDT","TUSDUSDT","USDTUSDT",
        "FDUSDUSDT","DAIUSDT","EURUSDT","PAXUSDT",
        "USTUSDT","FRAXUSDT","SUSDEUSDT","USDEUSDT",
    }

    # ── Capital ────────────────────────────────────────
    START_BALANCE     = 1000
    ORDER_USD         = 10
    MAX_OPEN_TRADES   = 5
    STOP_LOSS_PCT     = 3.0
    TAKE_PROFIT_PCT   = 5.0

    # ── Señal ──────────────────────────────────────────
    MIN_SCORE         = 3
    SCAN_INTERVAL     = 60
    ANALYSIS_INTERVAL = 300

    # ── API ────────────────────────────────────────────
    BINANCE           = "https://api.binance.com"
    THREADS           = 8


# ───────────────────────────────────────────────────────
#  LOGGER
# ───────────────────────────────────────────────────────

COLORS = {
    "BUY":   "\033[92m",
    "SELL":  "\033[91m",
    "TRADE": "\033[93m",
    "SCAN":  "\033[96m",
    "BOT":   "\033[94m",
    "DATA":  "\033[90m",
    "SCORE": "\033[95m",
}
RESET = "\033[0m"

def log(tag, msg):
    ts  = datetime.now().strftime("%H:%M:%S")
    col = COLORS.get(tag, "")
    print(f"{ts} {col}[{tag:6s}]{RESET} {msg}")


# ───────────────────────────────────────────────────────
#  BINANCE CLIENT
# ───────────────────────────────────────────────────────

class BinanceClient:

    def __init__(self):
        self.base     = Config.BINANCE
        self._session = requests.Session()

    def _get(self, path, params=None):
        try:
            r = self._session.get(
                f"{self.base}{path}",
                params=params,
                timeout=8
            )
            r.raise_for_status()
            return r.json()
        except Exception:
            return None

    def get_top_usdt_pairs(self):
        data = self._get("/api/v3/ticker/24hr")
        if not data:
            log("DATA", "No se pudo obtener tickers — usando lista de respaldo")
            return [
                {"symbol": s, "volume": 0, "change_pct": 0, "price": 0}
                for s in ["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT"]
            ]

        usdt_pairs = []
        for t in data:
            sym = t.get("symbol", "")
            if not sym.endswith("USDT"):
                continue
            if sym in Config.EXCLUDE:
                continue
            vol = float(t.get("quoteVolume", 0))
            if vol < Config.MIN_VOLUME_USD:
                continue
            usdt_pairs.append({
                "symbol":     sym,
                "volume":     vol,
                "change_pct": float(t.get("priceChangePercent", 0)),
                "price":      float(t.get("lastPrice", 0)),
            })

        usdt_pairs.sort(key=lambda x: x["volume"], reverse=True)
        top = usdt_pairs[:Config.TOP_N_PAIRS]

        log("SCAN", f"Universo: {len(top)} pares  "
                    f"(vol min ${Config.MIN_VOLUME_USD/1e6:.0f}M)")
        return top

    def get_price(self, symbol):
        data = self._get("/api/v3/ticker/price", {"symbol": symbol})
        return float(data["price"]) if data else None

    def get_klines(self, symbol, interval="1h", limit=100):
        data = self._get("/api/v3/klines", {
            "symbol":   symbol,
            "interval": interval,
            "limit":    limit,
        })
        return data if data else []


# ───────────────────────────────────────────────────────
#  TECHNICAL ANALYSIS
# ───────────────────────────────────────────────────────

class TA:

    @staticmethod
    def compute(klines, current_price):
        if len(klines) < 50:
            return {}

        closes = [float(k[4]) for k in klines]
        highs  = [float(k[2]) for k in klines]
        lows   = [float(k[3]) for k in klines]
        vols   = [float(k[5]) for k in klines]

        closes[-1] = current_price

        rsi  = TA.rsi(closes)
        ma7  = TA.ma(closes, 7)
        ma21 = TA.ma(closes, 21)
        ma50 = TA.ma(closes, 50)
        bb   = TA.bollinger(closes)
        macd = TA.macd_calc(closes)
        mom  = TA.momentum(closes)

        vol_avg   = sum(vols[-20:]) / 20
        vol_ratio = vols[-1] / vol_avg if vol_avg > 0 else 1

        return {
            "price":     current_price,
            "rsi":       rsi,
            "ma7":       ma7,
            "ma21":      ma21,
            "ma50":      ma50,
            "bb":        bb,
            "macd":      macd,
            "momentum":  mom,
            "vol_ratio": vol_ratio,
            "high_24h":  max(highs[-24:]),
            "low_24h":   min(lows[-24:]),
        }

    @staticmethod
    def rsi(prices, period=14):
        if len(prices) < period + 1:
            return None
        gains = losses = 0
        for i in range(1, period + 1):
            d = prices[i] - prices[i-1]
            if d > 0: gains += d
            else:     losses += abs(d)
        ag = gains / period
        al = losses / period
        for i in range(period + 1, len(prices)):
            d = prices[i] - prices[i-1]
            ag = (ag * (period-1) + (d if d > 0 else 0)) / period
            al = (al * (period-1) + (abs(d) if d < 0 else 0)) / period
        if al == 0:
            return 100
        return 100 - 100 / (1 + ag/al)

    @staticmethod
    def ma(prices, period):
        if len(prices) < period:
            return None
        return sum(prices[-period:]) / period

    @staticmethod
    def bollinger(prices, period=20):
        if len(prices) < period:
            return None
        s    = prices[-period:]
        mean = sum(s) / period
        std  = (sum((x - mean)**2 for x in s) / period) ** 0.5
        return {
            "upper": mean + 2*std,
            "mid":   mean,
            "lower": mean - 2*std,
        }

    @staticmethod
    def macd_calc(prices, fast=12, slow=26, signal=9):
        if len(prices) < slow + signal + 5:
            return None
        def ema(p, n):
            k = 2/(n+1)
            e = p[0]
            for v in p[1:]:
                e = v*k + e*(1-k)
            return e
        try:
            macd_vals = []
            for i in range(slow, len(prices)):
                win = prices[max(0, i - slow*2): i+1]
                m   = ema(win[-fast:], fast) - ema(win, slow)
                macd_vals.append(m)
            if len(macd_vals) < signal + 2:
                return None
            sig_line  = ema(macd_vals[-signal*2:], signal)
            hist      = macd_vals[-1] - sig_line
            prev_sig  = ema(macd_vals[-signal*2-1:-1], signal)
            prev_hist = macd_vals[-2] - prev_sig
            if hist > 0 and prev_hist <= 0:
                cross = "bullish"
            elif hist < 0 and prev_hist >= 0:
                cross = "bearish"
            else:
                cross = "none"
            return {"hist": hist, "cross": cross}
        except Exception:
            return None

    @staticmethod
    def momentum(prices, period=10):
        if len(prices) < period + 1:
            return None
        return (prices[-1] - prices[-period-1]) / prices[-period-1] * 100


# ───────────────────────────────────────────────────────
#  STRATEGY ENGINE
# ───────────────────────────────────────────────────────

class StrategyEngine:

    @staticmethod
    def score(ta):
        if not ta:
            return {"score": 0, "signals": [], "action": "HOLD", "vol_note": ""}

        score   = 0
        signals = []
        price   = ta.get("price", 0)

        # RSI (peso ±2)
        rsi = ta.get("rsi")
        if rsi is not None:
            if rsi < 25:
                score += 2
                signals.append(f"RSI {rsi:.0f} sobreventa extrema")
            elif rsi < 35:
                score += 1
                signals.append(f"RSI {rsi:.0f} sobreventa")
            elif rsi > 75:
                score -= 2
                signals.append(f"RSI {rsi:.0f} sobrecompra extrema")
            elif rsi > 65:
                score -= 1
                signals.append(f"RSI {rsi:.0f} sobrecompra")

        # Tendencia MA (peso ±2)
        ma7  = ta.get("ma7")
        ma21 = ta.get("ma21")
        ma50 = ta.get("ma50")
        if ma7 and ma21 and ma50:
            if ma7 > ma21 > ma50:
                score += 2
                signals.append("Tendencia alcista MA7>MA21>MA50")
            elif ma7 < ma21 < ma50:
                score -= 2
                signals.append("Tendencia bajista MA7<MA21<MA50")
            elif ma7 > ma21:
                score += 1
                signals.append("MA7 cruza MA21 al alza")
            elif ma7 < ma21:
                score -= 1
                signals.append("MA7 cruza MA21 a la baja")

        # Bollinger (peso ±2)
        bb = ta.get("bb")
        if bb and price:
            rng = bb["upper"] - bb["lower"]
            if rng > 0:
                pct = (price - bb["lower"]) / rng
                if pct < 0.05:
                    score += 2
                    signals.append("Bajo banda inferior BB")
                elif pct < 0.2:
                    score += 1
                    signals.append("Zona baja BB")
                elif pct > 0.95:
                    score -= 2
                    signals.append("Sobre banda superior BB")
                elif pct > 0.8:
                    score -= 1
                    signals.append("Zona alta BB")

        # MACD (peso ±1)
        macd = ta.get("macd")
        if macd:
            if macd["cross"] == "bullish":
                score += 1
                signals.append("MACD cruce alcista")
            elif macd["cross"] == "bearish":
                score -= 1
                signals.append("MACD cruce bajista")

        # Momentum ROC (peso ±1)
        mom = ta.get("momentum")
        if mom is not None:
            if mom > 3:
                score += 1
                signals.append(f"Momentum +{mom:.1f}%")
            elif mom < -3:
                score -= 1
                signals.append(f"Momentum {mom:.1f}%")

        # Volumen (info, no vota)
        vol = ta.get("vol_ratio", 1)
        if vol > 1.5:
            vol_note = f"Vol x{vol:.1f} alto (confirma)"
        elif vol < 0.5:
            vol_note = f"Vol x{vol:.1f} bajo (señal débil)"
        else:
            vol_note = f"Vol x{vol:.1f} normal"

        # Decisión
        if score >= Config.MIN_SCORE:
            action = "BUY"
        elif score <= -Config.MIN_SCORE:
            action = "SELL"
        else:
            action = "HOLD"

        return {
            "score":    score,
            "action":   action,
            "signals":  signals,
            "vol_note": vol_note,
        }


# ───────────────────────────────────────────────────────
#  TRADE MANAGER
# ───────────────────────────────────────────────────────

class TradeManager:

    def __init__(self):
        self.open_trades = {}
        self.history     = []
        self.balance     = float(Config.START_BALANCE)

    def can_open(self, symbol):
        return (
            len(self.open_trades) < Config.MAX_OPEN_TRADES
            and symbol not in self.open_trades
        )

    def open_trade(self, symbol, price, score):
        stop   = price * (1 - Config.STOP_LOSS_PCT   / 100)
        target = price * (1 + Config.TAKE_PROFIT_PCT / 100)
        self.open_trades[symbol] = {
            "entry":  price,
            "stop":   stop,
            "target": target,
            "usdt":   Config.ORDER_USD,
            "score":  score,
            "time":   datetime.now(),
        }
        log("TRADE", f"OPEN  {symbol:<12} @ ${price:>12,.4f}  "
                     f"SL ${stop:,.4f}  TP ${target:,.4f}  score={score:+d}")

    def check_exit(self, symbol, price):
        t = self.open_trades.get(symbol)
        if not t:
            return None
        if price <= t["stop"]:
            return "STOP_LOSS"
        if price >= t["target"]:
            return "TAKE_PROFIT"
        return None

    def close_trade(self, symbol, price, reason):
        t       = self.open_trades.pop(symbol)
        pnl_pct = (price - t["entry"]) / t["entry"] * 100
        pnl_usd = t["usdt"] * pnl_pct / 100
        self.history.append({
            "symbol":  symbol,
            "pnl_usd": pnl_usd,
            "pnl_pct": pnl_pct,
            "reason":  reason,
        })
        self.balance += pnl_usd
        icon = "+" if pnl_usd > 0 else "-"
        log("TRADE", f"CLOSE {icon} {symbol:<12} @ ${price:>12,.4f}  "
                     f"{pnl_pct:+.2f}%  ${pnl_usd:+.2f}  ({reason})")

    def status(self):
        n       = len(self.history)
        pnl     = self.balance - Config.START_BALANCE
        pnl_pct = pnl / Config.START_BALANCE * 100
        wins    = sum(1 for t in self.history if t["pnl_usd"] > 0)
        wr      = wins / n * 100 if n else 0

        open_lines = ""
        for sym, t in self.open_trades.items():
            mins = int((datetime.now() - t["time"]).total_seconds() / 60)
            open_lines += f"\n      {sym:<12} entrada ${t['entry']:,.4f}  hace {mins}min"

        return (
            f"\n  {'─'*56}"
            f"\n  Balance: ${self.balance:>10,.2f}   PnL {pnl:+.2f} ({pnl_pct:+.1f}%)"
            f"\n  Trades:  {n} cerrados | {len(self.open_trades)} abiertos | WR {wr:.0f}%"
            f"{open_lines}"
        )


# ───────────────────────────────────────────────────────
#  ORACLE BOT v2
# ───────────────────────────────────────────────────────

class OracleBot:

    def __init__(self):
        self.binance       = BinanceClient()
        self.trades        = TradeManager()
        self._cycle        = 0
        self._last_analysis = 0

    def _analyze_one(self, ticker):
        symbol = ticker["symbol"]
        price  = ticker["price"]
        klines = self.binance.get_klines(symbol, "1h", 100)
        if len(klines) < 50:
            return None
        ta     = TA.compute(klines, price)
        result = StrategyEngine.score(ta)
        return {
            "symbol":     symbol,
            "price":      price,
            "change_pct": ticker["change_pct"],
            "volume":     ticker["volume"],
            **result,
        }

    def _scan_market(self):
        log("SCAN", "Obteniendo universo de mercado...")
        universe = self.binance.get_top_usdt_pairs()
        if not universe:
            return

        log("SCAN", f"Analizando {len(universe)} pares ({Config.THREADS} hilos)...")

        results = []
        with ThreadPoolExecutor(max_workers=Config.THREADS) as ex:
            futures = {ex.submit(self._analyze_one, t): t for t in universe}
            for future in as_completed(futures):
                r = future.result()
                if r:
                    results.append(r)

        results.sort(key=lambda x: abs(x["score"]), reverse=True)

        # Tabla resumen top 10
        print(f"\n  {'─'*60}")
        print(f"  {'SÍMBOLO':<12} {'PRECIO':>12} {'24h':>7} {'SCORE':>6}  ACCIÓN")
        print(f"  {'─'*60}")
        for r in results[:10]:
            col = COLORS.get(r["action"], "")
            print(
                f"  {r['symbol']:<12} ${r['price']:>11,.4f} "
                f"{r['change_pct']:>+6.1f}%  "
                f"{col}{r['score']:>+5d}  {r['action']}{RESET}"
            )
        print(f"  {'─'*60}\n")

        for r in results:
            self._act(r)

    def _act(self, r):
        symbol = r["symbol"]
        price  = r["price"]
        action = r["action"]
        score  = r["score"]

        if action == "BUY" and self.trades.can_open(symbol):
            log("SCORE", f"{symbol} {score:+d} → {' | '.join(r['signals'][:2])}")
            self.trades.open_trade(symbol, price, score)

        elif action == "SELL" and symbol in self.trades.open_trades:
            log("SCORE", f"{symbol} {score:+d} → {' | '.join(r['signals'][:2])}")
            self.trades.close_trade(symbol, price, "signal")

    def _check_sl_tp(self):
        for symbol in list(self.trades.open_trades.keys()):
            price = self.binance.get_price(symbol)
            if not price:
                continue
            reason = self.trades.check_exit(symbol, price)
            if reason:
                self.trades.close_trade(symbol, price, reason)

    def run(self):
        print(f"""
\033[92m╔══════════════════════════════════════════════════════╗
║           ORACLE BOT v2 — Market Scanner             ║
╚══════════════════════════════════════════════════════╝\033[0m
  Universo:    Top {Config.TOP_N_PAIRS} pares USDT por volumen
  Indicadores: RSI · MA7/21/50 · Bollinger · MACD · Momentum
  Score mín:   {Config.MIN_SCORE}/8 para operar
  Capital/op:  ${Config.ORDER_USD}  |  Max trades: {Config.MAX_OPEN_TRADES}
  SL {Config.STOP_LOSS_PCT}%  |  TP {Config.TAKE_PROFIT_PCT}%
  Análisis:    cada {Config.ANALYSIS_INTERVAL}s  |  SL/TP check: cada {Config.SCAN_INTERVAL}s
""")
        while True:
            self._cycle += 1
            now = time.time()

            print(f"\n{'═'*60}")
            print(f"  Ciclo #{self._cycle} — {datetime.now().strftime('%d/%m %H:%M:%S')}")
            print(self.trades.status())

            if now - self._last_analysis >= Config.ANALYSIS_INTERVAL:
                self._scan_market()
                self._last_analysis = now
            else:
                remaining = int(Config.ANALYSIS_INTERVAL - (now - self._last_analysis))
                log("SCAN", f"Chequeando SL/TP... (análisis en {remaining}s)")
                self._check_sl_tp()

            log("BOT", f"Próximo ciclo en {Config.SCAN_INTERVAL}s  (Ctrl+C para detener)")
            time.sleep(Config.SCAN_INTERVAL)


# ───────────────────────────────────────────────────────
#  MAIN
# ───────────────────────────────────────────────────────

if __name__ == "__main__":
    bot = OracleBot()
    try:
        bot.run()
    except KeyboardInterrupt:
        print(f"\n\033[93mBot detenido.\033[0m")
        print(bot.trades.status())
