from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN

D = Decimal

class Unfillable(ValueError):
    pass

@dataclass(frozen=True)
class Market:
    symbol: str
    base: str
    quote: str
    step: Decimal
    minimum: Decimal
    maximum: Decimal
    min_notional: Decimal
    max_notional: Decimal

@dataclass(frozen=True)
class Book:
    bids: tuple
    asks: tuple
    received: float

@dataclass(frozen=True)
class Fill:
    output: Decimal
    fee: Decimal
    quantity: Decimal
    notional: Decimal

def fill(market, book, source, amount, fee):
    buying = source == market.quote
    if not buying and source != market.base:
        raise ValueError('asset')
    levels = book.asks if buying else book.bids
    left = amount
    quantity = D(0)
    for price, size in levels:
        taken = min(size, left / price if buying else left)
        quantity += taken
        capacity = size * price if buying else size
        if capacity >= left:
            left = D(0)
            break
        left -= capacity
    if left > 0:
        raise Unfillable('depth')
    quantity = (quantity / market.step).to_integral_value(rounding=ROUND_DOWN) * market.step
    if quantity <= 0 or not market.minimum <= quantity <= market.maximum:
        raise Unfillable('quantity')
    remaining = quantity
    notional = D(0)
    for price, size in levels:
        taken = min(size, remaining)
        notional += taken * price
        remaining -= taken
        if not remaining:
            break
    if not market.min_notional <= notional <= market.max_notional:
        raise Unfillable('notional')
    received = quantity if buying else notional
    return Fill(received * (1 - fee), received * fee, quantity, notional)

@dataclass(frozen=True)
class Route:
    assets: tuple
    markets: tuple

    @property
    def key(self):
        return '/'.join(self.assets)

@dataclass(frozen=True)
class Estimate:
    route: Route
    gross: Decimal
    net: Decimal | None
    fills: tuple

def estimate(route, books, amount, fee, clock, max_age=15, max_skew=8):
    if not amount.is_finite() or amount <= 0 or (
        fee is not None and (not fee.is_finite() or not 0 <= fee < 1)
    ):
        raise ValueError('amount or fee')
    timestamps = [books[m.symbol].received for m in route.markets]
    if clock - min(timestamps) > max_age or max(timestamps) - min(timestamps) > max_skew:
        raise Unfillable('stale or unsynchronized snapshots')

    def simulate(rate):
        balance = amount
        fills = []
        for asset, market in zip(route.assets, route.markets):
            trade = fill(market, books[market.symbol], asset, balance, rate)
            fills.append(trade)
            balance = trade.output
        first = fills[0]
        spent = first.notional if route.assets[0] == route.markets[0].quote else first.quantity
        return balance + amount - spent, tuple(fills)

    gross, fills = simulate(D(0))
    if fee is None:
        return Estimate(route, gross, None, fills)
    net, fills = simulate(fee)
    return Estimate(route, gross, net, fills)

def profit(start, end):
    return end - start, (end - start) / start * 100
