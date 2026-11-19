'use client'
import * as React from 'react'

type Candle = { ts: string; open: string; high: string; low: string; close: string }

export function CandlestickChart({ candles, height = 320 }: { candles: Candle[]; height?: number }) {
  const ref = React.useRef<SVGSVGElement | null>(null)
  const [width, setWidth] = React.useState(800)
  React.useEffect(() => {
    const el = ref.current?.parentElement
    if (!el) return
    const ro = new ResizeObserver((entries) => {
      for (const e of entries) setWidth(Math.max(320, e.contentRect.width))
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  if (!candles.length) {
    return (
      <div className="flex items-center justify-center text-muted-foreground text-sm border rounded-md" style={{ height }}>
        No candle data yet.
      </div>
    )
  }

  const padLeft = 8
  const padRight = 56
  const padTop = 8
  const padBottom = 18
  const plotW = Math.max(50, width - padLeft - padRight)
  const plotH = height - padTop - padBottom

  const highs = candles.map(c => parseFloat(c.high))
  const lows = candles.map(c => parseFloat(c.low))
  let min = Math.min(...lows)
  let max = Math.max(...highs)
  if (min === max) { min -= 1; max += 1 }
  const range = max - min
  min -= range * 0.05
  max += range * 0.05

  const n = candles.length
  const cw = plotW / n
  const bodyW = Math.max(1, cw * 0.6)

  const y = (price: number) => padTop + (1 - (price - min) / (max - min)) * plotH
  const x = (i: number) => padLeft + i * cw + cw / 2

  // Y-axis ticks
  const ticks = 5
  const tickVals: number[] = []
  for (let i = 0; i <= ticks; i++) tickVals.push(min + (i / ticks) * (max - min))

  const lastClose = parseFloat(candles[candles.length - 1].close)
  const firstClose = parseFloat(candles[0].close)
  const up = lastClose >= firstClose

  return (
    <svg ref={ref} width={width} height={height} className="block" role="img" aria-label="Candlestick chart">
      {/* grid */}
      {tickVals.map((v, i) => (
        <g key={i}>
          <line x1={padLeft} x2={padLeft + plotW} y1={y(v)} y2={y(v)} stroke="currentColor" className="text-border" strokeWidth={0.5} />
          <text x={padLeft + plotW + 4} y={y(v) + 3} className="fill-muted-foreground" fontSize={10}>{v.toFixed(5)}</text>
        </g>
      ))}
      {candles.map((c, i) => {
        const o = parseFloat(c.open), h = parseFloat(c.high), l = parseFloat(c.low), cl = parseFloat(c.close)
        const bullish = cl >= o
        const color = bullish ? '#16a34a' : '#dc2626'
        const bodyTop = y(Math.max(o, cl))
        const bodyBot = y(Math.min(o, cl))
        return (
          <g key={i}>
            <line x1={x(i)} x2={x(i)} y1={y(h)} y2={y(l)} stroke={color} strokeWidth={1} />
            <rect x={x(i) - bodyW / 2} y={bodyTop} width={bodyW} height={Math.max(1, bodyBot - bodyTop)} fill={color} />
          </g>
        )
      })}
      {/* last price line */}
      <line x1={padLeft} x2={padLeft + plotW} y1={y(lastClose)} y2={y(lastClose)} stroke={up ? '#16a34a' : '#dc2626'} strokeDasharray="3 3" strokeWidth={1} />
      <text x={padLeft + plotW + 4} y={y(lastClose) + 3} fontSize={10} fill={up ? '#16a34a' : '#dc2626'}>{lastClose.toFixed(5)}</text>
    </svg>
  )
}

export function LineChart({ points, height = 200, color = '#0ea5e9' }: { points: { ts: string; value: number }[]; height?: number; color?: string }) {
  const ref = React.useRef<SVGSVGElement | null>(null)
  const [width, setWidth] = React.useState(600)
  React.useEffect(() => {
    const el = ref.current?.parentElement
    if (!el) return
    const ro = new ResizeObserver((entries) => {
      for (const e of entries) setWidth(Math.max(280, e.contentRect.width))
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  if (!points.length) {
    return <div className="flex items-center justify-center text-muted-foreground text-sm border rounded-md" style={{ height }}>No data.</div>
  }
  const padLeft = 8, padRight = 8, padTop = 8, padBottom = 18
  const plotW = Math.max(50, width - padLeft - padRight)
  const plotH = height - padTop - padBottom
  const vals = points.map(p => p.value)
  let min = Math.min(...vals), max = Math.max(...vals)
  if (min === max) { min -= 1; max += 1 }
  const y = (v: number) => padTop + (1 - (v - min) / (max - min)) * plotH
  const x = (i: number) => padLeft + (i / Math.max(1, points.length - 1)) * plotW
  const path = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${x(i).toFixed(1)} ${y(p.value).toFixed(1)}`).join(' ')
  const area = `${path} L ${x(points.length - 1).toFixed(1)} ${plotH + padTop} L ${x(0).toFixed(1)} ${plotH + padTop} Z`
  return (
    <svg ref={ref} width={width} height={height} className="block" role="img" aria-label="Line chart">
      <path d={area} fill={color} opacity={0.12} />
      <path d={path} fill="none" stroke={color} strokeWidth={1.5} />
    </svg>
  )
}
