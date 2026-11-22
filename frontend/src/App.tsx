import type { ReactNode } from 'react'
import { BrowserRouter, Link, Navigate, Route, Routes, useNavigate } from 'react-router'

import { clearSession, getSession } from './api'
import Login from './pages/Login'
import TicketDetail from './pages/TicketDetail'
import TicketList from './pages/TicketList'

function RequireLogin({ children }: { children: ReactNode }) {
  return getSession() ? children : <Navigate to="/login" replace />
}

function Layout({ children }: { children: ReactNode }) {
  const navigate = useNavigate()
  const agent = getSession()?.agent

  function logout() {
    clearSession()
    navigate('/login', { replace: true })
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <Link to="/" className="text-lg font-semibold text-slate-900">
            Frontdesk
          </Link>
          <div className="flex items-center gap-3 text-sm">
            <span className="text-slate-600">
              {agent?.name}
              {agent?.role === 'ADMIN' && (
                <span className="ml-1 rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-500">admin</span>
              )}
            </span>
            <button onClick={logout} className="text-sky-700 hover:underline">
              Log out
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/"
          element={
            <RequireLogin>
              <Layout>
                <TicketList />
              </Layout>
            </RequireLogin>
          }
        />
        <Route
          path="/tickets/:id"
          element={
            <RequireLogin>
              <Layout>
                <TicketDetail />
              </Layout>
            </RequireLogin>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
