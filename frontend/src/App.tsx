import { useCallback, useEffect, useState } from 'react'
import { ApiError, fetchMe, login, setUnauthorizedHandler, signup } from './api'
import type { User } from './api'
import FoodsPage from './FoodsPage'
import TodayPage from './TodayPage'
import './App.css'

const TOKEN_KEY = 'haki_token'

type Tab = 'today' | 'foods' | 'profile'

const TABS: { id: Tab; label: string }[] = [
  { id: 'today', label: 'Today' },
  { id: 'foods', label: 'Foods' },
  { id: 'profile', label: 'Profile' },
]

type Mode = 'login' | 'signup'

function AuthForm({ onLoggedIn }: { onLoggedIn: (token: string) => void }) {
  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function handleSubmit() {
    setError(null)
    setBusy(true)
    try {
      if (mode === 'signup') {
        await signup(email, password)
      }
      const { access_token } = await login(email, password)
      onLoggedIn(access_token)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Cannot reach the server')
    } finally {
      setBusy(false)
    }
  }

  const isSignup = mode === 'signup'

  return (
    <form
      className="card"
      onSubmit={(event) => {
        event.preventDefault()
        void handleSubmit()
      }}
    >
      <h2>{isSignup ? 'Create your account' : 'Welcome back'}</h2>

      <label>
        Email
        <input
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
          autoComplete="email"
        />
      </label>

      <label>
        Password
        <input
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
          minLength={isSignup ? 8 : undefined}
          autoComplete={isSignup ? 'new-password' : 'current-password'}
        />
      </label>

      {error && <p className="error">{error}</p>}

      <button type="submit" disabled={busy}>
        {busy ? 'Please wait…' : isSignup ? 'Sign up' : 'Log in'}
      </button>

      <button
        type="button"
        className="link"
        onClick={() => {
          setMode(isSignup ? 'login' : 'signup')
          setError(null)
        }}
      >
        {isSignup ? 'Already have an account? Log in' : 'New here? Create an account'}
      </button>
    </form>
  )
}

function Profile({ user, onLogout }: { user: User; onLogout: () => void }) {
  const memberSince = new Date(user.created_at).toLocaleDateString()

  return (
    <section className="card">
      <h2>Welcome aboard!</h2>
      <dl>
        <dt>Email</dt>
        <dd>{user.email}</dd>
        <dt>Member since</dt>
        <dd>{memberSince}</dd>
        <dt>Crew number</dt>
        <dd>#{user.id}</dd>
      </dl>
      <button type="button" onClick={onLogout}>
        Log out
      </button>
    </section>
  )
}

function Header({
  tab,
  onTabChange,
  onLogout,
}: {
  tab: Tab
  onTabChange: (tab: Tab) => void
  onLogout: () => void
}) {
  return (
    <header className="app-header">
      <span className="brand">Haki</span>
      <nav className="tabs">
        {TABS.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            className="tab"
            aria-current={tab === id ? 'page' : undefined}
            onClick={() => onTabChange(id)}
          >
            {label}
          </button>
        ))}
      </nav>
      <button type="button" className="link" onClick={onLogout}>
        Log out
      </button>
    </header>
  )
}

function App() {
  const [token, setToken] = useState<string | null>(() =>
    localStorage.getItem(TOKEN_KEY),
  )
  const [user, setUser] = useState<User | null>(null)
  const [tab, setTab] = useState<Tab>('today')

  function handleLoggedIn(newToken: string) {
    localStorage.setItem(TOKEN_KEY, newToken)
    setToken(newToken)
  }

  // Stable across renders, so effects that use it don't re-run needlessly
  const handleLogout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    setToken(null)
    setUser(null)
    setTab('today')
  }, [])

  // Any 401 on an authenticated call means the token expired: log out
  useEffect(() => {
    setUnauthorizedHandler(handleLogout)
    return () => setUnauthorizedHandler(null)
  }, [handleLogout])

  // Whenever we have a token, load the profile; drop the token if it is rejected
  useEffect(() => {
    if (!token) return
    let cancelled = false
    fetchMe(token)
      .then((me) => {
        if (!cancelled) setUser(me)
      })
      .catch(() => {
        if (!cancelled) handleLogout()
      })
    return () => {
      cancelled = true
    }
  }, [token, handleLogout])

  if (!token) {
    return (
      <main className="container">
        <h1>Haki</h1>
        <p className="tagline">Train your Haki. Track your fuel.</p>
        <AuthForm onLoggedIn={handleLoggedIn} />
      </main>
    )
  }

  return (
    <main className="container">
      <Header tab={tab} onTabChange={setTab} onLogout={handleLogout} />
      {!user && <p>Loading…</p>}
      {user && tab === 'today' && (
        <TodayPage token={token} onGoToFoods={() => setTab('foods')} />
      )}
      {user && tab === 'foods' && <FoodsPage token={token} />}
      {user && tab === 'profile' && <Profile user={user} onLogout={handleLogout} />}
    </main>
  )
}

export default App
