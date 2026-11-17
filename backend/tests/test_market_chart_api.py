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

    async def test_deriv_session_can_read_markets_without_owner_privileges(self):
        history={'candles':[], 'source':'DERIV_PUBLIC', 'execution':'DISABLED'}
        with patch.object(api, 'owner') as owner, \
             patch('app.deriv_signin.read_session') as read_session, \
             patch.object(api.deriv_market_data, 'fetch_public_candles', new=AsyncMock(return_value=history)):
            result = await api.market_candles(authorization='Bearer deriv_' + 'a' * 64)
        self.assertEqual(result, history)
        read_session.assert_called_once_with('Bearer deriv_' + 'a' * 64)
        owner.assert_not_called()

    async def test_invalid_deriv_session_cannot_read_markets(self):
        with patch.object(api, 'owner') as owner, \
             patch('app.deriv_signin.read_session', side_effect=HTTPException(401, 'Invalid Deriv session')), \
             patch.object(api.deriv_market_data, 'fetch_public_candles', new_callable=AsyncMock) as fetch:
            with self.assertRaises(HTTPException) as caught:
                await api.market_candles(authorization='Bearer deriv_' + 'a' * 64)
        self.assertEqual(caught.exception.status_code, 401)
        owner.assert_not_called()
        fetch.assert_not_awaited()

    async def test_active_forex_catalog_uses_authenticated_deriv_session(self):
        catalog = {
            'markets': [{'symbol': 'frxAUDHUF', 'pair': 'AUDHUF'}],
            'source': 'DERIV_PUBLIC',
            'execution': 'DISABLED',
        }
        with patch.object(api, 'owner') as owner, \
             patch('app.deriv_signin.read_session') as read_session, \
             patch.object(api.deriv_market_data, 'fetch_public_forex_markets', new=AsyncMock(return_value=catalog)):
            result = await api.market_forex(authorization='Bearer deriv_' + 'a' * 64)
        self.assertEqual(result, catalog)
        read_session.assert_called_once_with('Bearer deriv_' + 'a' * 64)
        owner.assert_not_called()

    async def test_active_forex_catalog_requires_auth_before_feed(self):
        with patch.object(api, 'owner', side_effect=HTTPException(401, 'Unauthorized')), \
             patch.object(api.deriv_market_data, 'fetch_public_forex_markets', new_callable=AsyncMock) as fetch:
            with self.assertRaises(HTTPException) as caught:
                await api.market_forex(authorization='')
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

    async def test_any_validated_forex_pair_can_load_history(self):
        history={'candles':[], 'source':'DERIV_PUBLIC', 'execution':'DISABLED'}
        with patch.object(api, 'owner'), patch.object(api.deriv_market_data, 'fetch_public_candles', new=AsyncMock(return_value=history)) as fetch:
            await api.market_candles(pair='AUDHUF', authorization='Bearer test')
        fetch.assert_awaited_once_with('frxAUDHUF', count=80, granularity=300)
