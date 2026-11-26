from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import InvalidOperation
import time
import tkinter as tk
from tkinter import ttk
from urllib.error import HTTPError, URLError

from musx.binance import markets, scan
from musx.engine import D, profit


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('MusX Space 2.0')
        self.geometry('1080x580')
        self.minsize(820, 480)
        self.configure(bg='#101418')
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.future = None
        self.running = False
        self.generation = 0
        self.active = {}
        self.settings = None
        self.protocol('WM_DELETE_WINDOW', self.close)
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', background='#182027', foreground='#edf2f6', fieldbackground='#222d36')
        style.configure('Treeview', rowheight=32)
        style.configure('Accent.TButton', foreground='#142019', background='#55ee91')
        style.map('Accent.TButton', background=[('active', '#7dffa8')])

        header = ttk.Frame(self, padding=16)
        header.pack(fill='x')
        ttk.Label(header, text='MusX Space 2.0', font=('Segoe UI', 22, 'bold')).pack(side='left')
        self.status = tk.StringVar(value='Ожидание запуска')
        ttk.Label(header, textvariable=self.status).pack(side='right')
        body = ttk.Frame(self, padding=16)
        body.pack(fill='both', expand=True)
        controls = ttk.Frame(body, padding=(0, 0, 16, 0))
        controls.pack(side='left', fill='y')
        ttk.Label(controls, text='Базовая биржа', font=('Segoe UI', 12, 'bold')).pack(anchor='w')
        ttk.Label(controls, text='Binance Spot • 3 операции').pack(anchor='w', pady=(0, 18))
        self.amount = self.field(controls, 'Сумма в USDT', '100')
        self.threshold = self.field(controls, 'Мин. доходность, %', '0.30')
        self.fee = self.field(controls, 'Комиссия за шаг, %', '')
        ttk.Label(controls, text='Пустое поле — валовой расчёт', wraplength=190).pack(anchor='w')
        self.button = ttk.Button(controls, text='Scan Now', style='Accent.TButton', command=self.toggle)
        self.button.pack(fill='x', pady=18)
        self.summary = tk.StringVar(value='Введите параметры и запустите сканирование.')
        content = ttk.Frame(body)
        content.pack(side='left', fill='both', expand=True)
        ttk.Label(content, textvariable=self.summary, wraplength=610).pack(anchor='w', pady=(0, 12))
        columns = ('route', 'gross', 'net', 'total', 'elapsed')
        self.table = ttk.Treeview(content, columns=columns, show='headings')
        for col, label, width in zip(columns, ('Маршрут', 'Вал. %', 'Чист. %*', 'Итог USDT', 'Время'), (240, 70, 75, 95, 85)):
            self.table.heading(col, text=label)
            self.table.column(col, width=width, minwidth=55, stretch=col == 'route')
        self.table.pack(fill='both', expand=True)
        ttk.Label(content, text='* По введённой комиссии. Оценка по снимкам стаканов, ручное исполнение.',
                  wraplength=610).pack(anchor='w', pady=(12, 0))
        self.after(200, self.poll)

    def field(self, parent, label, initial):
        ttk.Label(parent, text=label).pack(anchor='w')
        value = tk.StringVar(value=initial)
        ttk.Entry(parent, textvariable=value, width=23).pack(fill='x', pady=(3, 10))
        return value

    def read_settings(self):
        amount = D(self.amount.get().strip().replace(',', '.'))
        threshold = D(self.threshold.get().strip().replace(',', '.'))
        raw_fee = self.fee.get().strip().replace(',', '.')
        fee = D(raw_fee) / 100 if raw_fee else None
        if not amount.is_finite() or amount <= 0 or not threshold.is_finite():
            raise ValueError
        if fee is not None and (not fee.is_finite() or not 0 <= fee < 1):
            raise ValueError
        return amount, threshold, fee

    def clear(self):
        self.active.clear()
        self.table.delete(*self.table.get_children())

    def toggle(self):
        self.generation += 1
        self.running = not self.running
        self.clear()
        self.button.configure(text='Остановить' if self.running else 'Scan Now')
        self.status.set('Подключение…' if self.running else 'Остановлено')
        self.next_run = 0
        self.market_data = None

    def load_scan(self, existing, amount, fee):
        data = existing or markets()
        return data, scan(data, amount, fee)

    def poll(self):
        if self.running:
            try:
                settings = self.read_settings()
            except (InvalidOperation, ValueError):
                settings = None
            if settings != self.settings:
                self.settings = settings
                self.generation += 1
                self.clear()
                self.next_run = 0
            if settings is None:
                self.status.set('Проверьте сумму, порог и комиссию')
        if self.future is not None and self.future.done():
            future, self.future = self.future, None
            if self.running and self.request_generation == self.generation:
                self.consume(future)
        now = time.monotonic()
        if self.running and self.settings is not None and self.future is None and now >= self.next_run:
            amount, _, fee = self.settings
            self.request_generation = self.generation
            self.future = self.pool.submit(self.load_scan, self.market_data, amount, fee)
        for key, started in self.active.items():
            self.table.set(key, 'elapsed', f'{int(now - started)} с')
        self.after(200, self.poll)

    def consume(self, future):
        now = time.monotonic()
        self.next_run = now + 10
        try:
            self.market_data, (results, candidates) = future.result()
        except HTTPError as error:
            self.clear()
            self.status.set(f'Данные недоступны · HTTP {error.code}')
            self.summary.set('Состояние маршрутов неизвестно.')
            retry = error.headers.get('Retry-After', '')
            delay = int(retry) if retry.isdecimal() else 0
            self.next_run = now + max(delay, 120 if error.code in (418, 429) else 30)
            return
        except (URLError, OSError, ValueError, KeyError, ArithmeticError):
            self.clear()
            self.status.set('Данные недоступны')
            self.summary.set('Состояние маршрутов неизвестно. Повтор через 30 с.')
            self.next_run = now + 30
            return
        amount, threshold, fee = self.settings
        visible = {}
        for item in results:
            total = item.gross if fee is None else item.net
            _, rate = profit(amount, total)
            if rate >= threshold:
                visible[item.route.key] = (item, total, rate)
        previous = self.active.copy()
        self.clear()
        self.status.set('Binance Spot · Online')
        self.summary.set(
            f'Связок: {len(visible)} · Проверено: {candidates} · '
            f'Рассчитано: {len(results)} · Обновлено: {datetime.now():%H:%M:%S}'
        )
        for key, (result, total, rate) in sorted(visible.items(), key=lambda row: row[1][2], reverse=True):
            self.active[key] = previous.get(key, now)
            gross = profit(amount, result.gross)[1]
            net = '—' if result.net is None else f'{rate:+.4f}%'
            self.table.insert('', 'end', iid=key, values=(
                ' → '.join(result.route.assets), f'{gross:+.4f}%', net, f'{total:.4f}', '0 с'
            ))

    def close(self):
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.destroy()


if __name__ == '__main__':
    app = App()
    import sys
    if '--smoke-test' in sys.argv:
        app.after(100, app.close)
    app.mainloop()
