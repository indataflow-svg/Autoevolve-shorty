import { createContext, useContext, useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { ArrowRight, LockKeyhole } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { api, ApiError, type Credentials } from '../api/client'

const AuthContext = createContext<Credentials | null>(null)
export type Plan = 'free' | 'paid'
const PlanContext = createContext<Plan>('paid')

// A sentinel, not a credential: the client deliberately omits the Basic header
// when the password is empty, so requests authenticate with the HttpOnly cookie.
const SESSION_CREDENTIALS: Credentials = { username: 'session', password: '' }

export function useCredentials(): Credentials {
  const value = useContext(AuthContext)
  if (!value) throw new Error('Authentication is required')
  return value
}

export function useAuthSession(): boolean {
  return useCredentials().password === ''
}

export function usePlan(): Plan {
  return useContext(PlanContext)
}

export function AuthGate({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [credentials, setCredentials] = useState<Credentials | null>(null)
  const [plan, setPlan] = useState<Plan>('paid')
  const [checking, setChecking] = useState(true)
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetch('/company/ui/session', {
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    })
      .then(async response => {
        if (!response.ok || cancelled) return
        let orgPlan: Plan = 'free'
        try {
          const me = await fetch('/api/auth/me', {
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
          })
          if (me.ok) {
            const body = await me.json() as { org?: { plan?: string } }
            orgPlan = body.org?.plan === 'paid' ? 'paid' : 'free'
          }
        } catch {
          // Fail closed: an unknown website plan is treated as free.
        }
        if (!cancelled) {
          setPlan(orgPlan)
          setCredentials(SESSION_CREDENTIALS)
        }
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setChecking(false) })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    const expire = () => {
      if (!credentials) return
      queryClient.clear()
      setCredentials(null)
      setPlan('paid')
      setError('Your dashboard credentials were rejected. Sign in again.')
    }
    window.addEventListener('autoevolve:auth-failed', expire)
    return () => window.removeEventListener('autoevolve:auth-failed', expire)
  }, [credentials, queryClient])

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const candidate = { username: String(data.get('username') || ''), password: String(data.get('password') || '') }
    setPending(true)
    setError('')
    try {
      await api('/company/ui/session', candidate)
      queryClient.clear()
      setPlan('paid')
      setCredentials(candidate)
    } catch (reason) {
      setError(reason instanceof ApiError && reason.status === 401
        ? 'Incorrect dashboard username or password.'
        : reason instanceof Error ? reason.message : 'Sign in failed')
    } finally { setPending(false) }
  }

  if (checking) return <main className="sign-in-screen"><div className="sign-in-card"><p>Checking your session…</p></div></main>
  if (credentials) return <AuthContext.Provider value={credentials}><PlanContext.Provider value={plan}>{children}</PlanContext.Provider></AuthContext.Provider>
  return <main className="sign-in-screen">
    <form className="sign-in-card" onSubmit={signIn}>
      <div className="sign-in-icon"><LockKeyhole size={24} /></div>
      <h1>Auto<span>Evolve</span></h1>
      <p>Sign in with your dashboard username and password.</p>
      <label>Username<input name="username" autoComplete="username" required /></label>
      <label>Password<input name="password" type="password" autoComplete="current-password" required /></label>
      {error && <div className="form-error" role="alert">{error}</div>}
      <button className="button primary" type="submit" disabled={pending}>{pending ? 'Signing in…' : 'Sign in'} <ArrowRight size={16} /></button>
    </form>
  </main>
}
