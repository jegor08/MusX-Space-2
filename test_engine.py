from decimal import Decimal as D
import unittest

from musx.engine import Book, Market, Route, Unfillable, estimate, fill, profit


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.market = Market('XUSDT', 'X', 'USDT', D('.1'), D('.1'), D('1000'), D('5'), D('10000'))
        self.book = Book(((D(9), D(100)),), ((D(10), D(5)), (D(12), D(100))), 50)

    def test_depth_and_quantity_rounding(self):
        result = fill(self.market, self.book, 'USDT', D(100), D('.01'))
        self.assertEqual(result.quantity, D('9.1'))
        self.assertEqual(result.notional, D('99.2'))
        self.assertEqual(result.fee, D('.091'))
        self.assertEqual(result.output, D('9.009'))

    def test_sale_fee_in_quote_asset(self):
        self.assertEqual(fill(self.market, self.book, 'X', D('10.09'), D('.01')).fee, D('.9'))

    def test_insufficient_depth(self):
        with self.assertRaisesRegex(Unfillable, 'depth'):
            fill(self.market, self.book, 'X', D(101), D(0))

    def test_minimum_notional(self):
        with self.assertRaisesRegex(Unfillable, 'notional'):
            fill(self.market, self.book, 'USDT', D(4), D(0))

    def test_stale_book(self):
        route = Route(('USDT', 'X', 'USDT'), (self.market, self.market))
        with self.assertRaisesRegex(Unfillable, 'stale'):
            estimate(route, {'XUSDT': self.book}, D(100), None, 70)

    def test_unknown_commission_and_negative_profit(self):
        route = Route(('USDT', 'X', 'USDT'), (self.market, self.market))
        result = estimate(route, {'XUSDT': self.book}, D(100), None, 51)
        self.assertIsNone(result.net)
        self.assertLess(profit(D(100), result.gross)[0], 0)

    def test_net_profit_reference(self):
        self.assertEqual(profit(D(1000), D(1007)), (D(7), D('.7')))
