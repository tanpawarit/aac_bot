# !pip install discordwebhook
# !pip install MetaTrader5

import MetaTrader5 as mt
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import time
import pytz
from discordwebhook import Discord


# display data on the MetaTrader 5 package
print("MetaTrader5 package author: ", mt.__author__)
print("MetaTrader5 package version: ", mt.__version__)
print("Session Breakout Strategy: 1.0.0")

# ===================== init setting ========================
username = 55632504
password = "A1s2d3f4/"
server = "Tickmill-Live"
symbol = "GBPJPY"
lot = 0.01  # 500$ lot 0.05
discord = Discord(
    url="https://discord.com/api/webhooks/1209860197816729621/l3Urs2-z0Bqtic7lpVJK4JmwkpCzUIpFlaJb_zIM1vF_SUQW9TPHJCMPQ1ycPEpiHCNH"
)


def start_mt5(username, password, server):
    # Ensure that all variables are the correct type
    uname = int(username)  # Username must be an int
    pword = str(password)  # Password must be a string
    trading_server = str(server)  # Server must be a string

    # Attempt to start MT5
    if mt.initialize(login=uname, password=pword, server=trading_server):
        print("Trading Bot Starting")
        # Login to MT5
        if mt.login(login=uname, password=pword, server=trading_server):
            current_accout_info = mt.account_info()
            print("----------------------------------------")
            print(
                f"Login: {current_accout_info.login} \t server: {current_accout_info.server}"
            )
            print(f"Run time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")
            print("Trading Bot Logged in and Ready to Go!")
            return True
        else:
            print("initialize() failed, error code =", mt.last_error())
            quit()
            return PermissionError
    else:
        print("MT5 Initialization Failed")
        quit()
        return ConnectionAbortedError


# =============================================


def discord_template(side, current_time, price, sl):
    return discord.post(
        embeds=[
            {
                "author": {
                    "name": "Session Breakout",
                },
                "description": f"Open {side} GBPJPY at : {current_time} UTC",
                "fields": [
                    {"name": "Price", "value": f"{price}", "inline": False},
                    {"name": "Stop loss", "value": f"{sl}", "inline": True},
                    {"name": "Take Profit", "value": f"-", "inline": True},
                ],
                "footer": {
                    "text": "=========================",
                },
            }
        ],
    )


def get_data(symbol="GBPJPY", interval=mt.TIMEFRAME_M15, no_of_rows=500):

    rate = mt.copy_rates_from_pos(symbol, interval, 0, no_of_rows)
    columns = [
        "time",
        "open",
        "high",
        "low",
        "close",
        "tick_volume",
        "spread",
        "real_volume",
    ]
    df = pd.DataFrame(rate, columns=columns)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    # df['time'] = df['time'] - timedelta(hours=2) # Change to tradingview time (UTC)

    return df


def get_session(hour):
    if 0 <= hour < 8:
        return "asian session"
    else:
        None


def get_signal():

    df = get_data()
    df["hour"] = df["time"].dt.hour
    df["session"] = df["hour"].apply(get_session)
    df["date"] = df["time"].dt.date

    df_by_date = df.groupby(["date", "session"], as_index=False).agg(
        session_high=("high", "max"), session_low=("low", "min")
    )

    df = df.merge(
        df_by_date[["date", "session_high", "session_low"]], on=["date"], how="left"
    )

    df["stoploss"] = df["session_high"] - (df["session_high"] - df["session_low"]) / 2

    open_cond1 = (df["hour"] >= 8) & (12 > df["hour"])

    long_cond1 = df["open"] > df["session_high"]

    short_cond1 = df["open"] < df["session_low"]

    close_cond1 = df["hour"] >= 17

    df["order_type"] = np.nan
    df["order_type"] = np.where(open_cond1 & long_cond1, "long", df["order_type"])
    df["order_type"] = np.where(open_cond1 & short_cond1, "short", df["order_type"])
    df["order_type"] = np.where(close_cond1, "close", df["order_type"])

    return df


def create_position(symbol, lot, stoploss, order_type):

    if order_type == "long":
        side = mt.ORDER_TYPE_BUY
        last_price = mt.symbol_info_tick(symbol).ask
        comment = "long"

    elif order_type == "short":
        side = mt.ORDER_TYPE_SELL
        last_price = mt.symbol_info_tick(symbol).bid
        comment = "short"

    request = {
        "action": mt.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": side,
        "price": last_price,
        "sl": stoploss,
        "tp": 0.0,
        "deviation": 20,
        "magic": 234000,
        "comment": comment,
        "type_time": mt.ORDER_TIME_GTC,
        "type_filling": mt.ORDER_FILLING_IOC,
    }
    ordered = mt.order_send(request)

    if ordered.retcode != mt.TRADE_RETCODE_DONE:
        print(
            f"Order execution failed with error code {ordered.retcode}: {ordered.comment}"
        )

    return ordered


def close_position(deal_id):
    open_positions = positions_get()
    open_positions = open_positions[open_positions["ticket"] == deal_id]
    order_type = open_positions["type"][0]
    symbol = open_positions["symbol"][0]
    volume = open_positions["volume"][0]

    if order_type == mt.ORDER_TYPE_BUY:
        order_type = mt.ORDER_TYPE_SELL
        price = mt.symbol_info_tick(symbol).bid
    else:
        order_type = mt.ORDER_TYPE_BUY
        price = mt.symbol_info_tick(symbol).ask

    close_request = {
        "action": mt.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(volume),
        "type": order_type,
        "position": deal_id,
        "price": price,
        "deviation": 20,
        "magic": 234000,
        "comment": "Close trade",
        "type_time": mt.ORDER_TIME_GTC,
        "type_filling": mt.ORDER_FILLING_IOC,
    }

    result = mt.order_send(close_request)

    if result.retcode != mt.TRADE_RETCODE_DONE:
        print("Failed to close order :(")
    else:
        print("Order successfully closed!")


def positions_get(symbol=None):
    if symbol is None:
        res = mt.positions_get()
    else:
        res = mt.positions_get(symbol=symbol)

    if res is not None and res != ():
        df = pd.DataFrame(list(res), columns=res[0]._asdict().keys())
        df["time"] = pd.to_datetime(df["time"], unit="s")
        return df

    return pd.DataFrame()


def make_order(df, symbol, lot):

    current_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    side = df.iloc[-1]["order_type"]
    price = round(df.iloc[-1]["close"], 3)
    sl = round(df.iloc[-1]["stoploss"], 3)

    holding_position = mt.positions_get()
    num_position = len(mt.positions_get())

    if num_position == 0:

        if side == "long":
            ordered = create_position(symbol, lot, stoploss=sl, order_type="long")
            discord_template(side, current_time, price, sl)

        elif side == "short":
            ordered = create_position(symbol, lot, stoploss=sl, order_type="short")
            discord_template(side, current_time, price, sl)
        else:
            pass

    elif (num_position != 0) and (side == "close"):

        latest_pos_side = positions_get(symbol=None)["type"][0]
        latest_pos_id = positions_get(symbol=None)["ticket"][0]

        close_position(latest_pos_id)
        discord.post(
            content=f"Close GBPJPY at : {current_time}, \t Balance: {mt.account_info().balance} USD, \t Equity: {mt.account_info().equity} USD, \t Profit: {mt.account_info().profit}"
        )

    else:
        pass


def main():
    start_mt5(username, password, server)
    try:
        while True:

            current_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")  # (UTC)
            count_minute = 60 - time.time() % 60
            time.sleep(count_minute)

            df = get_signal()
            make_order(df, symbol, lot)

            time.sleep(1)

    except Exception as error:
        print(error)
        print("=============================================")


main()
