# Oracle Bot v2

Bot de paper trading que escanea los top 30 pares USDT por volumen en Binance y opera automáticamente usando análisis técnico multicapa.

## Cómo funciona

Cada 5 minutos descarga el universo de mercado, analiza cada par en paralelo y abre trades si el score supera el umbral mínimo. Cada 60 segundos chequea stop loss y take profit de posiciones abiertas.

**Indicadores:** RSI · MA7/MA21/MA50 · Bollinger Bands · MACD · Momentum

**Score:** -8 a +8. Opera solo si score ≥ 3 (configurable).

## Setup

```bash
pip install -r requirements.txt
python oracle_bot.py
```

## Configuración

Todo se edita directamente en `Config` al inicio de `oracle_bot.py`:

| Parámetro | Default | Descripción |
|---|---|---|
| `TOP_N_PAIRS` | 30 | Pares a escanear por volumen |
| `ORDER_USD` | 10 | USD por operación |
| `MAX_OPEN_TRADES` | 5 | Trades simultáneos máximos |
| `STOP_LOSS_PCT` | 3.0 | % stop loss |
| `TAKE_PROFIT_PCT` | 5.0 | % take profit |
| `MIN_SCORE` | 3 | Score mínimo para operar |
| `ANALYSIS_INTERVAL` | 300 | Segundos entre análisis completos |

## Roadmap

- [ ] Persistencia de estado (JSON)
- [ ] Log en archivo
- [ ] Notificaciones Telegram
- [ ] Análisis multi-timeframe (1h + 4h)
- [ ] Filtro de tendencia BTC

---

> Experimental. Usá solo dinero que podés perder.
