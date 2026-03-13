#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════╗
║           ORACLE BOT v3 — Market Scanner             ║
║  Multi-timeframe · BTC filter · File logging         ║
╚══════════════════════════════════════════════════════╝
"""

import time
import logging
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests


# ───────────────────────────────────────────────────────
#  CONFIG
# ───────────────────────────────────────────────────────

class Config:

    # ── Universo ───────────────────────────────────────
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
    # Score mínimo requerido en CADA timeframe para operar
    MIN_SCORE_1H      = 3    # sobre 8
    MIN_SCORE_4H      = 2    # sobre 8 (menos exigente en TF mayor)

    # ── Filtro BTC ─────────────────────────────────────
    BTC_FILTER        = True   # False = deshabilitar
    # Si RSI de BTC en 4h < este valor → bloquear compras
    BTC_RSI_BLOCK_BUY = 40
    # Si RSI de BTC en 4h > este valor → bloquear ventas en largo
    BTC_RSI_BLOCK_SELL = 65
    # Si BTC cae más de este % en 4h → bloquear compras
    BTC_DROP_BLOCK    = -3.0

    # ── Timing ─────────────────────────────────────────
    SCAN_INTERVAL     = 60
    ANALYSIS_INTERVAL = 300

    # ── API / sistema ──────────────────────────────────
    BINANCE           = "https://api.binance.com"
    THREADS           = 8
    LOG_DIR           = "logs"


# ───────────────────────────────────────────────────────
#  LOGGER — consola con color + archivo diario
# ───────────────────────────────────────────────────────

COLORS = {
    "BUY":    "\033[92m",
    "SELL":   "\033[91m",
    "TRADE":  "\033[93m",
    "SCAN":   "\033[96m",
    "BOT":    "\033[94m",
    "DATA":   "\033[90m",
    "SCORE":  "\033[95m",
    "FILTER": "\033[33m",
    "MTF":    "\033[36m",
}
RESET = "\033[0m"

os.makedirs(Config.LOG_DIR, exist_ok=True)
_log_filename = os.path.join(
    Config.LOG_DIR,
    f"oracle_{datetime.now().strftime('%Y-%m-%d')}.log"
)
logging.basicConfig(
    filename=_log_filename,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

def log(tag: str, msg: str):
    ts  = datetime.now().strftime("%H:%M:%S")
    col = COLORS.get(tag, "")
    print(f"{ts} {col}[{tag:7s}]{RESET} {msg}")
    logging.info(f"[{tag}] {msg}")


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
                timeout=8,
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
        pairs = []
        for t in data:
            sym = t.get("symbol", "")
            if not sym.endswith("USDT") or sym in Config.EXCLUDE:
                continue
            vol = float(t.get("quoteVolume", 0))
            if vol < Config.MIN_VOLUME_USD:
                continue
            pairs.append({
                "symbol":     sym,
                "volume":     vol,
                "change_pct": float(t.get("priceChangePercent", 0)),
                "price":      float(t.get("lastPrice", 0)),
            })
        pairs.sort(key=lambda x: x["volume"], reverse=True)
        top = pairs[:Config.TOP_N_PAIRS]
        log("SCAN", f"Universo: {len(top)} pares  (vol min ${Config.MIN_VOLUME_USD/1e6:.0f}M)")
        return top

    def get_price(self, symbol):
        data = self._get("/api/v3/ticker/price", {"symbol": symbol})
        return float(data["price"]) if data else None

    def get_klines(self, symbol, interval="1h", limit=100):
        data = self._get("/api/v3/klines", {
            "symbol": symbol, "interval": interval, "limit": limit,
        })
        return data if data else []


# ───────────────────────────────────────────────────────
#  TECHNICAL ANALYSIS
# ───────────────────────────────────────────────────────

class TA:

    @staticmethod
    def compute(klines, current_price=None):
        if len(klines) < 50:
            return {}
        closes = [float(k[4]) for k in klines]
        highs  = [float(k[2]) for k in klines]
        lows   = [float(k[3]) for k in klines]
        vols   = [float(k[5]) for k in klines]
        if current_price:
            closes[-1] = current_price

        vol_avg   = sum(vols[-20:]) / 20
        vol_ratio = vols[-1] / vol_avg if vol_avg > 0 else 1

        return {
            "price":     closes[-1],
            "rsi":       TA.rsi(closes),
            "ma7":       TA.ma(closes, 7),
            "ma21":      TA.ma(closes, 21),
            "ma50":      TA.ma(closes, 50),
            "bb":        TA.bollinger(closes),
            "macd":      TA.macd_calc(closes),
            "momentum":  TA.momentum(closes),
            "vol_ratio": vol_ratio,
            "high_24h":  max(highs[-24:]),
            "low_24h":   min(lows[-24:]),
            # Cambio % en este timeframe (últimas 4 velas)
            "change_4c": (closes[-1] - closes[-5]) / closes[-5] * 100 if len(closes) >= 5 else 0,
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
            ag = (ag*(period-1) + (d if d > 0 else 0)) / period
            al = (al*(period-1) + (abs(d) if d < 0 else 0)) / period
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
        std  = (sum((x-mean)**2 for x in s) / period) ** 0.5
        return {"upper": mean + 2*std, "mid": mean, "lower": mean - 2*std}

    @staticmethod
    def macd_calc(prices, fast=12, slow=26, signal=9):
        if len(prices) < slow + signal + 5:
            return None
        def ema(p, n):
            k = 2/(n+1); e = p[0]
            for v in p[1:]: e = v*k + e*(1-k)
            return e
        try:
            macd_vals = []
            for i in range(slow, len(prices)):
                win = prices[max(0, i-slow*2): i+1]
                macd_vals.append(ema(win[-fast:], fast) - ema(win, slow))
            if len(macd_vals) < signal + 2:
                return None
            sig_line  = ema(macd_vals[-signal*2:], signal)
            hist      = macd_vals[-1] - sig_line
            prev_hist = macd_vals[-2] - ema(macd_vals[-signal*2-1:-1], signal)
            cross = ("bullish" if hist > 0 and prev_hist <= 0 else
                     "bearish" if hist < 0 and prev_hist >= 0 else "none")
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
    def score(ta: dict) -> dict:
        """Score -8 a +8. Cada indicador vota con peso propio."""
        if not ta:
            return {"score": 0, "signals": [], "action": "HOLD", "vol_note": ""}

        score   = 0
        signals = []
        price   = ta.get("price", 0)

        # RSI (±2)
        rsi = ta.get("rsi")
        if rsi is not None:
            if   rsi < 25: score += 2; signals.append(f"RSI {rsi:.0f} sobreventa extrema")
            elif rsi < 35: score += 1; signals.append(f"RSI {rsi:.0f} sobreventa")
            elif rsi > 75: score -= 2; signals.append(f"RSI {rsi:.0f} sobrecompra extrema")
            elif rsi > 65: score -= 1; signals.append(f"RSI {rsi:.0f} sobrecompra")

        # Tendencia MA (±2)
        ma7, ma21, ma50 = ta.get("ma7"), ta.get("ma21"), ta.get("ma50")
        if ma7 and ma21 and ma50:
            if   ma7 > ma21 > ma50: score += 2; signals.append("Tendencia alcista MA7>MA21>MA50")
            elif ma7 < ma21 < ma50: score -= 2; signals.append("Tendencia bajista MA7<MA21<MA50")
            elif ma7 > ma21:        score += 1; signals.append("MA7 sobre MA21")
            elif ma7 < ma21:        score -= 1; signals.append("MA7 bajo MA21")

        # Bollinger (±2)
        bb = ta.get("bb")
        if bb and price:
            rng = bb["upper"] - bb["lower"]
            if rng > 0:
                pct = (price - bb["lower"]) / rng
                if   pct < 0.05: score += 2; signals.append("Bajo banda inferior BB")
                elif pct < 0.20: score += 1; signals.append("Zona baja BB")
                elif pct > 0.95: score -= 2; signals.append("Sobre banda superior BB")
                elif pct > 0.80: score -= 1; signals.append("Zona alta BB")

        # MACD (±1)
        macd = ta.get("macd")
        if macd:
            if   macd["cross"] == "bullish": score += 1; signals.append("MACD cruce alcista")
            elif macd["cross"] == "bearish": score -= 1; signals.append("MACD cruce bajista")

        # Momentum ROC (±1)
        mom = ta.get("momentum")
        if mom is not None:
            if   mom >  3: score += 1; signals.append(f"Momentum +{mom:.1f}%")
            elif mom < -3: score -= 1; signals.append(f"Momentum {mom:.1f}%")

        # Volumen — informativo
        vol = ta.get("vol_ratio", 1)
        vol_note = (f"Vol x{vol:.1f} alto (confirma)" if vol > 1.5 else
                    f"Vol x{vol:.1f} bajo (señal débil)" if vol < 0.5 else
                    f"Vol x{vol:.1f} normal")

        action = ("BUY"  if score >= Config.MIN_SCORE_1H else
                  "SELL" if score <= -Config.MIN_SCORE_1H else "HOLD")

        return {"score": score, "action": action, "signals": signals, "vol_note": vol_note}


# ───────────────────────────────────────────────────────
#  BTC MARKET FILTER
# ───────────────────────────────────────────────────────

class BTCFilter:
    """
    Analiza BTC en 4h y devuelve el estado del mercado.
    block_buy  = True → no abrir compras
    block_sell = True → no cerrar posiciones largas por señal
    """

    def __init__(self, binance: BinanceClient):
        self.binance = binance
        self.state   = {"block_buy": False, "block_sell": False, "reason": "OK", "rsi": None}

    def update(self):
        if not Config.BTC_FILTER:
            return

        klines = self.binance.get_klines("BTCUSDT", "4h", 60)
        if len(klines) < 50:
            return

        ta = TA.compute(klines)
        rsi     = ta.get("rsi")
        change  = ta.get("change_4c", 0)   # cambio últimas 4 velas de 4h = 16h
        ma7     = ta.get("ma7")
        ma21    = ta.get("ma21")

        block_buy  = False
        block_sell = False
        reasons    = []

        if rsi is not None:
            if rsi < Config.BTC_RSI_BLOCK_BUY:
                block_buy = True
                reasons.append(f"BTC RSI {rsi:.0f} (débil)")
            if rsi > Config.BTC_RSI_BLOCK_SELL:
                block_sell = True
                reasons.append(f"BTC RSI {rsi:.0f} (sobrecomprado)")

        if change < Config.BTC_DROP_BLOCK:
            block_buy = True
            reasons.append(f"BTC cayó {change:.1f}% en 16h")

        if ma7 and ma21 and ma7 < ma21 * 0.995:
            block_buy = True
            reasons.append("BTC tendencia bajista 4h")

        reason = " | ".join(reasons) if reasons else "Mercado OK"
        self.state = {
            "block_buy":  block_buy,
            "block_sell": block_sell,
            "reason":     reason,
            "rsi":        rsi,
            "change_4c":  change,
        }

        if block_buy or block_sell:
            log("FILTER", f"BTC filter activo → {reason}")
        else:
            log("FILTER", f"BTC OK — RSI {rsi:.0f} | cambio 16h {change:+.1f}%")

    @property
    def block_buy(self):
        return self.state.get("block_buy", False)

    @property
    def block_sell(self):
        return self.state.get("block_sell", False)


# ───────────────────────────────────────────────────────
#  MULTI-TIMEFRAME ANALYSIS
# ───────────────────────────────────────────────────────

class MTFAnalysis:
    """
    Analiza un par en 1h y 4h.
    Solo genera señal si AMBOS timeframes coinciden en dirección.
    El score final es el mínimo entre los dos (el más conservador).
    """

    def __init__(self, binance: BinanceClient):
        self.binance = binance

    def analyze(self, ticker: dict) -> dict | None:
        symbol = ticker["symbol"]
        price  = ticker["price"]

        # ── Timeframe 1h ──────────────────────────────
        k1h = self.binance.get_klines(symbol, "1h", 100)
        if len(k1h) < 50:
            return None
        ta1h   = TA.compute(k1h, price)
        res1h  = StrategyEngine.score(ta1h)

        # ── Timeframe 4h ──────────────────────────────
        k4h = self.binance.get_klines(symbol, "4h", 100)
        if len(k4h) < 50:
            return None
        ta4h   = TA.compute(k4h)
        res4h  = StrategyEngine.score(ta4h)

        score_1h = res1h["score"]
        score_4h = res4h["score"]
        act_1h   = res1h["action"]
        act_4h   = res4h["action"]

        # ── Confluencia: ambos TF deben coincidir ─────
        if act_1h == act_4h and act_1h != "HOLD":
            # El score definitivo es el mínimo (más conservador)
            final_score  = min(abs(score_1h), abs(score_4h))
            final_score *= (1 if act_1h == "BUY" else -1)
            action       = act_1h
            mtf_ok       = True
        else:
            # Sin confluencia → no operar aunque haya señal en 1h
            final_score = score_1h  # guardar para info
            action      = "HOLD"
            mtf_ok      = False

        signals_combined = res1h["signals"] + [f"[4h] {s}" for s in res4h["signals"]]

        return {
            "symbol":     symbol,
            "price":      price,
            "change_pct": ticker["change_pct"],
            "volume":     ticker["volume"],
            "score":      final_score,
            "score_1h":   score_1h,
            "score_4h":   score_4h,
            "action":     action,
            "mtf_ok":     mtf_ok,
            "signals":    signals_combined,
            "vol_note":   res1h["vol_note"],
        }


# ───────────────────────────────────────────────────────
#  TRADE MANAGER
# ───────────────────────────────────────────────────────

class TradeManager:

    def __init__(self):
        self.open_trades: dict  = {}
        self.history:     list  = []
        self.balance:     float = float(Config.START_BALANCE)

    def can_open(self, symbol):
        return (
            len(self.open_trades) < Config.MAX_OPEN_TRADES
            and symbol not in self.open_trades
        )

    def open_trade(self, symbol, price, score):
        stop   = price * (1 - Config.STOP_LOSS_PCT   / 100)
        target = price * (1 + Config.TAKE_PROFIT_PCT / 100)
        self.open_trades[symbol] = {
            "entry": price, "stop": stop, "target": target,
            "usdt": Config.ORDER_USD, "score": score,
            "time": datetime.now(),
        }
        log("TRADE", f"OPEN  {symbol:<12} @ ${price:>12,.4f}  "
                     f"SL ${stop:,.4f}  TP ${target:,.4f}  score={score:+d}")

    def check_exit(self, symbol, price):
        t = self.open_trades.get(symbol)
        if not t: return None
        if price <= t["stop"]:   return "STOP_LOSS"
        if price >= t["target"]: return "TAKE_PROFIT"
        return None

    def close_trade(self, symbol, price, reason):
        t       = self.open_trades.pop(symbol)
        pnl_pct = (price - t["entry"]) / t["entry"] * 100
        pnl_usd = t["usdt"] * pnl_pct / 100
        self.history.append({
            "symbol": symbol, "pnl_usd": pnl_usd,
            "pnl_pct": pnl_pct, "reason": reason,
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
            f"\n  {'─'*60}"
            f"\n  Balance: ${self.balance:>10,.2f}   PnL {pnl:+.2f} ({pnl_pct:+.1f}%)"
            f"\n  Trades:  {n} cerrados | {len(self.open_trades)} abiertos | WR {wr:.0f}%"
            f"{open_lines}"
        )


# ───────────────────────────────────────────────────────
#  ORACLE BOT v3
# ───────────────────────────────────────────────────────

class OracleBot:

    def __init__(self):
        self.binance        = BinanceClient()
        self.trades         = TradeManager()
        self.btc_filter     = BTCFilter(self.binance)
        self.mtf            = MTFAnalysis(self.binance)
        self._cycle         = 0
        self._last_analysis = 0

    def _scan_market(self):
        # 1. Actualizar filtro BTC primero
        self.btc_filter.update()

        log("SCAN", "Obteniendo universo de mercado...")
        universe = self.binance.get_top_usdt_pairs()
        if not universe:
            return

        log("SCAN", f"Analizando {len(universe)} pares multi-timeframe ({Config.THREADS} hilos)...")

        results = []
        with ThreadPoolExecutor(max_workers=Config.THREADS) as ex:
            futures = {ex.submit(self.mtf.analyze, t): t for t in universe}
            for future in as_completed(futures):
                r = future.result()
                if r:
                    results.append(r)

        # Ordenar: primero los que tienen confluencia MTF, luego por score abs
        results.sort(key=lambda x: (x["mtf_ok"], abs(x["score"])), reverse=True)

        # ── Tabla top 10 ──────────────────────────────
        print(f"\n  {'─'*72}")
        print(f"  {'SÍMBOLO':<12} {'PRECIO':>12} {'24h':>7} {'1h':>5} {'4h':>5} {'MTF':>4}  ACCIÓN")
        print(f"  {'─'*72}")
        for r in results[:10]:
            col     = COLORS.get(r["action"], "")
            mtf_str = "✓" if r["mtf_ok"] else "✗"
            print(
                f"  {r['symbol']:<12} ${r['price']:>11,.4f} "
                f"{r['change_pct']:>+6.1f}%  "
                f"{r['score_1h']:>+4d}  {r['score_4h']:>+4d}  "
                f"{mtf_str}  {col}{r['action']}{RESET}"
            )
        print(f"  {'─'*72}\n")

        # ── Actuar ────────────────────────────────────
        btc_blocked = self.btc_filter.block_buy
        for r in results:
            self._act(r, btc_blocked)

    def _act(self, r: dict, btc_block_buy: bool):
        symbol = r["symbol"]
        price  = r["price"]
        action = r["action"]
        score  = r["score"]

        if symbol == "BTCUSDT":
            return  # BTC se usa solo como filtro, no se tradea

        if action == "BUY":
            if btc_block_buy:
                # Solo logueamos si había una buena señal bloqueada
                if abs(score) >= Config.MIN_SCORE_1H:
                    log("FILTER", f"BUY {symbol} bloqueado por filtro BTC ({self.btc_filter.state['reason']})")
                return
            if self.trades.can_open(symbol):
                log("MTF", f"{symbol} confluencia 1h={r['score_1h']:+d} 4h={r['score_4h']:+d} → {r['signals'][0] if r['signals'] else ''}")
                self.trades.open_trade(symbol, price, score)

        elif action == "SELL" and symbol in self.trades.open_trades:
            if self.btc_filter.block_sell:
                log("FILTER", f"SELL {symbol} bloqueado (BTC sobrecomprado — dejar correr)")
                return
            log("MTF", f"{symbol} confluencia SELL 1h={r['score_1h']:+d} 4h={r['score_4h']:+d}")
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
║           ORACLE BOT v3 — Market Scanner             ║
╚══════════════════════════════════════════════════════╝\033[0m
  Universo:    Top {Config.TOP_N_PAIRS} pares USDT por volumen
  Timeframes:  1h + 4h (confluencia requerida)
  Indicadores: RSI · MA7/21/50 · Bollinger · MACD · Momentum
  Filtro BTC:  {'activado' if Config.BTC_FILTER else 'desactivado'}
  Score mín:   {Config.MIN_SCORE_1H} en 1h  |  {Config.MIN_SCORE_4H} en 4h
  Capital/op:  ${Config.ORDER_USD}  |  Max trades: {Config.MAX_OPEN_TRADES}
  SL {Config.STOP_LOSS_PCT}%  |  TP {Config.TAKE_PROFIT_PCT}%
  Log:         {_log_filename}
""")
        while True:
            self._cycle += 1
            now = time.time()

            print(f"\n{'═'*62}")
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
