import type { ReactNode } from 'react'
import { Link } from 'react-router'

/** Shell for customer-facing pages: no agent name, no agent navigation. */
export default function PublicLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-4 py-3">
          <Link to="/new" className="text-lg font-semibold text-slate-900">
            Arvo Systems Support
          </Link>
          <Link to="/new" className="text-sm text-sky-700 hover:underline">
            New request
          </Link>
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-4 py-6">{children}</main>
    </div>
  )
}
