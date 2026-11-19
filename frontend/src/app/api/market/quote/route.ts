import { json, err } from '@/lib/api'
import { getQuote } from '@/lib/market'

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url)
  const symbol = searchParams.get('symbol')
  if (!symbol) return err('symbol required')
  try {
    const q = await getQuote(symbol)
    return json({ quote: q })
  } catch (e) {
    return err((e as Error).message, 400)
  }
}
