# ORACLE BOT — Guía de instalación

## ¿Qué hace?

Analiza el mercado cada 5 minutos usando 4 fuentes simultáneas:
1. **Binance** — precios en vivo, velas, volumen, order book
2. **CoinGecko** — market cap, cambios de 7/30 días, distancia del ATH
3. **Alternative.me** — Fear & Greed Index (psicología del mercado)
4. **Claude AI** — árbitro final que pondera todo y decide BUY/SELL/HOLD

Cuando decide operar, ejecuta la orden automáticamente y monitorea
stop loss / take profit cada 10 segundos.

---

## Instalación (15 minutos)

### 1. Instalá Python
Descargá Python 3.11+ desde python.org si no lo tenés.

### 2. Descargá el bot
Guardá `oracle_bot.py`, `requirements.txt` y `.env.example` en una carpeta,
por ejemplo `C:\oracle-bot\` o `~/oracle-bot/`.

### 3. Instalá dependencias
```bash
cd oracle-bot
pip install -r requirements.txt
```

### 4. Configurá las keys

Copiá `.env.example` como `.env` y completá:

```
BINANCE_API_KEY=...     ← De Binance → Gestión de API
BINANCE_API_SECRET=...  ← Solo se ve una vez al crear la key
ANTHROPIC_API_KEY=...   ← De console.anthropic.com (gratuito para probar)
TESTNET=true            ← Dejalo en true hasta que confíes en el bot
ORDER_USD=10            ← Empezá con poco
```

Luego cargá las variables antes de correr (en Windows):
```cmd
set BINANCE_API_KEY=tu_key
set BINANCE_API_SECRET=tu_secret
set ANTHROPIC_API_KEY=tu_key
set TESTNET=true
set ORDER_USD=10
```

O en Mac/Linux:
```bash
export BINANCE_API_KEY=tu_key
export BINANCE_API_SECRET=tu_secret
export ANTHROPIC_API_KEY=tu_key
export TESTNET=true
export ORDER_USD=10
```

### 5. Clave de Binance

En binance.com → tu perfil → Gestión de API → Crear API:
- Activá: **Lectura** ✓
- Para operar: **Trading spot** ✓  
- NO activar: Retiros ✗

### 6. Corré el bot
```bash
python oracle_bot.py
```

---

## Parámetros clave

| Variable | Default | Descripción |
|---|---|---|
| TESTNET | true | Paper trading (sin dinero real) |
| ORDER_USD | 10 | USD por operación |
| MAX_OPEN_TRADES | 2 | Trades simultáneos máximos |
| STOP_LOSS_PCT | 3 | % pérdida máxima |
| TAKE_PROFIT_PCT | 5 | % ganancia objetivo |
| MIN_CONFIDENCE | 65 | Confianza mínima de IA |
| ANALYSIS_INTERVAL | 300 | Segundos entre ciclos |

---

## Cómo funciona la decisión

```
Binance (precio, velas, volumen)
        +
CoinGecko (contexto de mercado)     →  Claude AI  →  BUY / SELL / HOLD
        +                                (árbitro)
Fear & Greed Index (sentimiento)
        +
Indicadores técnicos (RSI, MA, BB, MACD)
```

Claude recibe todos los datos, razona, y devuelve:
- **action**: BUY / SELL / HOLD
- **confidence**: 0-100%
- **reason**: por qué tomó esa decisión
- **risk**: LOW / MEDIUM / HIGH

El bot solo opera si `confidence >= MIN_CONFIDENCE`.

---

## Recomendaciones

1. **Empezá con TESTNET=true** por al menos 1 semana para ver cómo se comporta
2. **ORDER_USD=10** es un buen punto de partida para dinero real
3. Revisá los logs cada día — el bot imprime todo lo que piensa
4. Si querés agregar CryptoPanic (noticias), registrate gratis en cryptopanic.com/developers/api

---

## Disclaimer

Este bot es experimental. El mercado es impredecible.
Usá solo dinero que podés perder completamente.
