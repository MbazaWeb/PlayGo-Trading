'use client'

import dynamic from 'next/dynamic'

const AccountWorkspace = dynamic(() => import('@/AccountWorkspace'), {
  ssr: false,
  loading: () => <div className="min-h-screen flex items-center justify-center">Loading Deriv workspace...</div>,
})

export function DerivWorkspaceEntry() {
  return <AccountWorkspace />
}
