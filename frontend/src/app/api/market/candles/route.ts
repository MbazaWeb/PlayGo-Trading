import { json, err } from '@/lib/api'
import { getCandles } from '@/lib/market'

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url)
  const symbol = searchParams.get('symbol') || 'EUR/USD'
  const timeframe = searchParams.get('timeframe') || 'M15'
  const bars = parseInt(searchParams.get('bars') || '120', 10)
  const to = new Date()
  const from = new Date(to.getTime() - bars * 60 * 1000 * tfMinutes(timeframe))
  try {
    const candles = await getCandles(symbol, timeframe, from, to)
    return json({ symbol, timeframe, candles, source: 'synthetic', isPaper: true })
  } catch (e) {
    return err((e as Error).message, 400)
  }
}

function tfMinutes(tf: string): number {
  switch (tf) {
    case 'M1': return 1
    case 'M5': return 5
    case 'M15': return 15
    case 'H1': return 60
    case 'H4': return 240
    case 'D1': return 1440
    default: return 15
  }
}
