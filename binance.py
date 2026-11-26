from concurrent.futures import ThreadPoolExecutor
from itertools import permutations
import json
import time
from urllib.parse import urlencode
from urllib.request import urlopen

from .engine import Book, D, Market, Route, Unfillable, estimate

API = 'https://data-api.binance.vision/api/v3/'
ASSETS = ('BTC', 'ETH', 'BNB', 'SOL')

def fetch(endpoint, **query):
    with urlopen(API + endpoint + '?' + urlencode(query), timeout=7) as response:
        return json.load(response)

def markets():
    pairs = [(a, b) for a in ASSETS for b in (*ASSETS, 'USDT') if a != b]
    data = fetch('exchangeInfo', symbolStatus='TRADING', permissions='SPOT')
    by_symbol = {}
    allowed = {a + b for a, b in pairs}
    for row in data['symbols']:
        if row['symbol'] not in allowed or not row['isSpotTradingAllowed']:
            continue
        filters = {f['filterType']: f for f in row['filters']}
        lot = filters['LOT_SIZE']
        minimum, maximum = D(0), D('Infinity')
        if 'MIN_NOTIONAL' in filters:
            minimum = D(filters['MIN_NOTIONAL']['minNotional'])
        if 'NOTIONAL' in filters:
            minimum = max(minimum, D(filters['NOTIONAL']['minNotional']))
            maximum = D(filters['NOTIONAL']['maxNotional'])
        market = Market(row['symbol'], row['baseAsset'], row['quoteAsset'],
                        D(lot['stepSize']), D(lot['minQty']), D(lot['maxQty']),
                        minimum, maximum)
        by_symbol[frozenset((market.base, market.quote))] = market
    return by_symbol

def depth(market):
    data = fetch('depth', symbol=market.symbol, limit=100)
    received = time.monotonic()
    sides = [tuple((D(price), D(size)) for price, size in data[name])
             for name in ('bids', 'asks')]
    if any(not levels or any(price <= 0 or size <= 0 for price, size in levels)
           for levels in sides) or sides[0][0][0] >= sides[1][0][0]:
        raise ValueError('Invalid order book')
    return Book(*sides, received)

def scan(by_pair, amount, fee):
    routes = []
    for a, b in permutations(ASSETS, 2):
        assets = ('USDT', a, b, 'USDT')
        keys = [frozenset(pair) for pair in zip(assets, assets[1:])]
        if all(key in by_pair for key in keys):
            routes.append(Route(assets, tuple(by_pair[key] for key in keys)))
    if not routes:
        raise ValueError('No eligible spot markets')
    used = {m.symbol: m for route in routes for m in route.markets}
    with ThreadPoolExecutor(max_workers=5) as executor:
        books = dict(zip(used, executor.map(depth, used.values())))
    clock = time.monotonic()
    results = []
    for route in routes:
        try:
            results.append(estimate(route, books, amount, fee, clock))
        except Unfillable:
            continue
    return results, len(routes)
