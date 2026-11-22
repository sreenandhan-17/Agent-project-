import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'

import { ApiError, api, saveSession } from '../api'

export default function Login() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState<string | null>(
    params.get('expired') ? 'Your session expired. Please log in again.' : null,
  )
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const { access_token, agent } = await api.login(email, password)
      saveSession(access_token, agent)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not reach the server')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Frontdesk</h1>
          <p className="text-sm text-slate-500">Arvo Systems support: agent login</p>
        </div>
        <label className="block">
          <span className="text-sm font-medium text-slate-700">Email</span>
          <input
            type="email"
            autoComplete="username"
            autoCapitalize="off"
            autoCorrect="off"
            spellCheck={false}
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 focus:border-sky-500 focus:outline-none"
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium text-slate-700">Password</span>
          <div className="mt-1 flex gap-2">
            <input
              type={showPassword ? 'text' : 'password'}
              autoComplete="current-password"
              autoCapitalize="off"
              autoCorrect="off"
              spellCheck={false}
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 focus:border-sky-500 focus:outline-none"
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              className="shrink-0 rounded-md border border-slate-300 px-3 text-sm text-slate-600 hover:bg-slate-50"
            >
              {showPassword ? 'Hide' : 'Show'}
            </button>
          </div>
        </label>
        {error && <p className="rounded bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
        <button
          disabled={busy}
          className="w-full rounded-md bg-sky-600 py-2 font-medium text-white hover:bg-sky-700 disabled:opacity-60"
        >
          {busy ? 'Logging in…' : 'Log in'}
        </button>
        <p className="text-xs text-slate-400">
          Demo: ananya@arvo.example (admin) or rahul@arvo.example. Demo password is shared
          privately with reviewers in the submission note.
        </p>
        <p className="border-t border-slate-100 pt-3 text-sm text-slate-600">
          Not an agent?{' '}
          <Link to="/new" className="font-medium text-sky-700 hover:underline">
            Customer portal: contact support →
          </Link>
        </p>
      </form>
    </main>
  )
}
