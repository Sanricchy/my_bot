# =============================================================================
# RICCHY OMEGA FUSION
# Adaptive Multi-Timeframe MT5 Trading System
# =============================================================================
#
# MERGED / REBUILT FROM:
#   - OMEGA V4 concepts
#   - RICCHY Lux Lucens concepts
#
# IMPORTANT:
#   LIVE_TRADING = False
#   DRY_RUN      = True
#
# TEST ON DEMO FIRST.
#
# INSTALL:
#   pip install MetaTrader5 pandas numpy requests
#
# =============================================================================

import os
import csv
import json
import time
import math
import traceback
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Tuple

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import requests


# =============================================================================
# CONFIG
# =============================================================================

BOT_NAME = "RICCHY OMEGA FUSION LUX LUCENS"
BOT_VERSION = "1.0.0"

LIVE_TRADING = True
DRY_RUN = False

MAGIC_NUMBER = 26091901

# ---------------------------------------------------------------------
# Account / connection
# ---------------------------------------------------------------------

MT5_LOGIN = 0
MT5_PASSWORD = ""
MT5_SERVER = ""
MT5_PATH = ""

# ---------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------

TELEGRAM_ENABLED = True
TELEGRAM_BOT_TOKEN = "8776466894:AAG_LX2zNHLYk5bZqLWxkTkCmV2Bl6EeGgw"
TELEGRAM_CHAT_ID = "8374185295"

# ---------------------------------------------------------------------
# State / journal
# ---------------------------------------------------------------------

STATE_FILE = "RICCHY_OMEGA_FUSION_LUX_LUCENS_state.json"
JOURNAL_FILE = "RICCHY_OMEGA_FUSION_LUX_LUCENS_journal.csv"

# ---------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------

WAT_OFFSET_HOURS = 1

# ---------------------------------------------------------------------
# Symbols
# ---------------------------------------------------------------------

SYMBOLS = [
    "XAUUSD",
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "GBPJPY",
    "EURJPY",
    "EURGBP",
    "USDCAD",
    "USDCHF",
    "NZDUSD",
]

GOLD_ALIASES = {
    "XAUUSD",
    "XAUUSD.",
    "XAUUSDm",
    "XAUUSD.a",
    "GOLD",
    "GOLD.",
    "GOLDm",
}

# ---------------------------------------------------------------------
# Timeframes
# ---------------------------------------------------------------------

TF_H4 = mt5.TIMEFRAME_H4
TF_H1 = mt5.TIMEFRAME_H1
TF_M30 = mt5.TIMEFRAME_M30
TF_M15 = mt5.TIMEFRAME_M15
TF_M5 = mt5.TIMEFRAME_M5
TF_M1 = mt5.TIMEFRAME_M1

BARS = {
    TF_H4: 220,
    TF_H1: 260,
    TF_M30: 300,
    TF_M15: 320,
    TF_M5: 350,
    TF_M1: 180,
}

# ---------------------------------------------------------------------
# Risk
# ---------------------------------------------------------------------

BASE_RISK_PERCENT = 0.50
HARD_MAX_RISK_PERCENT = 1.00

GOLD_RISK_MULTIPLIER = 0.60

DAILY_LOSS_LIMIT_PERCENT = 3.0
MAX_DRAWDOWN_PERCENT = 8.0

MAX_CONSECUTIVE_LOSSES = 4

MAX_OPEN_POSITIONS = 5
MAX_NEW_TRADES_PER_DAY = 8

ONE_POSITION_PER_SYMBOL = True

LOSS_STREAK_REDUCTION_AFTER = 2
LOSS_STREAK_RISK_MULTIPLIER = 0.50

COOLDOWN_MINUTES = 20

# ---------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------

MIN_NORMAL_SCORE = 68
MIN_STRONG_SCORE = 82
MIN_GOLD_SCORE = 78

MIN_RR = 1.80
TARGET_RR = 2.50

# ---------------------------------------------------------------------
# Gold
# ---------------------------------------------------------------------

MAX_GOLD_ATR_PERCENT = 1.80
MAX_GOLD_SPREAD_ATR_RATIO = 0.28

# ---------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------

MAX_SPREAD_POINTS = 30
MAX_GOLD_SPREAD_POINTS = 100

DEVIATION = 30
ORDER_RETRIES = 3

SCAN_SECONDS = 20
STATUS_SECONDS = 300

# ---------------------------------------------------------------------
# Management
# ---------------------------------------------------------------------

BREAK_EVEN_R = 1.0
BREAK_EVEN_LOCK_R = 0.05

PARTIAL_R = 1.50
PARTIAL_PERCENT = 0.50

TRAIL_START_R = 2.0
TRAIL_ATR_MULTIPLIER = 1.20

# ---------------------------------------------------------------------
# Sessions WAT
# ---------------------------------------------------------------------

USE_SESSION_FILTER = True

TOKYO_START = 1
TOKYO_END = 9

LONDON_START = 8
LONDON_END = 17

NEW_YORK_START = 13
NEW_YORK_END = 22

# ---------------------------------------------------------------------
# News
# ---------------------------------------------------------------------

ENABLE_NEWS_FILTER = False

TRADING_ECONOMICS_API_KEY = ""

NEWS_BLOCK_BEFORE_MINUTES = 20
NEWS_BLOCK_AFTER_MINUTES = 20

NEWS_RISK_REDUCTION = 0.50


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class AccountState:
    trading_date: str = ""
    daily_start_balance: float = 0.0
    peak_equity: float = 0.0
    consecutive_losses: int = 0
    daily_trades: int = 0
    daily_profit: float = 0.0
    daily_loss: float = 0.0
    halted: bool = False
    halt_reason: str = ""
    processed_deals: List[int] = field(default_factory=list)


@dataclass
class PositionState:
    ticket: int
    symbol: str
    direction: str
    entry: float
    initial_sl: float
    initial_tp: float
    initial_risk: float
    initial_volume: float
    partial_done: bool = False
    breakeven_done: bool = False


@dataclass
class TradeSignal:
    symbol: str
    direction: str
    setup: str
    regime: str

    score: float
    required_score: float

    entry: float
    sl: float
    tp: float

    rr: float
    atr: float
    atr_percent: float

    risk_percent: float
    lot: float

    reason: str

    confirmations: List[str] = field(default_factory=list)


ACCOUNT = AccountState()

POSITION_STATES: Dict[int, PositionState] = {}

LAST_SIGNAL_TIME: Dict[str, float] = {}
LAST_STATUS_TIME = 0.0

BOT_RUNNING = True


# =============================================================================
# TIME
# =============================================================================

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def wat_now() -> datetime:
    return utc_now() + timedelta(hours=WAT_OFFSET_HOURS)


def wat_date() -> str:
    return wat_now().strftime("%Y-%m-%d")


def wat_time_string() -> str:
    return wat_now().strftime("%Y-%m-%d %H:%M:%S")


def current_hour_wat() -> int:
    return wat_now().hour


# =============================================================================
# LOGGING
# =============================================================================

def log(message: str):
    print(f"[{wat_time_string()}] {message}")


# =============================================================================
# TELEGRAM
# =============================================================================

class TelegramNotifier:

    def __init__(self):
        self.enabled = (
            TELEGRAM_ENABLED
            and bool(TELEGRAM_BOT_TOKEN)
            and bool(TELEGRAM_CHAT_ID)
        )

    def send(self, message: str):
        if not self.enabled:
            return

        try:
            url = (
                f"https://api.telegram.org/bot"
                f"{TELEGRAM_BOT_TOKEN}/sendMessage"
            )

            requests.post(
                url,
                data={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": message,
                },
                timeout=10,
            )

        except Exception as exc:
            log(f"Telegram error: {exc}")


TELEGRAM = TelegramNotifier()


# =============================================================================
# STATE STORAGE
# =============================================================================

def save_state():

    try:
        data = {
            "account": asdict(ACCOUNT),
            "positions": {
                str(ticket): asdict(state)
                for ticket, state in POSITION_STATES.items()
            },
        }

        temp_file = STATE_FILE + ".tmp"

        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        os.replace(temp_file, STATE_FILE)

    except Exception as exc:
        log(f"State save error: {exc}")


def load_state():

    global ACCOUNT

    if not os.path.exists(STATE_FILE):
        return

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        account_data = data.get("account", {})

        ACCOUNT = AccountState(
            **{
                k: account_data.get(k, getattr(AccountState(), k))
                for k in AccountState.__dataclass_fields__
            }
        )

        POSITION_STATES.clear()

        for ticket, raw in data.get("positions", {}).items():

            try:
                POSITION_STATES[int(ticket)] = PositionState(**raw)
            except Exception:
                continue

        log("Persistent state loaded.")

    except Exception as exc:
        log(f"State load error: {exc}")


# =============================================================================
# JOURNAL
# =============================================================================

def journal_event(
    event: str,
    symbol: str = "",
    direction: str = "",
    setup: str = "",
    score: float = 0.0,
    entry: float = 0.0,
    sl: float = 0.0,
    tp: float = 0.0,
    lot: float = 0.0,
    result: float = 0.0,
    note: str = "",
):

    fields = [
        "time",
        "event",
        "symbol",
        "direction",
        "setup",
        "score",
        "entry",
        "sl",
        "tp",
        "lot",
        "result",
        "note",
    ]

    row = [
        wat_time_string(),
        event,
        symbol,
        direction,
        setup,
        score,
        entry,
        sl,
        tp,
        lot,
        result,
        note,
    ]

    exists = os.path.exists(JOURNAL_FILE)

    try:
        with open(
            JOURNAL_FILE,
            "a",
            newline="",
            encoding="utf-8",
        ) as f:

            writer = csv.writer(f)

            if not exists:
                writer.writerow(fields)

            writer.writerow(row)

    except Exception as exc:
        log(f"Journal error: {exc}")


# =============================================================================
# MT5 CONNECTION
# =============================================================================

def initialize_mt5() -> bool:

    try:

        kwargs = {}

        if MT5_PATH:
            kwargs["path"] = MT5_PATH

        if MT5_LOGIN:
            kwargs["login"] = MT5_LOGIN
            kwargs["password"] = MT5_PASSWORD
            kwargs["server"] = MT5_SERVER

        if not mt5.initialize(**kwargs):

            log(f"MT5 initialize failed: {mt5.last_error()}")
            return False

        terminal = mt5.terminal_info()
        account = mt5.account_info()

        if terminal is None or account is None:
            log("MT5 terminal/account information unavailable.")
            return False

        log(
            f"MT5 connected | "
            f"account={account.login} | "
            f"balance={account.balance:.2f} | "
            f"equity={account.equity:.2f}"
        )

        return True

    except Exception as exc:

        log(f"MT5 connection error: {exc}")
        return False


def reconnect_mt5() -> bool:

    try:

        if mt5.terminal_info() is not None:
            return True

    except Exception:
        pass

    try:
        mt5.shutdown()
    except Exception:
        pass

    return initialize_mt5()


def shutdown_mt5():

    try:
        mt5.shutdown()
    except Exception:
        pass


# =============================================================================
# SYMBOL HELPERS
# =============================================================================

def is_gold(symbol: str) -> bool:
    return symbol.upper() in GOLD_ALIASES


def find_available_symbol(requested: str) -> Optional[str]:

    candidates = [requested]

    if requested == "XAUUSD":
        candidates.extend([
            "XAUUSD.",
            "XAUUSDm",
            "XAUUSD.a",
            "GOLD",
            "GOLD.",
            "GOLDm",
        ])

    for symbol in candidates:

        info = mt5.symbol_info(symbol)

        if info is not None:

            if not info.visible:
                mt5.symbol_select(symbol, True)

            return symbol

    return None


def get_tick(symbol: str):

    try:
        return mt5.symbol_info_tick(symbol)
    except Exception:
        return None


def get_symbol_info(symbol: str):

    try:
        return mt5.symbol_info(symbol)
    except Exception:
        return None


# =============================================================================
# MARKET DATA
# =============================================================================

def get_rates(symbol: str, timeframe, count: int) -> Optional[pd.DataFrame]:

    try:

        rates = mt5.copy_rates_from_pos(
            symbol,
            timeframe,
            0,
            count,
        )

        if rates is None or len(rates) < 100:
            return None

        df = pd.DataFrame(rates)

        df["time"] = pd.to_datetime(
            df["time"],
            unit="s",
            utc=True,
        )

        return df

    except Exception as exc:

        log(f"Rates error {symbol}/{timeframe}: {exc}")
        return None


# =============================================================================
# INDICATORS
# =============================================================================

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:

    x = df.copy()

    x["ema20"] = x["close"].ewm(span=20, adjust=False).mean()
    x["ema50"] = x["close"].ewm(span=50, adjust=False).mean()
    x["ema200"] = x["close"].ewm(span=200, adjust=False).mean()

    delta = x["close"].diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)

    x["rsi"] = 100 - (100 / (1 + rs))

    high_low = x["high"] - x["low"]
    high_close = (x["high"] - x["close"].shift()).abs()
    low_close = (x["low"] - x["close"].shift()).abs()

    tr = pd.concat(
        [high_low, high_close, low_close],
        axis=1,
    ).max(axis=1)

    x["atr"] = tr.rolling(14).mean()

    plus_dm = x["high"].diff()
    minus_dm = -x["low"].diff()

    plus_dm = plus_dm.where(
        (plus_dm > minus_dm) & (plus_dm > 0),
        0,
    )

    minus_dm = minus_dm.where(
        (minus_dm > plus_dm) & (minus_dm > 0),
        0,
    )

    atr14 = x["atr"].replace(0, np.nan)

    plus_di = 100 * (
        plus_dm.rolling(14).mean() / atr14
    )

    minus_di = 100 * (
        minus_dm.rolling(14).mean() / atr14
    )

    dx = (
        (plus_di - minus_di).abs()
        /
        (plus_di + minus_di).replace(0, np.nan)
    ) * 100

    x["adx"] = dx.rolling(14).mean()

    x["body"] = (x["close"] - x["open"]).abs()
    x["range"] = x["high"] - x["low"]

    x["upper_wick"] = (
        x["high"]
        - x[["open", "close"]].max(axis=1)
    )

    x["lower_wick"] = (
        x[["open", "close"]].min(axis=1)
        - x["low"]
    )

    x["bullish"] = x["close"] > x["open"]
    x["bearish"] = x["close"] < x["open"]

    x["atr_percent"] = (
        x["atr"] / x["close"].replace(0, np.nan)
    ) * 100

    return x


# =============================================================================
# PRICE / VOLUME UTILITIES
# =============================================================================

def normalize_price(symbol: str, price: float) -> float:

    info = get_symbol_info(symbol)

    if info is None:
        return price

    return round(price, info.digits)


def normalize_volume(symbol: str, volume: float) -> float:

    info = get_symbol_info(symbol)

    if info is None:
        return volume

    step = info.volume_step
    minimum = info.volume_min
    maximum = info.volume_max

    if step <= 0:
        return max(minimum, min(volume, maximum))

    volume = math.floor(volume / step) * step

    volume = max(minimum, min(volume, maximum))

    decimals = max(0, int(round(-math.log10(step))))

    return round(volume, decimals)


# =============================================================================
# SESSION FILTER
# =============================================================================

def session_allowed() -> bool:

    if not USE_SESSION_FILTER:
        return True

    hour = current_hour_wat()

    tokyo = TOKYO_START <= hour < TOKYO_END
    london = LONDON_START <= hour < LONDON_END
    new_york = NEW_YORK_START <= hour < NEW_YORK_END

    return tokyo or london or new_york


# =============================================================================
# ACCOUNT STATE
# =============================================================================

def update_account_state():

    global ACCOUNT

    account = mt5.account_info()

    if account is None:
        return

    today = wat_date()

    if not ACCOUNT.trading_date:

        ACCOUNT.trading_date = today
        ACCOUNT.daily_start_balance = account.balance
        ACCOUNT.peak_equity = account.equity

    if ACCOUNT.peak_equity <= 0:
        ACCOUNT.peak_equity = account.equity

    ACCOUNT.peak_equity = max(
        ACCOUNT.peak_equity,
        account.equity,
    )

    if ACCOUNT.trading_date != today:

        ACCOUNT.trading_date = today
        ACCOUNT.daily_start_balance = account.balance
        ACCOUNT.daily_trades = 0
        ACCOUNT.daily_profit = 0.0
        ACCOUNT.daily_loss = 0.0

        # Do NOT automatically clear a serious risk halt.
        # It must be deliberately cleared after review.

        save_state()

    ACCOUNT.daily_profit = max(
        0.0,
        account.equity - ACCOUNT.daily_start_balance,
    )

    ACCOUNT.daily_loss = max(
        0.0,
        ACCOUNT.daily_start_balance - account.equity,
    )


def current_drawdown_percent() -> float:

    account = mt5.account_info()

    if account is None or ACCOUNT.peak_equity <= 0:
        return 0.0

    return max(
        0.0,
        (
            (ACCOUNT.peak_equity - account.equity)
            /
            ACCOUNT.peak_equity
        ) * 100,
    )


def risk_gate() -> Tuple[bool, str]:

    update_account_state()

    dd = current_drawdown_percent()

    if ACCOUNT.halted:
        return False, ACCOUNT.halt_reason

    if ACCOUNT.daily_start_balance > 0:

        daily_loss_pct = (
            ACCOUNT.daily_loss
            /
            ACCOUNT.daily_start_balance
        ) * 100

        if daily_loss_pct >= DAILY_LOSS_LIMIT_PERCENT:

            ACCOUNT.halted = True
            ACCOUNT.halt_reason = (
                f"Daily loss limit reached "
                f"{daily_loss_pct:.2f}%"
            )

            save_state()

            return False, ACCOUNT.halt_reason

    if dd >= MAX_DRAWDOWN_PERCENT:

        ACCOUNT.halted = True
        ACCOUNT.halt_reason = (
            f"Maximum drawdown reached {dd:.2f}%"
        )

        save_state()

        return False, ACCOUNT.halt_reason

    if ACCOUNT.consecutive_losses >= MAX_CONSECUTIVE_LOSSES:

        ACCOUNT.halted = True
        ACCOUNT.halt_reason = (
            f"Maximum consecutive losses reached "
            f"{ACCOUNT.consecutive_losses}"
        )

        save_state()

        return False, ACCOUNT.halt_reason

    if ACCOUNT.daily_trades >= MAX_NEW_TRADES_PER_DAY:

        return False, "Daily trade limit reached"

    return True, "Risk OK"
# =============================================================================
# RICCHY OMEGA FUSION
# PART 2/5
# REGIME + STRUCTURE + LIQUIDITY + ZONES
# =============================================================================


# =============================================================================
# BASIC BIAS
# =============================================================================

def determine_bias(df: pd.DataFrame) -> str:

    if df is None or len(df) < 50:
        return "NEUTRAL"

    r = df.iloc[-1]

    if (
        r["close"] > r["ema20"]
        and r["ema20"] > r["ema50"]
        and r["ema50"] > r["ema200"]
    ):
        return "BULLISH"

    if (
        r["close"] < r["ema20"]
        and r["ema20"] < r["ema50"]
        and r["ema50"] < r["ema200"]
    ):
        return "BEARISH"

    return "NEUTRAL"


# =============================================================================
# MARKET REGIME
# =============================================================================

def detect_regime(df: pd.DataFrame) -> Dict:

    if df is None or len(df) < 60:

        return {
            "regime": "UNKNOWN",
            "volatility": "UNKNOWN",
            "strength": 0.0,
            "atr": 0.0,
            "atr_percent": 0.0,
            "adx": 0.0,
            "bias": "NEUTRAL",
        }

    r = df.iloc[-1]

    adx = float(r["adx"]) if pd.notna(r["adx"]) else 0.0
    atr = float(r["atr"]) if pd.notna(r["atr"]) else 0.0
    atr_percent = (
        float(r["atr_percent"])
        if pd.notna(r["atr_percent"])
        else 0.0
    )

    bias = determine_bias(df)

    if adx >= 28 and bias != "NEUTRAL":
        regime = "TREND"

    elif adx < 18:
        regime = "RANGE"

    elif adx < 24:
        regime = "TRANSITION"

    else:
        regime = "TREND"

    if atr_percent >= 0.20:
        volatility = "HIGH"

    elif atr_percent <= 0.05:
        volatility = "LOW"

    else:
        volatility = "NORMAL"

    return {
        "regime": regime,
        "volatility": volatility,
        "strength": min(100.0, adx * 2),
        "atr": atr,
        "atr_percent": atr_percent,
        "adx": adx,
        "bias": bias,
    }


# =============================================================================
# SWINGS
# =============================================================================

def swing_highs(
    df: pd.DataFrame,
    lookback: int = 3,
) -> List[Tuple[int, float]]:

    result = []

    if df is None:
        return result

    for i in range(
        lookback,
        len(df) - lookback,
    ):

        high = df.iloc[i]["high"]

        left = df.iloc[
            i - lookback:i
        ]["high"].max()

        right = df.iloc[
            i + 1:i + lookback + 1
        ]["high"].max()

        if high > left and high >= right:
            result.append((i, float(high)))

    return result


def swing_lows(
    df: pd.DataFrame,
    lookback: int = 3,
) -> List[Tuple[int, float]]:

    result = []

    if df is None:
        return result

    for i in range(
        lookback,
        len(df) - lookback,
    ):

        low = df.iloc[i]["low"]

        left = df.iloc[
            i - lookback:i
        ]["low"].min()

        right = df.iloc[
            i + 1:i + lookback + 1
        ]["low"].min()

        if low < left and low <= right:
            result.append((i, float(low)))

    return result


# =============================================================================
# STRUCTURE
# =============================================================================

def structure_state(
    df: pd.DataFrame,
) -> Dict:

    if df is None or len(df) < 40:

        return {
            "bullish": False,
            "bearish": False,
            "mss_bullish": False,
            "mss_bearish": False,
            "bos_bullish": False,
            "bos_bearish": False,
        }

    highs = swing_highs(df, 3)
    lows = swing_lows(df, 3)

    if not highs or not lows:

        return {
            "bullish": False,
            "bearish": False,
            "mss_bullish": False,
            "mss_bearish": False,
            "bos_bullish": False,
            "bos_bearish": False,
        }

    last_close = float(df.iloc[-1]["close"])

    recent_high = highs[-1][1]
    recent_low = lows[-1][1]

    previous_high = highs[-2][1] if len(highs) >= 2 else recent_high
    previous_low = lows[-2][1] if len(lows) >= 2 else recent_low

    bos_bullish = last_close > recent_high
    bos_bearish = last_close < recent_low

    bullish = (
        recent_high > previous_high
        and recent_low > previous_low
    )

    bearish = (
        recent_high < previous_high
        and recent_low < previous_low
    )

    # MSS approximation:
    # current close breaks the latest opposing swing.

    mss_bullish = last_close > recent_high
    mss_bearish = last_close < recent_low

    return {
        "bullish": bullish,
        "bearish": bearish,
        "mss_bullish": mss_bullish,
        "mss_bearish": mss_bearish,
        "bos_bullish": bos_bullish,
        "bos_bearish": bos_bearish,
        "recent_high": recent_high,
        "recent_low": recent_low,
    }


# =============================================================================
# LIQUIDITY SWEEPS
# =============================================================================

def liquidity_sweep(
    df: pd.DataFrame,
    direction: str,
) -> bool:

    if df is None or len(df) < 30:
        return False

    r = df.iloc[-1]

    recent = df.iloc[-21:-1]

    if recent.empty:
        return False

    if direction == "BUY":

        prior_low = float(recent["low"].min())

        swept = float(r["low"]) < prior_low
        recovered = float(r["close"]) > prior_low

        return swept and recovered

    if direction == "SELL":

        prior_high = float(recent["high"].max())

        swept = float(r["high"]) > prior_high
        recovered = float(r["close"]) < prior_high

        return swept and recovered

    return False


# =============================================================================
# DISPLACEMENT
# =============================================================================

def displacement(
    df: pd.DataFrame,
    direction: str,
) -> bool:

    if df is None or len(df) < 25:
        return False

    recent = df.iloc[-16:-1]

    if recent.empty:
        return False

    average_body = float(
        recent["body"].mean()
    )

    if average_body <= 0:
        return False

    r = df.iloc[-1]

    body = float(r["body"])

    strong = body >= average_body * 1.40

    if direction == "BUY":
        return strong and bool(r["bullish"])

    if direction == "SELL":
        return strong and bool(r["bearish"])

    return False


# =============================================================================
# FVG DETECTION
# =============================================================================

def find_fvg(
    df: pd.DataFrame,
    direction: str,
) -> Optional[Dict]:

    if df is None or len(df) < 10:
        return None

    # Search recent candles only.
    # This prevents ancient zones from acting as confirmation.

    start = max(2, len(df) - 50)

    for i in range(
        len(df) - 2,
        start - 1,
        -1,
    ):

        a = df.iloc[i - 2]
        b = df.iloc[i - 1]
        c = df.iloc[i]

        if direction == "BUY":

            # Bullish FVG:
            # candle A high below candle C low

            if float(c["low"]) > float(a["high"]):

                low = float(a["high"])
                high = float(c["low"])

                return {
                    "low": low,
                    "high": high,
                    "index": i,
                    "type": "BULLISH_FVG",
                }

        elif direction == "SELL":

            if float(c["high"]) < float(a["low"]):

                low = float(c["high"])
                high = float(a["low"])

                return {
                    "low": low,
                    "high": high,
                    "index": i,
                    "type": "BEARISH_FVG",
                }

    return None


# =============================================================================
# ORDER BLOCK
# =============================================================================

def find_order_block(
    df: pd.DataFrame,
    direction: str,
) -> Optional[Dict]:

    if df is None or len(df) < 15:
        return None

    # Only inspect recent candles.
    start = max(2, len(df) - 40)

    for i in range(
        len(df) - 2,
        start - 1,
        -1,
    ):

        candle = df.iloc[i]

        if direction == "BUY":

            if bool(candle["bearish"]):

                return {
                    "low": float(candle["low"]),
                    "high": float(candle["high"]),
                    "index": i,
                    "type": "BULLISH_OB",
                }

        elif direction == "SELL":

            if bool(candle["bullish"]):

                return {
                    "low": float(candle["low"]),
                    "high": float(candle["high"]),
                    "index": i,
                    "type": "BEARISH_OB",
                }

    return None


# =============================================================================
# ZONE PROXIMITY
# =============================================================================

def price_near_zone(
    price: float,
    zone: Optional[Dict],
    atr: float,
    tolerance_atr: float = 0.35,
) -> bool:

    if zone is None or atr <= 0:
        return False

    low = float(zone["low"])
    high = float(zone["high"])

    tolerance = atr * tolerance_atr

    return (
        low - tolerance
        <= price
        <= high + tolerance
    )


# =============================================================================
# CANDLE CONFIRMATION
# =============================================================================

def candle_confirmation(
    df: pd.DataFrame,
    direction: str,
) -> bool:

    if df is None or len(df) < 3:
        return False

    prev = df.iloc[-2]
    cur = df.iloc[-1]

    if direction == "BUY":

        engulfing = (
            bool(cur["bullish"])
            and float(cur["open"]) <= float(prev["close"])
            and float(cur["close"]) >= float(prev["open"])
        )

        rejection = (
            float(cur["lower_wick"])
            > float(cur["body"]) * 1.2
            and float(cur["close"]) > float(cur["open"])
        )

        return engulfing or rejection

    if direction == "SELL":

        engulfing = (
            bool(cur["bearish"])
            and float(cur["open"]) >= float(prev["close"])
            and float(cur["close"]) <= float(prev["open"])
        )

        rejection = (
            float(cur["upper_wick"])
            > float(cur["body"]) * 1.2
            and float(cur["close"]) < float(cur["open"])
        )

        return engulfing or rejection

    return False


# =============================================================================
# MARKET SNAPSHOT
# =============================================================================

def build_snapshot(symbol: str) -> Optional[Dict]:

    data = {}

    for tf, count in BARS.items():

        df = get_rates(symbol, tf, count)

        if df is None:
            return None

        df = add_indicators(df)

        data[tf] = df

    regime = detect_regime(data[TF_M30])

    biases = {
        "H4": determine_bias(data[TF_H4]),
        "H1": determine_bias(data[TF_H1]),
        "M30": determine_bias(data[TF_M30]),
        "M15": determine_bias(data[TF_M15]),
        "M5": determine_bias(data[TF_M5]),
        "M1": determine_bias(data[TF_M1]),
    }

    return {
        "data": data,
        "regime": regime,
        "biases": biases,
        "structure": structure_state(data[TF_M15]),
    }


# =============================================================================
# DIRECTION SELECTION
# =============================================================================

def select_direction(
    snapshot: Dict,
) -> Optional[str]:

    biases = snapshot["biases"]
    structure = snapshot["structure"]

    bull_score = 0
    bear_score = 0

    for tf, weight in [
        ("H4", 3),
        ("H1", 3),
        ("M30", 3),
        ("M15", 2),
        ("M5", 1),
    ]:

        if biases[tf] == "BULLISH":
            bull_score += weight

        elif biases[tf] == "BEARISH":
            bear_score += weight

    if structure.get("mss_bullish"):
        bull_score += 3

    if structure.get("mss_bearish"):
        bear_score += 3

    if bull_score > bear_score:
        return "BUY"

    if bear_score > bull_score:
        return "SELL"

    return None


# =============================================================================
# SETUP STYLE
# =============================================================================

def determine_setup(
    snapshot: Dict,
    direction: str,
) -> str:

    regime = snapshot["regime"]["regime"]
    volatility = snapshot["regime"]["volatility"]

    if regime == "TREND":
        return "TREND_RETEST"

    if regime == "TRANSITION":
        return "TRANSITION_LIQUIDITY"

    if regime == "RANGE":
        return "RANGE_LIQUIDITY"

    if volatility == "HIGH":
        return "VOLATILITY_RETEST"

    return "STRUCTURE_RETEST"
# =============================================================================
# RICCHY OMEGA FUSION
# PART 3/5
# SCORING + RISK + SIGNAL GENERATION + NEWS
# =============================================================================


# =============================================================================
# OPEN POSITION HELPERS
# =============================================================================

def bot_positions():

    positions = mt5.positions_get()

    if positions is None:
        return []

    return [
        p for p in positions
        if int(getattr(p, "magic", 0)) == MAGIC_NUMBER
    ]


def symbol_bot_position(symbol: str) -> bool:

    return any(
        p.symbol == symbol
        for p in bot_positions()
    )


# =============================================================================
# SPREAD
# =============================================================================

def spread_info(
    symbol: str,
) -> Tuple[float, float]:

    info = get_symbol_info(symbol)
    tick = get_tick(symbol)

    if info is None or tick is None:
        return 999999.0, 999999.0

    spread_points = (
        float(tick.ask - tick.bid)
        /
        float(info.point)
    )

    return spread_points, float(tick.ask - tick.bid)


def spread_allowed(
    symbol: str,
    atr: float,
) -> bool:

    spread_points, spread_price = spread_info(symbol)

    if is_gold(symbol):

        if spread_points > MAX_GOLD_SPREAD_POINTS:
            return False

        if atr <= 0:
            return False

        if spread_price / atr > MAX_GOLD_SPREAD_ATR_RATIO:
            return False

        return True

    return spread_points <= MAX_SPREAD_POINTS


# =============================================================================
# COOLDOWN
# =============================================================================

def cooldown_allowed(symbol: str) -> bool:

    last = LAST_SIGNAL_TIME.get(symbol)

    if last is None:
        return True

    elapsed = time.time() - last

    return elapsed >= COOLDOWN_MINUTES * 60


# =============================================================================
# RISK PERCENT
# =============================================================================

def effective_risk_percent(
    symbol: str,
    setup: str,
    news_multiplier: float = 1.0,
) -> float:

    risk = BASE_RISK_PERCENT

    if is_gold(symbol):
        risk *= GOLD_RISK_MULTIPLIER

    if ACCOUNT.consecutive_losses >= LOSS_STREAK_REDUCTION_AFTER:
        risk *= LOSS_STREAK_RISK_MULTIPLIER

    if setup == "TRANSITION_LIQUIDITY":
        risk *= 0.75

    if setup == "RANGE_LIQUIDITY":
        risk *= 0.60

    if setup == "VOLATILITY_RETEST":
        risk *= 0.75

    risk *= news_multiplier

    return min(
        HARD_MAX_RISK_PERCENT,
        max(0.05, risk),
    )


# =============================================================================
# LOT SIZE
# =============================================================================

def calculate_lot(
    symbol: str,
    entry: float,
    sl: float,
    risk_percent: float,
) -> float:

    account = mt5.account_info()
    info = get_symbol_info(symbol)

    if account is None or info is None:
        return 0.0

    distance = abs(entry - sl)

    if distance <= 0:
        return 0.0

    tick_size = float(info.trade_tick_size)
    tick_value = float(info.trade_tick_value)

    if tick_size <= 0 or tick_value <= 0:
        return 0.0

    risk_money = (
        float(account.balance)
        * risk_percent
        / 100.0
    )

    money_per_lot = (
        distance / tick_size
    ) * tick_value

    if money_per_lot <= 0:
        return 0.0

    lot = risk_money / money_per_lot

    return normalize_volume(symbol, lot)


# =============================================================================
# STOP / TARGET
# =============================================================================

def calculate_levels(
    symbol: str,
    df: pd.DataFrame,
    direction: str,
    regime: str,
) -> Optional[Tuple[float, float, float, float]]:

    tick = get_tick(symbol)

    if tick is None:
        return None

    entry = (
        float(tick.ask)
        if direction == "BUY"
        else float(tick.bid)
    )

    atr = float(df.iloc[-1]["atr"])

    if atr <= 0:
        return None

    recent = df.iloc[-30:]

    recent_low = float(recent["low"].min())
    recent_high = float(recent["high"].max())

    if direction == "BUY":

        structural_sl = recent_low - atr * 0.15

        if regime == "TREND":
            volatility_sl = entry - atr * 1.25
        else:
            volatility_sl = entry - atr * 1.00

        sl = min(
            structural_sl,
            volatility_sl,
        )

        risk_distance = entry - sl

        if risk_distance <= 0:
            return None

        tp = entry + risk_distance * TARGET_RR

    else:

        structural_sl = recent_high + atr * 0.15

        if regime == "TREND":
            volatility_sl = entry + atr * 1.25
        else:
            volatility_sl = entry + atr * 1.00

        sl = max(
            structural_sl,
            volatility_sl,
        )

        risk_distance = sl - entry

        if risk_distance <= 0:
            return None

        tp = entry - risk_distance * TARGET_RR

    entry = normalize_price(symbol, entry)
    sl = normalize_price(symbol, sl)
    tp = normalize_price(symbol, tp)

    rr = (
        abs(tp - entry)
        /
        abs(entry - sl)
    )

    return entry, sl, tp, rr


# =============================================================================
# BROKER STOP VALIDATION
# =============================================================================

def validate_stops(
    symbol: str,
    direction: str,
    entry: float,
    sl: float,
    tp: float,
) -> bool:

    info = get_symbol_info(symbol)

    if info is None:
        return False

    point = float(info.point)

    stop_level = max(
        int(getattr(info, "trade_stops_level", 0)),
        int(getattr(info, "trade_freeze_level", 0)),
    )

    minimum_distance = stop_level * point

    if direction == "BUY":

        if not (sl < entry < tp):
            return False

        if minimum_distance > 0:

            if entry - sl < minimum_distance:
                return False

            if tp - entry < minimum_distance:
                return False

    elif direction == "SELL":

        if not (tp < entry < sl):
            return False

        if minimum_distance > 0:

            if sl - entry < minimum_distance:
                return False

            if entry - tp < minimum_distance:
                return False

    else:
        return False

    return True


# =============================================================================
# NEWS
# =============================================================================

class NewsManager:

    def __init__(self):
        self.events = []
        self.last_refresh = 0.0

    def currencies(self, symbol: str) -> List[str]:

        if is_gold(symbol):
            return ["USD"]

        base = symbol[:3]
        quote = symbol[3:6]

        return [base, quote]

    def refresh(self):

        if not ENABLE_NEWS_FILTER:
            return

        if not TRADING_ECONOMICS_API_KEY:
            return

        now = time.time()

        if now - self.last_refresh < 600:
            return

        self.last_refresh = now

        try:

            start = (
                utc_now()
                - timedelta(hours=1)
            ).strftime("%Y-%m-%dT%H:%M:%S")

            end = (
                utc_now()
                + timedelta(hours=24)
            ).strftime("%Y-%m-%dT%H:%M:%S")

            url = (
                "https://api.tradingeconomics.com/calendar/country/All"
                f"?c={TRADING_ECONOMICS_API_KEY}"
                f"&d1={start}&d2={end}"
            )

            response = requests.get(
                url,
                timeout=10,
            )

            if response.status_code != 200:
                self.events = []
                return

            data = response.json()

            self.events = data if isinstance(data, list) else []

            log(
                f"News calendar refreshed: "
                f"{len(self.events)} events"
            )

        except Exception as exc:

            log(f"News refresh error: {exc}")
            self.events = []

    def multiplier(
        self,
        symbol: str,
    ) -> Tuple[float, str]:

        if not ENABLE_NEWS_FILTER:
            return 1.0, "NEWS_OFF"

        if not self.events:
            return 1.0, "NO_NEWS_DATA"

        currencies = self.currencies(symbol)

        now = utc_now()

        for event in self.events:

            try:

                country = str(
                    event.get("country", "")
                ).upper()

                importance = int(
                    event.get("importance", 0)
                    or 0
                )

                date_text = (
                    event.get("date")
                    or event.get("Date")
                )

                if not date_text:
                    continue

                event_time = pd.to_datetime(
                    date_text,
                    utc=True,
                    errors="coerce",
                )

                if pd.isna(event_time):
                    continue

                event_dt = event_time.to_pydatetime()

                minutes = (
                    event_dt - now
                ).total_seconds() / 60.0

                if country not in currencies:
                    continue

                if (
                    -NEWS_BLOCK_AFTER_MINUTES
                    <= minutes
                    <= NEWS_BLOCK_BEFORE_MINUTES
                ):

                    if importance >= 3:
                        return 0.0, "HIGH_IMPACT_NEWS"

                    if importance == 2:
                        return (
                            NEWS_RISK_REDUCTION,
                            "MEDIUM_IMPACT_NEWS",
                        )

            except Exception:
                continue

        return 1.0, "NEWS_CLEAR"


NEWS = NewsManager()


# =============================================================================
# CONFIRMATIONS
# =============================================================================

def build_confirmations(
    symbol: str,
    snapshot: Dict,
    direction: str,
) -> Tuple[List[str], float]:

    data = snapshot["data"]
    biases = snapshot["biases"]
    regime = snapshot["regime"]

    confirmations = []
    score = 0.0

    # -----------------------------------------------------------------
    # 1. HTF CONTEXT - 25
    # -----------------------------------------------------------------

    htf_biases = [
        biases["H4"],
        biases["H1"],
        biases["M30"],
    ]

    htf_bull = htf_biases.count("BULLISH")
    htf_bear = htf_biases.count("BEARISH")

    if direction == "BUY" and htf_bull >= 2:

        confirmations.append("HTF_ALIGNMENT")
        score += 25

    elif direction == "SELL" and htf_bear >= 2:

        confirmations.append("HTF_ALIGNMENT")
        score += 25

    # -----------------------------------------------------------------
    # 2. REGIME - 15
    # -----------------------------------------------------------------

    if regime["regime"] == "TREND":

        if (
            direction == "BUY"
            and regime["bias"] == "BULLISH"
        ):

            confirmations.append("TREND_REGIME")
            score += 15

        elif (
            direction == "SELL"
            and regime["bias"] == "BEARISH"
        ):

            confirmations.append("TREND_REGIME")
            score += 15

    elif regime["regime"] == "TRANSITION":

        confirmations.append("TRANSITION")
        score += 8

    elif regime["regime"] == "RANGE":

        confirmations.append("RANGE")
        score += 4

    # -----------------------------------------------------------------
    # 3. LIQUIDITY - 20
    # -----------------------------------------------------------------

    m15 = data[TF_M15]

    if liquidity_sweep(m15, direction):

        confirmations.append("LIQUIDITY_SWEEP")
        score += 20

    # -----------------------------------------------------------------
    # 4. STRUCTURE - 20
    # -----------------------------------------------------------------

    structure = snapshot["structure"]

    structure_ok = (
        direction == "BUY"
        and (
            structure.get("mss_bullish")
            or structure.get("bos_bullish")
            or structure.get("bullish")
        )
    ) or (
        direction == "SELL"
        and (
            structure.get("mss_bearish")
            or structure.get("bos_bearish")
            or structure.get("bearish")
        )
    )

    if structure_ok:

        confirmations.append("STRUCTURE")
        score += 20

    # -----------------------------------------------------------------
    # 5. DISPLACEMENT - 15
    # -----------------------------------------------------------------

    m5 = data[TF_M5]

    if (
        displacement(m15, direction)
        or displacement(m5, direction)
    ):

        confirmations.append("DISPLACEMENT")
        score += 15

    # -----------------------------------------------------------------
    # 6. FRESH ZONE RETEST - 15
    # -----------------------------------------------------------------

    tick = get_tick(symbol)

    if tick is not None:

        price = (
            float(tick.ask)
            if direction == "BUY"
            else float(tick.bid)
        )

        atr = float(m15.iloc[-1]["atr"])

        fvg = find_fvg(
            m15,
            direction,
        )

        ob = find_order_block(
            m15,
            direction,
        )

        zone_ok = (
            price_near_zone(
                price,
                fvg,
                atr,
                0.35,
            )
            or
            price_near_zone(
                price,
                ob,
                atr,
                0.35,
            )
        )

        if zone_ok:

            confirmations.append("FRESH_ZONE_RETEST")
            score += 15

    # -----------------------------------------------------------------
    # 7. CANDLE / MICRO CONFIRMATION - 10
    # -----------------------------------------------------------------

    if candle_confirmation(
        m5,
        direction,
    ):

        confirmations.append("MICRO_CONFIRMATION")
        score += 10

    return confirmations, score


# =============================================================================
# SIGNAL QUALITY RULES
# =============================================================================

def required_score(
    symbol: str,
    regime: str,
    volatility: str,
) -> float:

    if is_gold(symbol):
        threshold = MIN_GOLD_SCORE
    else:
        threshold = MIN_NORMAL_SCORE

    if regime == "TRANSITION":
        threshold += 4

    if volatility == "HIGH":
        threshold += 4

    return threshold


def signal_quality_ok(
    symbol: str,
    snapshot: Dict,
    confirmations: List[str],
    score: float,
) -> bool:

    regime = snapshot["regime"]["regime"]
    volatility = snapshot["regime"]["volatility"]

    required = required_score(
        symbol,
        regime,
        volatility,
    )

    # We require real structural components.
    has_structure = "STRUCTURE" in confirmations
    has_liquidity = "LIQUIDITY_SWEEP" in confirmations
    has_displacement = "DISPLACEMENT" in confirmations
    has_zone = "FRESH_ZONE_RETEST" in confirmations

    # Avoid low-quality “indicator stacking”.
    if not has_structure:
        return False

    if not has_liquidity and not has_displacement:
        return False

    if not has_zone:
        return False

    # Range trading requires additional caution.
    if regime == "RANGE":

        if not has_liquidity:
            return False

        if score < required + 5:
            return False

    return score >= required


# =============================================================================
# BUILD SIGNAL
# =============================================================================

def generate_signal(
    symbol: str,
    snapshot: Dict,
) -> Optional[TradeSignal]:

    allowed, reason = risk_gate()

    if not allowed:
        return None

    if not session_allowed():
        return None

    if ACCOUNT.daily_trades >= MAX_NEW_TRADES_PER_DAY:
        return None

    if len(bot_positions()) >= MAX_OPEN_POSITIONS:
        return None

    if ONE_POSITION_PER_SYMBOL and symbol_bot_position(symbol):
        return None

    if not cooldown_allowed(symbol):
        return None

    regime_data = snapshot["regime"]

    # Extreme volatility is not automatically a buy/sell signal.
    if regime_data["volatility"] == "HIGH":

        if is_gold(symbol):
            if regime_data["atr_percent"] > MAX_GOLD_ATR_PERCENT:
                return None

    direction = select_direction(snapshot)

    if direction is None:
        return None

    confirmations, score = build_confirmations(
        symbol,
        snapshot,
        direction,
    )

    if not signal_quality_ok(
        symbol,
        snapshot,
        confirmations,
        score,
    ):
        return None

    setup = determine_setup(
        snapshot,
        direction,
    )

    news_multiplier, news_reason = NEWS.multiplier(
        symbol
    )

    if news_multiplier <= 0:
        log(
            f"{symbol}: blocked by {news_reason}"
        )
        return None

    m15 = snapshot["data"][TF_M15]

    levels = calculate_levels(
        symbol,
        m15,
        direction,
        regime_data["regime"],
    )

    if levels is None:
        return None

    entry, sl, tp, rr = levels

    if rr < MIN_RR:
        return None

    if not validate_stops(
        symbol,
        direction,
        entry,
        sl,
        tp,
    ):
        return None

    risk_percent = effective_risk_percent(
        symbol,
        setup,
        news_multiplier,
    )

    lot = calculate_lot(
        symbol,
        entry,
        sl,
        risk_percent,
    )

    if lot <= 0:
        return None

    atr = float(m15.iloc[-1]["atr"])
    atr_percent = float(
        m15.iloc[-1]["atr_percent"]
    )

    reason_text = (
        f"{direction} | "
        f"{setup} | "
        f"regime={regime_data['regime']} | "
        f"vol={regime_data['volatility']} | "
        f"score={score:.0f} | "
        f"RR={rr:.2f} | "
        f"news={news_reason}"
    )

    return TradeSignal(
        symbol=symbol,
        direction=direction,
        setup=setup,
        regime=regime_data["regime"],
        score=score,
        required_score=required_score(
            symbol,
            regime_data["regime"],
            regime_data["volatility"],
        ),
        entry=entry,
        sl=sl,
        tp=tp,
        rr=rr,
        atr=atr,
        atr_percent=atr_percent,
        risk_percent=risk_percent,
        lot=lot,
        reason=reason_text,
        confirmations=confirmations,
    )
# =============================================================================
# RICCHY OMEGA FUSION
# PART 4/5
# EXECUTION + BROKER VALIDATION + POSITION MANAGEMENT
# =============================================================================


# =============================================================================
# FILLING MODE
# =============================================================================

def get_filling_mode(symbol: str) -> int:

    info = get_symbol_info(symbol)

    if info is None:
        return mt5.ORDER_FILLING_FOK

    execution_mode = getattr(
        info,
        "trade_exemode",
        None,
    )

    filling_flags = int(
        getattr(info, "filling_mode", 0)
    )

    # Market execution cannot use RETURN.
    if execution_mode == mt5.SYMBOL_TRADE_EXECUTION_MARKET:

        if filling_flags & mt5.ORDER_FILLING_IOC:
            return mt5.ORDER_FILLING_IOC

        if filling_flags & mt5.ORDER_FILLING_FOK:
            return mt5.ORDER_FILLING_FOK

        # Safe fallback.
        return mt5.ORDER_FILLING_IOC

    # For non-market execution, RETURN is normally valid.
    return mt5.ORDER_FILLING_RETURN


def alternate_filling_modes(symbol: str) -> List[int]:

    info = get_symbol_info(symbol)

    if info is None:
        return [mt5.ORDER_FILLING_FOK]

    execution_mode = getattr(
        info,
        "trade_exemode",
        None,
    )

    flags = int(
        getattr(info, "filling_mode", 0)
    )

    modes = []

    if execution_mode != mt5.SYMBOL_TRADE_EXECUTION_MARKET:
        modes.append(mt5.ORDER_FILLING_RETURN)

    if flags & mt5.ORDER_FILLING_IOC:
        modes.append(mt5.ORDER_FILLING_IOC)

    if flags & mt5.ORDER_FILLING_FOK:
        modes.append(mt5.ORDER_FILLING_FOK)

    # Remove duplicates while preserving order.
    result = []

    for mode in modes:

        if mode not in result:
            result.append(mode)

    return result


# =============================================================================
# ORDER CHECK
# =============================================================================

def check_order(
    request: Dict,
) -> bool:

    try:

        result = mt5.order_check(request)

        if result is None:
            log(
                f"order_check returned None: "
                f"{mt5.last_error()}"
            )
            return False

        # 0 normally means successful validation.
        if int(result.retcode) != 0:

            log(
                f"order_check failed: "
                f"retcode={result.retcode} "
                f"comment={result.comment}"
            )

            return False

        return True

    except Exception as exc:

        log(f"order_check exception: {exc}")
        return False


# =============================================================================
# OPEN POSITION
# =============================================================================

def open_trade(
    signal: TradeSignal,
) -> bool:

    global ACCOUNT

    allowed, reason = risk_gate()

    if not allowed:

        log(
            f"Trade rejected by risk gate: {reason}"
        )

        return False

    if ACCOUNT.daily_trades >= MAX_NEW_TRADES_PER_DAY:
        return False

    if len(bot_positions()) >= MAX_OPEN_POSITIONS:
        return False

    if (
        ONE_POSITION_PER_SYMBOL
        and symbol_bot_position(signal.symbol)
    ):
        return False

    tick = get_tick(signal.symbol)

    if tick is None:
        return False

    # Refresh price immediately before execution.
    entry = (
        float(tick.ask)
        if signal.direction == "BUY"
        else float(tick.bid)
    )

    # Preserve original SL distance while adapting
    # entry to the current market price.

    risk_distance = abs(
        signal.entry - signal.sl
    )

    if risk_distance <= 0:
        return False

    if signal.direction == "BUY":

        sl = entry - risk_distance
        tp = entry + risk_distance * signal.rr

        order_type = mt5.ORDER_TYPE_BUY

    else:

        sl = entry + risk_distance
        tp = entry - risk_distance * signal.rr

        order_type = mt5.ORDER_TYPE_SELL

    entry = normalize_price(
        signal.symbol,
        entry,
    )

    sl = normalize_price(
        signal.symbol,
        sl,
    )

    tp = normalize_price(
        signal.symbol,
        tp,
    )

    if not validate_stops(
        signal.symbol,
        signal.direction,
        entry,
        sl,
        tp,
    ):
        log(
            f"{signal.symbol}: broker stop validation failed."
        )
        return False

    volume = normalize_volume(
        signal.symbol,
        signal.lot,
    )

    if volume <= 0:
        return False

    filling_modes = alternate_filling_modes(
        signal.symbol
    )

    if not filling_modes:
        filling_modes = [
            get_filling_mode(signal.symbol)
        ]

    request_base = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": signal.symbol,
        "volume": volume,
        "type": order_type,
        "price": entry,
        "sl": sl,
        "tp": tp,
        "deviation": DEVIATION,
        "magic": MAGIC_NUMBER,
        "comment": "RICCHY_FUSION",
        "type_time": mt5.ORDER_TIME_GTC,
    }

    # -----------------------------------------------------------------
    # DRY RUN
    # -----------------------------------------------------------------

    if DRY_RUN or not LIVE_TRADING:

        ACCOUNT.daily_trades += 1

        LAST_SIGNAL_TIME[
            signal.symbol
        ] = time.time()

        journal_event(
            event="DRY_RUN_ENTRY",
            symbol=signal.symbol,
            direction=signal.direction,
            setup=signal.setup,
            score=signal.score,
            entry=entry,
            sl=sl,
            tp=tp,
            lot=volume,
            note=signal.reason,
        )

        save_state()

        log(
            f"[DRY RUN] {signal.symbol} "
            f"{signal.direction} "
            f"lot={volume} "
            f"score={signal.score:.0f} "
            f"RR={signal.rr:.2f}"
        )

        TELEGRAM.send(
            f"🧪 DRY RUN\n"
            f"{BOT_NAME}\n"
            f"{signal.symbol} {signal.direction}\n"
            f"Score: {signal.score:.0f}\n"
            f"RR: {signal.rr:.2f}\n"
            f"Risk: {signal.risk_percent:.2f}%\n"
            f"Daily trades: "
            f"{ACCOUNT.daily_trades}/"
            f"{MAX_NEW_TRADES_PER_DAY}"
        )

        return True

    # -----------------------------------------------------------------
    # LIVE EXECUTION
    # -----------------------------------------------------------------

    for attempt in range(1, ORDER_RETRIES + 1):

        for filling in filling_modes:

            request = dict(request_base)
            request["type_filling"] = filling

            if not check_order(request):

                continue

            try:

                result = mt5.order_send(
                    request
                )

            except Exception as exc:

                log(
                    f"order_send exception "
                    f"attempt={attempt}: {exc}"
                )

                continue

            if result is None:

                log(
                    f"order_send returned None "
                    f"attempt={attempt}"
                )

                continue

            if result.retcode in (
                mt5.TRADE_RETCODE_DONE,
                mt5.TRADE_RETCODE_PLACED,
                mt5.TRADE_RETCODE_DONE_PARTIAL,
            ):

                ACCOUNT.daily_trades += 1

                LAST_SIGNAL_TIME[
                    signal.symbol
                ] = time.time()

                ticket = int(
                    result.order
                    or result.deal
                    or 0
                )

                position_ticket = ticket

                # Locate the actual position when possible.
                time.sleep(0.5)

                positions = mt5.positions_get(
                    symbol=signal.symbol
                )

                if positions:

                    candidates = [
                        p for p in positions
                        if int(
                            getattr(
                                p,
                                "magic",
                                0,
                            )
                        ) == MAGIC_NUMBER
                    ]

                    if candidates:

                        newest = max(
                            candidates,
                            key=lambda p: int(
                                getattr(
                                    p,
                                    "time",
                                    0,
                                )
                            ),
                        )

                        position_ticket = int(
                            newest.ticket
                        )

                POSITION_STATES[
                    position_ticket
                ] = PositionState(
                    ticket=position_ticket,
                    symbol=signal.symbol,
                    direction=signal.direction,
                    entry=entry,
                    initial_sl=sl,
                    initial_tp=tp,
                    initial_risk=abs(entry - sl),
                    initial_volume=volume,
                )

                journal_event(
                    event="LIVE_ENTRY",
                    symbol=signal.symbol,
                    direction=signal.direction,
                    setup=signal.setup,
                    score=signal.score,
                    entry=entry,
                    sl=sl,
                    tp=tp,
                    lot=volume,
                    note=signal.reason,
                )

                save_state()

                log(
                    f"LIVE TRADE OPENED | "
                    f"{signal.symbol} "
                    f"{signal.direction} "
                    f"ticket={position_ticket}"
                )

                TELEGRAM.send(
                    f"🚀 TRADE OPENED\n"
                    f"{BOT_NAME}\n"
                    f"{signal.symbol} "
                    f"{signal.direction}\n"
                    f"Score: {signal.score:.0f}\n"
                    f"RR: {signal.rr:.2f}\n"
                    f"Risk: {signal.risk_percent:.2f}%\n"
                    f"Daily: "
                    f"{ACCOUNT.daily_trades}/"
                    f"{MAX_NEW_TRADES_PER_DAY}"
                )

                return True

            log(
                f"Order failed | "
                f"{signal.symbol} | "
                f"retcode={result.retcode} | "
                f"comment={result.comment}"
            )

        time.sleep(0.7)

    return False


# =============================================================================
# POSITION STATE RECOVERY
# =============================================================================

def recover_position_states():

    positions = bot_positions()

    active_tickets = set()

    for p in positions:

        ticket = int(p.ticket)

        active_tickets.add(ticket)

        if ticket in POSITION_STATES:
            continue

        direction = (
            "BUY"
            if p.type == mt5.POSITION_TYPE_BUY
            else "SELL"
        )

        entry = float(p.price_open)
        sl = float(p.sl)

        if sl <= 0:
            continue

        POSITION_STATES[ticket] = PositionState(
            ticket=ticket,
            symbol=p.symbol,
            direction=direction,
            entry=entry,
            initial_sl=sl,
            initial_tp=float(p.tp),
            initial_risk=abs(entry - sl),
            initial_volume=float(p.volume),
        )

    stale = [
        ticket
        for ticket in POSITION_STATES
        if ticket not in active_tickets
    ]

    for ticket in stale:
        del POSITION_STATES[ticket]

    save_state()


# =============================================================================
# MODIFY POSITION SL / TP
# =============================================================================

def modify_position(
    position,
    sl: float,
    tp: Optional[float] = None,
) -> bool:

    info = get_symbol_info(position.symbol)

    if info is None:
        return False

    sl = normalize_price(
        position.symbol,
        sl,
    )

    if tp is None:
        tp = float(position.tp)

    else:
        tp = normalize_price(
            position.symbol,
            tp,
        )

    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": position.symbol,
        "position": int(position.ticket),
        "sl": sl,
        "tp": tp,
        "magic": MAGIC_NUMBER,
    }

    try:

        result = mt5.order_send(request)

        if result is None:
            return False

        return result.retcode in (
            mt5.TRADE_RETCODE_DONE,
            mt5.TRADE_RETCODE_PLACED,
        )

    except Exception as exc:

        log(
            f"Modify error {position.symbol}: {exc}"
        )

        return False


# =============================================================================
# CLOSE PARTIAL
# =============================================================================

def partial_close(
    position,
    percentage: float,
) -> bool:

    volume = float(position.volume)

    close_volume = normalize_volume(
        position.symbol,
        volume * percentage,
    )

    info = get_symbol_info(position.symbol)

    if info is None:
        return False

    if close_volume <= 0:
        return False

    # Never attempt to leave an invalid remainder.
    remainder = volume - close_volume

    if remainder > 0 and remainder < info.volume_min:

        close_volume = volume

    tick = get_tick(position.symbol)

    if tick is None:
        return False

    if position.type == mt5.POSITION_TYPE_BUY:

        order_type = mt5.ORDER_TYPE_SELL
        price = float(tick.bid)

    else:

        order_type = mt5.ORDER_TYPE_BUY
        price = float(tick.ask)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": position.symbol,
        "volume": close_volume,
        "type": order_type,
        "position": int(position.ticket),
        "price": price,
        "deviation": DEVIATION,
        "magic": MAGIC_NUMBER,
        "comment": "RICCHY_FUSION_PARTIAL",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": get_filling_mode(
            position.symbol
        ),
    }

    try:

        result = mt5.order_send(request)

        if result is None:
            return False

        return result.retcode in (
            mt5.TRADE_RETCODE_DONE,
            mt5.TRADE_RETCODE_PLACED,
            mt5.TRADE_RETCODE_DONE_PARTIAL,
        )

    except Exception as exc:

        log(
            f"Partial close error: {exc}"
        )

        return False


# =============================================================================
# POSITION MANAGEMENT
# =============================================================================

def manage_positions():

    recover_position_states()

    positions = bot_positions()

    for position in positions:

        ticket = int(position.ticket)

        state = POSITION_STATES.get(ticket)

        if state is None:
            continue

        if state.initial_risk <= 0:
            continue

        tick = get_tick(position.symbol)

        if tick is None:
            continue

        if state.direction == "BUY":

            current_price = float(tick.bid)

            profit_distance = (
                current_price - state.entry
            )

        else:

            current_price = float(tick.ask)

            profit_distance = (
                state.entry - current_price
            )

        current_r = (
            profit_distance
            /
            state.initial_risk
        )

        # -------------------------------------------------------------
        # BREAK EVEN
        # -------------------------------------------------------------

        if (
            current_r >= BREAK_EVEN_R
            and not state.breakeven_done
        ):

            if state.direction == "BUY":

                new_sl = (
                    state.entry
                    + state.initial_risk
                    * BREAK_EVEN_LOCK_R
                )

            else:

                new_sl = (
                    state.entry
                    - state.initial_risk
                    * BREAK_EVEN_LOCK_R
                )

            if modify_position(
                position,
                new_sl,
                position.tp,
            ):

                state.breakeven_done = True

                journal_event(
                    event="BREAKEVEN",
                    symbol=position.symbol,
                    direction=state.direction,
                    note=f"R={current_r:.2f}",
                )

                save_state()

        # -------------------------------------------------------------
        # PARTIAL PROFIT
        # -------------------------------------------------------------

        if (
            current_r >= PARTIAL_R
            and not state.partial_done
        ):

            if partial_close(
                position,
                PARTIAL_PERCENT,
            ):

                state.partial_done = True

                journal_event(
                    event="PARTIAL",
                    symbol=position.symbol,
                    direction=state.direction,
                    note=f"R={current_r:.2f}",
                )

                save_state()

        # -------------------------------------------------------------
        # TRAILING
        # -------------------------------------------------------------

        if current_r >= TRAIL_START_R:

            df = get_rates(
                position.symbol,
                TF_M5,
                80,
            )

            if df is None:
                continue

            df = add_indicators(df)

            atr = float(
                df.iloc[-1]["atr"]
            )

            if atr <= 0:
                continue

            if state.direction == "BUY":

                trail_sl = (
                    current_price
                    - atr * TRAIL_ATR_MULTIPLIER
                )

                # Never move SL backwards.
                if trail_sl <= float(position.sl):
                    continue

                # Never move below locked BE.
                minimum_sl = (
                    state.entry
                    + state.initial_risk
                    * BREAK_EVEN_LOCK_R
                )

                trail_sl = max(
                    trail_sl,
                    minimum_sl,
                )

            else:

                trail_sl = (
                    current_price
                    + atr * TRAIL_ATR_MULTIPLIER
                )

                if (
                    position.sl > 0
                    and trail_sl >= float(position.sl)
                ):
                    continue

                maximum_sl = (
                    state.entry
                    - state.initial_risk
                    * BREAK_EVEN_LOCK_R
                )

                trail_sl = min(
                    trail_sl,
                    maximum_sl,
                )

            if modify_position(
                position,
                trail_sl,
                position.tp,
            ):

                journal_event(
                    event="TRAIL",
                    symbol=position.symbol,
                    direction=state.direction,
                    note=f"R={current_r:.2f}",
                )
# =============================================================================
# RICCHY OMEGA FUSION
# PART 5/5
# PERFORMANCE GOVERNOR + LOSS TRACKING + SCANNER + MAIN LOOP
# =============================================================================


# =============================================================================
# DAILY TRADE RECONSTRUCTION
# =============================================================================

def reconstruct_daily_trade_count():

    today_start = wat_now().replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    utc_start = (
        today_start
        - timedelta(hours=WAT_OFFSET_HOURS)
    )

    utc_start_timestamp = int(
        utc_start.timestamp()
    )

    try:

        deals = mt5.history_deals_get(
            utc_start,
            utc_now(),
        )

        if deals is None:
            return

        count = 0

        for deal in deals:

            if int(
                getattr(
                    deal,
                    "magic",
                    0,
                )
            ) != MAGIC_NUMBER:
                continue

            entry_type = int(
                getattr(
                    deal,
                    "entry",
                    -1,
                )
            )

            # Count only entries, not exits.
            if entry_type == mt5.DEAL_ENTRY_IN:
                count += 1

        ACCOUNT.daily_trades = count

    except Exception as exc:

        log(
            f"Daily trade reconstruction error: {exc}"
        )


# =============================================================================
# CLOSED TRADE LOSS TRACKER
# =============================================================================

def update_loss_streak():

    global ACCOUNT

    try:

        start = utc_now() - timedelta(days=30)

        deals = mt5.history_deals_get(
            start,
            utc_now(),
        )

        if deals is None:
            return

        # Group exits by deal time.
        exits = []

        for deal in deals:

            if int(
                getattr(
                    deal,
                    "magic",
                    0,
                )
            ) != MAGIC_NUMBER:
                continue

            entry_type = int(
                getattr(
                    deal,
                    "entry",
                    -1,
                )
            )

            if entry_type not in (
                mt5.DEAL_ENTRY_OUT,
                mt5.DEAL_ENTRY_OUT_BY,
            ):
                continue

            exits.append(deal)

        exits.sort(
            key=lambda d: int(
                getattr(d, "time", 0)
            ),
            reverse=True,
        )

        streak = 0

        for deal in exits:

            profit = float(
                getattr(deal, "profit", 0.0)
            )

            commission = float(
                getattr(deal, "commission", 0.0)
            )

            swap = float(
                getattr(deal, "swap", 0.0)
            )

            net = (
                profit
                + commission
                + swap
            )

            if net < 0:

                streak += 1

            elif net > 0:

                break

        ACCOUNT.consecutive_losses = streak

        save_state()

    except Exception as exc:

        log(
            f"Loss tracker error: {exc}"
        )


# =============================================================================
# SETUP PERFORMANCE GOVERNOR
# =============================================================================

def setup_recent_performance(
    symbol: str,
    setup: str,
    lookback: int = 20,
) -> Dict:

    result = {
        "count": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0.0,
        "net": 0.0,
    }

    if not os.path.exists(JOURNAL_FILE):
        return result

    try:

        df = pd.read_csv(
            JOURNAL_FILE
        )

        if df.empty:
            return result

        trades = df[
            (df["event"] == "CLOSED")
            &
            (df["symbol"] == symbol)
            &
            (df["setup"] == setup)
        ].tail(lookback)

        if trades.empty:
            return result

        result["count"] = len(trades)

        wins = (
            pd.to_numeric(
                trades["result"],
                errors="coerce",
            ) > 0
        ).sum()

        losses = (
            pd.to_numeric(
                trades["result"],
                errors="coerce",
            ) < 0
        ).sum()

        net = pd.to_numeric(
            trades["result"],
            errors="coerce",
        ).sum()

        result["wins"] = int(wins)
        result["losses"] = int(losses)
        result["net"] = float(net)

        result["win_rate"] = (
            wins / len(trades)
        ) * 100

        return result

    except Exception:

        return result


def performance_governor(
    symbol: str,
    setup: str,
) -> Tuple[bool, float, str]:

    stats = setup_recent_performance(
        symbol,
        setup,
        20,
    )

    # Not enough data = don't punish a new setup.
    if stats["count"] < 10:
        return True, 1.0, "INSUFFICIENT_DATA"

    # If a setup has deteriorated badly recently,
    # stop adding exposure to it.
    if (
        stats["count"] >= 15
        and stats["win_rate"] < 30
    ):

        return (
            False,
            0.0,
            "SETUP_DETERIORATED",
        )

    # Moderate deterioration -> half risk.
    if (
        stats["count"] >= 10
        and stats["win_rate"] < 40
    ):

        return (
            True,
            0.50,
            "SETUP_RISK_REDUCED",
        )

    return True, 1.0, "SETUP_HEALTHY"


# =============================================================================
# SIGNAL SCANNER
# =============================================================================

def scan_symbol(symbol: str):

    if ACCOUNT.daily_trades >= MAX_NEW_TRADES_PER_DAY:
        return

    if len(bot_positions()) >= MAX_OPEN_POSITIONS:
        return

    actual_symbol = find_available_symbol(symbol)

    if actual_symbol is None:
        return

    spread_points, _ = spread_info(
        actual_symbol
    )

    if is_gold(actual_symbol):

        if spread_points > MAX_GOLD_SPREAD_POINTS:
            return

    else:

        if spread_points > MAX_SPREAD_POINTS:
            return

    snapshot = build_snapshot(
        actual_symbol
    )

    if snapshot is None:
        return

    regime = snapshot["regime"]

    log(
        f"{actual_symbol} | "
        f"regime={regime['regime']} | "
        f"vol={regime['volatility']} | "
        f"bias={regime['bias']} | "
        f"H4={snapshot['biases']['H4']} | "
        f"H1={snapshot['biases']['H1']} | "
        f"M30={snapshot['biases']['M30']}"
    )

    signal = generate_signal(
        actual_symbol,
        snapshot,
    )

    if signal is None:
        return

    # -------------------------------------------------------------
    # PERFORMANCE GOVERNOR
    # -------------------------------------------------------------

    allowed, multiplier, performance_reason = (
        performance_governor(
            signal.symbol,
            signal.setup,
        )
    )

    if not allowed:

        log(
            f"{signal.symbol}: setup paused "
            f"by performance governor."
        )

        return

    if multiplier < 1.0:

        signal.risk_percent *= multiplier

        signal.lot = calculate_lot(
            signal.symbol,
            signal.entry,
            signal.sl,
            signal.risk_percent,
        )

        if signal.lot <= 0:
            return

    log(
        f"SIGNAL | "
        f"{signal.symbol} "
        f"{signal.direction} | "
        f"score={signal.score:.0f}/"
        f"{signal.required_score:.0f} | "
        f"setup={signal.setup} | "
        f"risk={signal.risk_percent:.2f}% | "
        f"performance={performance_reason}"
    )

    opened = open_trade(signal)

    if opened:

        journal_event(
            event="SIGNAL_ACCEPTED",
            symbol=signal.symbol,
            direction=signal.direction,
            setup=signal.setup,
            score=signal.score,
            entry=signal.entry,
            sl=signal.sl,
            tp=signal.tp,
            lot=signal.lot,
            note=performance_reason,
        )


# =============================================================================
# MARKET SCAN
# =============================================================================

def scan_market():

    if ACCOUNT.daily_trades >= MAX_NEW_TRADES_PER_DAY:

        log(
            "Daily trade limit reached. "
            "No more entries today."
        )

        return

    if len(bot_positions()) >= MAX_OPEN_POSITIONS:
        return

    for symbol in SYMBOLS:

        if ACCOUNT.daily_trades >= MAX_NEW_TRADES_PER_DAY:
            break

        if len(bot_positions()) >= MAX_OPEN_POSITIONS:
            break

        try:

            scan_symbol(symbol)

        except Exception as exc:

            log(
                f"Scan error {symbol}: {exc}"
            )

            traceback.print_exc()


# =============================================================================
# CLOSED DEAL JOURNAL
# =============================================================================

def journal_new_closed_deals():

    try:

        start = utc_now() - timedelta(hours=24)

        deals = mt5.history_deals_get(
            start,
            utc_now(),
        )

        if deals is None:
            return

        processed = set(
            int(x)
            for x in ACCOUNT.processed_deals
        )

        changed = False

        for deal in deals:

            deal_id = int(
                getattr(
                    deal,
                    "ticket",
                    0,
                )
            )

            if deal_id <= 0 or deal_id in processed:
                continue

            if int(
                getattr(
                    deal,
                    "magic",
                    0,
                )
            ) != MAGIC_NUMBER:
                continue

            entry_type = int(
                getattr(
                    deal,
                    "entry",
                    -1,
                )
            )

            if entry_type not in (
                mt5.DEAL_ENTRY_OUT,
                mt5.DEAL_ENTRY_OUT_BY,
            ):
                continue

            symbol = str(
                getattr(
                    deal,
                    "symbol",
                    "",
                )
            )

            profit = float(
                getattr(
                    deal,
                    "profit",
                    0.0,
                )
            )

            # Setup isn't always recoverable from MT5
            # after restart, so journal it as UNKNOWN.
            journal_event(
                event="CLOSED",
                symbol=symbol,
                result=profit,
                note=f"deal={deal_id}",
            )

            processed.add(deal_id)
            changed = True

        if changed:

            # Keep state file reasonably small.
            ACCOUNT.processed_deals = list(
                processed
            )[-2000:]

            save_state()

    except Exception as exc:

        log(
            f"Closed deal journal error: {exc}"
        )


# =============================================================================
# DASHBOARD
# =============================================================================

def dashboard():

    account = mt5.account_info()

    if account is None:
        return

    drawdown = current_drawdown_percent()

    open_count = len(
        bot_positions()
    )

    log(
        "================================================================"
    )

    log(
        f"{BOT_NAME} v{BOT_VERSION}"
    )

    log(
        f"Balance: {account.balance:.2f} | "
        f"Equity: {account.equity:.2f}"
    )

    log(
        f"Open: {open_count}/{MAX_OPEN_POSITIONS} | "
        f"Daily: "
        f"{ACCOUNT.daily_trades}/"
        f"{MAX_NEW_TRADES_PER_DAY}"
    )

    log(
        f"Loss streak: "
        f"{ACCOUNT.consecutive_losses}/"
        f"{MAX_CONSECUTIVE_LOSSES}"
    )

    log(
        f"Drawdown: {drawdown:.2f}%/"
        f"{MAX_DRAWDOWN_PERCENT:.2f}%"
    )

    log(
        f"Risk status: "
        f"{'HALTED' if ACCOUNT.halted else 'OK'}"
    )

    if ACCOUNT.halted:
        log(
            f"HALT REASON: "
            f"{ACCOUNT.halt_reason}"
        )

    log(
        "================================================================"
    )


# =============================================================================
# STARTUP
# =============================================================================

def startup():

    global BOT_RUNNING

    log(
        f"Starting {BOT_NAME} v{BOT_VERSION}"
    )

    log(
        f"LIVE_TRADING={LIVE_TRADING} | "
        f"DRY_RUN={DRY_RUN}"
    )

    if LIVE_TRADING and DRY_RUN:

        raise RuntimeError(
            "LIVE_TRADING and DRY_RUN cannot both be True."
        )

    load_state()

    if not initialize_mt5():

        raise RuntimeError(
            "Could not connect to MT5."
        )

    # Select available symbols.
    for symbol in SYMBOLS:

        actual = find_available_symbol(symbol)

        if actual:
            log(
                f"Symbol ready: {actual}"
            )

    update_account_state()

    reconstruct_daily_trade_count()

    update_loss_streak()

    recover_position_states()

    NEWS.refresh()

    dashboard()

    TELEGRAM.send(
        f"🟢 {BOT_NAME} STARTED\n"
        f"Mode: "
        f"{'LIVE' if LIVE_TRADING else 'DEMO/DRY'}\n"
        f"Date: {wat_date()}\n"
        f"Daily trades: "
        f"{ACCOUNT.daily_trades}/"
        f"{MAX_NEW_TRADES_PER_DAY}\n"
        f"Loss streak: "
        f"{ACCOUNT.consecutive_losses}/"
        f"{MAX_CONSECUTIVE_LOSSES}"
    )


# =============================================================================
# MAIN LOOP
# =============================================================================

def run_bot():

    global BOT_RUNNING
    global LAST_STATUS_TIME

    startup()

    last_loss_update = 0.0
    last_daily_reconstruction = 0.0

    try:

        while BOT_RUNNING:

            # ---------------------------------------------------------
            # CONNECTION
            # ---------------------------------------------------------

            if mt5.terminal_info() is None:

                log(
                    "MT5 connection lost. Reconnecting..."
                )

                if not reconnect_mt5():

                    time.sleep(10)
                    continue

            # ---------------------------------------------------------
            # ACCOUNT / DAY
            # ---------------------------------------------------------

            update_account_state()

            now = time.time()

            if (
                now - last_daily_reconstruction
                >= 60
            ):

                reconstruct_daily_trade_count()

                last_daily_reconstruction = now

            # ---------------------------------------------------------
            # NEWS
            # ---------------------------------------------------------

            NEWS.refresh()

            # ---------------------------------------------------------
            # LOSS TRACKER
            # ---------------------------------------------------------

            if (
                now - last_loss_update
                >= 30
            ):

                update_loss_streak()
                journal_new_closed_deals()

                last_loss_update = now

            # ---------------------------------------------------------
            # RISK
            # ---------------------------------------------------------

            allowed, reason = risk_gate()

            if not allowed:

                log(
                    f"TRADING BLOCKED: {reason}"
                )

            # ---------------------------------------------------------
            # MANAGE EXISTING POSITIONS
            # ---------------------------------------------------------

            try:

                manage_positions()

            except Exception as exc:

                log(
                    f"Position manager error: {exc}"
                )

            # ---------------------------------------------------------
            # NEW ENTRIES
            # ---------------------------------------------------------

            if allowed:

                try:

                    scan_market()

                except Exception as exc:

                    log(
                        f"Market scanner error: {exc}"
                    )

            # ---------------------------------------------------------
            # STATUS
            # ---------------------------------------------------------

            if (
                time.time() - LAST_STATUS_TIME
                >= STATUS_SECONDS
            ):

                dashboard()

                TELEGRAM.send(
                    f"📊 {BOT_NAME}\n"
                    f"Balance/Equity: "
                    f"{mt5.account_info().balance:.2f}/"
                    f"{mt5.account_info().equity:.2f}\n"
                    f"Open: "
                    f"{len(bot_positions())}/"
                    f"{MAX_OPEN_POSITIONS}\n"
                    f"Daily trades: "
                    f"{ACCOUNT.daily_trades}/"
                    f"{MAX_NEW_TRADES_PER_DAY}\n"
                    f"Loss streak: "
                    f"{ACCOUNT.consecutive_losses}/"
                    f"{MAX_CONSECUTIVE_LOSSES}\n"
                    f"DD: "
                    f"{current_drawdown_percent():.2f}%"
                )

                LAST_STATUS_TIME = time.time()

            # ---------------------------------------------------------
            # SAVE
            # ---------------------------------------------------------

            save_state()

            time.sleep(
                SCAN_SECONDS
            )

    except KeyboardInterrupt:

        log(
            "Keyboard interrupt received."
        )

    except Exception as exc:

        log(
            f"FATAL BOT ERROR: {exc}"
        )

        traceback.print_exc()

        TELEGRAM.send(
            f"🔴 {BOT_NAME} stopped بسبب error:\n"
            f"{exc}"
        )

    finally:

        save_state()

        TELEGRAM.send(
            f"🔴 {BOT_NAME} STOPPED"
        )

        shutdown_mt5()


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":

    run_bot()