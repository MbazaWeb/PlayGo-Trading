import { json } from '@/lib/api'
import { listInstruments } from '@/lib/market'

export async function GET() {
  const instruments = await listInstruments()
  return json({ instruments })
}
