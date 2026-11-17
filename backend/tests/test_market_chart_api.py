"""Read-only chart endpoint authorization and failure handling."""
import unittest
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
from app import postgres_api as api

class MarketChartTests(unittest.IsolatedAsyncioTestCase):
    async def test_auth_required(self):
        with patch.object(api, 'owner', side_effect=HTTPException(401, 'Unauthorized')), patch.object(api.deriv_market_data, 'fetch_public_candles', new_callable=AsyncMock) as fetch:
            with self.assertRaises(HTTPException) as caught:
                await api.market_candles(authorization='')
            self.assertEqual(caught.exception.status_code, 401)
            fetch.assert_not_awaited()

    async def test_invalid_symbol_rejected_before_feed(self):
        with patch.object(api, 'owner'), patch.object(api.deriv_market_data, 'fetch_public_candles', new_callable=AsyncMock) as fetch:
            with self.assertRaises(HTTPException) as caught:
                await api.market_candles(pair='INVALID', authorization='Bearer test')
            self.assertEqual(caught.exception.status_code, 400)
            fetch.assert_not_awaited()

    async def test_feed_unavailable_is_503(self):
        with patch.object(api, 'owner'), patch.object(api.deriv_market_data, 'fetch_public_candles', new=AsyncMock(side_effect=api.deriv_market_data.DerivMarketDataError('Feed unavailable'))):
            with self.assertRaises(HTTPException) as caught:
                await api.market_candles(authorization='Bearer test')
            self.assertEqual(caught.exception.status_code, 503)

    async def test_read_only_history_returned(self):
        history={'candles':[], 'source':'DERIV_PUBLIC', 'execution':'DISABLED'}
        with patch.object(api, 'owner'), patch.object(api.deriv_market_data, 'fetch_public_candles', new=AsyncMock(return_value=history)) as fetch:
            self.assertEqual(await api.market_candles(pair='GBPUSD', granularity=60, count=80, authorization='Bearer test'), history)
            fetch.assert_awaited_once_with('frxGBPUSD', count=80, granularity=60)
