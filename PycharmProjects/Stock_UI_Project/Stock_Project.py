
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
import traceback

# Third-party imports; listed in requirements.txt
import yfinance as yf
import pandas as pd
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# Map friendly names to symbols
SYMBOLS = {"Tesla": "TSLA", "Google": "GOOGL"}


def fetch_history(symbol: str, period: str = "90d") -> pd.DataFrame:
    
    ticker = yf.Ticker(symbol)
    #print(ticker)
    hist = ticker.history(period=period, auto_adjust=False) #contains Open, High, Low, Close, Volume data
    #print(hist) #OHLCV data
    return hist


def fetch_quote(symbol: str) -> dict:
    """Fetch a small set of quote info for display.

    Returns a dict: {price, prev_close, change, change_pct, volume, currency}
    """
    ticker = yf.Ticker(symbol)
    info = {}
    try:
        # Use info fields when available
        raw = ticker.info
        #print(raw)
        info['price'] = raw.get('regularMarketPrice')
        info['prev_close'] = raw.get('regularMarketPreviousClose')
        info['volume'] = raw.get('volume')
        info['currency'] = raw.get('currency', '')
    except Exception:
        # info may fail for some tickers or rate limits; fall back to history
        raw = {}

    hist = fetch_history(symbol, period='5d')
    if hist is None or hist.empty:
        raise RuntimeError(f"No data available for {symbol}")

    # Fill any missing values using history
    last_close = float(hist['Close'].iloc[-1])
    #print(last_close)
    prev_close_hist = float(hist['Close'].iloc[-2]) if len(hist) > 1 else last_close
    #print(prev_close_hist)
    price = info.get('price', last_close)
    prev_close = info.get('prev_close', prev_close_hist)
    volume = info.get('volume', int(hist['Volume'].iloc[-1]) if 'Volume' in hist.columns else None)
    currency = info.get('currency', '')

    change = (price - prev_close) if (price is not None and prev_close is not None) else 0.0
    change_pct = (change / prev_close * 100.0) if (prev_close not in (0, None)) else 0.0

    return {
        'price': price,
        'prev_close': prev_close,
        'change': change,
        'change_pct': change_pct,
        'volume': volume,
        'currency': currency,
    }


class StockApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title('Stock Viewer — Tesla & Google')
        self.root.geometry('900x640')

        # State
        self.selected_name = tk.StringVar(value='Tesla')
        self.auto_refresh = tk.BooleanVar(value=False)
        self.refresh_interval = 60  # seconds when auto-refresh enabled

        # Top controls
        top = ttk.Frame(root)
        top.pack(side='top', fill='x', padx=8, pady=8)

        ttk.Label(top, text='Select:').pack(side='left')
        self.combo = ttk.Combobox(top, values=list(SYMBOLS.keys()), textvariable=self.selected_name, state='readonly', width=12)
        self.combo.pack(side='left', padx=(6, 6))

        self.refresh_btn = ttk.Button(top, text='Refresh', command=self.start_fetch_thread)
        self.refresh_btn.pack(side='left')

        ttk.Checkbutton(top, text='Auto refresh', variable=self.auto_refresh, command=self._on_toggle_auto).pack(side='left', padx=(8, 6))

        self.status_lbl = ttk.Label(top, text='Ready')
        self.status_lbl.pack(side='right')

        # Info frame
        info_frame = ttk.Frame(root)
        info_frame.pack(side='top', fill='x', padx=8, pady=(0, 6))

        self.price_lbl = ttk.Label(info_frame, text='Price: —', font=('Segoe UI', 16, 'bold'))
        self.price_lbl.grid(row=0, column=0, sticky='w', padx=4, pady=4)

        self.change_lbl = ttk.Label(info_frame, text='Change: —', font=('Segoe UI', 12))
        self.change_lbl.grid(row=0, column=1, sticky='w', padx=4)

        self.volume_lbl = ttk.Label(info_frame, text='Volume: —', font=('Segoe UI', 12))
        self.volume_lbl.grid(row=0, column=2, sticky='w', padx=4)

        self.updated_lbl = ttk.Label(info_frame, text='Last update: —', font=('Segoe UI', 10))
        self.updated_lbl.grid(row=1, column=0, columnspan=3, sticky='w', padx=4)

        # Chart area
        self.fig = Figure(figsize=(9, 4.5), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_title('Price History')
        self.ax.set_xlabel('Date')
        self.ax.set_ylabel('Close')

        self.canvas = FigureCanvasTkAgg(self.fig, master=root)
        self.canvas.get_tk_widget().pack(side='top', fill='both', expand=True, padx=8, pady=6)

        # Initial fetch
        self.start_fetch_thread()

    def _on_toggle_auto(self):
        if self.auto_refresh.get():
            # start auto-refreshing
            #boolean variable changed to True
            self._schedule_auto_refresh()

    def _schedule_auto_refresh(self):
        if self.auto_refresh.get():
            # schedule next
            self.root.after(self.refresh_interval * 1000, self._auto_refresh_callback)


#periodic update every refresh_interval seconds
    #if auto_refresh is enabled, start a timer to fetch data again
    #if not enabled, do nothing
    def _auto_refresh_callback(self):
        if not self.auto_refresh.get():
            return
        self.start_fetch_thread()
        # schedule again
        self._schedule_auto_refresh()

    def start_fetch_thread(self):
        # disable controls while fetching
        #_fetch_and_update runs in a separate thread (from start_fetch_thread) to avoid freezing the GUI.
        self.refresh_btn.config(state='disabled')
        self.combo.config(state='disabled')
        thread = threading.Thread(target=self._fetch_and_update, daemon=True)#thread stops when app closes
        thread.start()

    def _fetch_and_update(self):
        name = self.selected_name.get()
        symbol = SYMBOLS.get(name, name)
        try:
            self._set_status(f'Fetching {symbol} ...')
            quote = fetch_quote(symbol)
            hist = fetch_history(symbol, period='180d')
            # schedule UI update on main thread
            self.root.after(0, lambda: self._update_ui(name, symbol, quote, hist))
        except Exception as ex:#any exception during fetch
            tb = traceback.format_exc()
            print(tb)
            self.root.after(0, lambda: messagebox.showerror('Fetch error', f'Failed to fetch data for {symbol}:\n{ex}'))
            self.root.after(0, self._enable_controls)

#_fetch_and_update runs in a separate thread (from start_fetch_thread) to avoid freezing the GUI.


    def _update_ui(self, name: str, symbol: str, quote: dict, hist: pd.DataFrame):
        price = quote.get('price')
        change = quote.get('change')
        change_pct = quote.get('change_pct')
        volume = quote.get('volume')
        currency = quote.get('currency', '')

        if price is None:
            price_text = 'N/A'
        else:
            price_text = f"{price:,.2f} {currency}" if currency else f"{price:,.2f}"

        self.price_lbl.config(text=f"{name} ({symbol}) — {price_text}")

        if change is None:
            ch_text = 'N/A'
            self.change_lbl.config(text=f'Change: {ch_text}', foreground='black')
        else:
            ch_text = f"{change:+,.2f} ({change_pct:+.2f}%)"
            self.change_lbl.config(text=f'Change: {ch_text}', foreground=('green' if change >= 0 else 'red'))

        vol_text = f"{volume:,}" if volume is not None else 'N/A'
        self.volume_lbl.config(text=f'Volume: {vol_text}')

        self.updated_lbl.config(text=f'Last update: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')

        # Update chart
        try:
            self.ax.clear()
            if hist is not None and not hist.empty and 'Close' in hist.columns:#check if 'Close' column exists
                # hist DataFrame is not empty
                #hist.empty hast atleast one row
                data = hist['Close'].dropna()#drop NaN values(removes unexpected index types )
                self.ax.plot(data.index, data.values, color='#1f77b4', linewidth=1.3)
                self.ax.fill_between(data.index, data.values, alpha=0.12, color='#1f77b4')
                self.ax.set_title(f'{name} ({symbol}) — Last {len(data)} points')
                self.ax.set_xlabel('Date')
                self.ax.set_ylabel('Close')
                self.ax.grid(alpha=0.3)
                self.fig.autofmt_xdate()
            else:
                self.ax.text(0.5, 0.5, 'No historical data', ha='center', va='center')
        except Exception:
            # keep UI resilient
            self.ax.clear()
            self.ax.text(0.5, 0.5, 'Chart error', ha='center', va='center')

        self.canvas.draw()#updated figure into the GUI. Without this call, user won’t see the new plot.
        self._enable_controls()#Enables the Refresh button and the combobox
        self._set_status('Ready')

    def _enable_controls(self):
        self.refresh_btn.config(state='normal')
        self.combo.config(state='readonly')

    def _set_status(self, text: str):
        self.status_lbl.config(text=text)


def main():
    root = tk.Tk()
    app = StockApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
