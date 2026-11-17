"""Public read-only chart endpoint behavior and failure handling."""
import unittest
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
from app import postgres_api as api

class MarketChartTests(unittest.IsolatedAsyncioTestCase):
    async def test_active_forex_catalog_is_public(self):
        catalog = {
            'markets': [{'symbol': 'frxAUDHUF', 'pair': 'AUDHUF'}],
            'source': 'DERIV_PUBLIC',
            'execution': 'DISABLED',
        }
        with patch.object(api, 'owner') as owner, \
             patch.object(api.deriv_market_data, 'fetch_public_forex_markets', new=AsyncMock(return_value=catalog)):
            result = await api.market_forex()
        self.assertEqual(result, catalog)
        owner.assert_not_called()

    async def test_candles_are_public_without_owner_or_deriv_session(self):
        history={'candles':[], 'source':'DERIV_PUBLIC', 'execution':'DISABLED'}
        with patch.object(api, 'owner') as owner, \
             patch.object(api.deriv_market_data, 'fetch_public_candles', new=AsyncMock(return_value=history)) as fetch:
            result = await api.market_candles(pair='EURUSD')
        self.assertEqual(result, history)
        owner.assert_not_called()
        fetch.assert_awaited_once_with('frxEURUSD', count=80, granularity=300)

    async def test_invalid_symbol_rejected_before_feed(self):
        with patch.object(api.deriv_market_data, 'fetch_public_candles', new_callable=AsyncMock) as fetch:
            with self.assertRaises(HTTPException) as caught:
                await api.market_candles(pair='INVALID')
            self.assertEqual(caught.exception.status_code, 400)
            fetch.assert_not_awaited()

    async def test_feed_unavailable_is_503(self):
        with patch.object(api.deriv_market_data, 'fetch_public_candles', new=AsyncMock(side_effect=api.deriv_market_data.DerivMarketDataError('Feed unavailable'))):
            with self.assertRaises(HTTPException) as caught:
                await api.market_candles()
            self.assertEqual(caught.exception.status_code, 503)

    async def test_read_only_history_returned(self):
        history={'candles':[], 'source':'DERIV_PUBLIC', 'execution':'DISABLED'}
        with patch.object(api.deriv_market_data, 'fetch_public_candles', new=AsyncMock(return_value=history)) as fetch:
            self.assertEqual(await api.market_candles(pair='GBPUSD', granularity=60, count=80), history)
            fetch.assert_awaited_once_with('frxGBPUSD', count=80, granularity=60)

    async def test_any_validated_forex_pair_can_load_history(self):
        history={'candles':[], 'source':'DERIV_PUBLIC', 'execution':'DISABLED'}
        with patch.object(api.deriv_market_data, 'fetch_public_candles', new=AsyncMock(return_value=history)) as fetch:
            await api.market_candles(pair='AUDHUF')
        fetch.assert_awaited_once_with('frxAUDHUF', count=80, granularity=300)
