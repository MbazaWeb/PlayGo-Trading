import { NextResponse } from 'next/server'

export async function POST() {
  return NextResponse.json(
    { error: 'Public registration is disabled. The application uses one authorized company owner.' },
    { status: 403 },
  )
}
