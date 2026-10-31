import { useEffect, useState } from 'react'
import { ApiError, fetchMe, login, signup } from './api'
import type { User } from './api'
import './App.css'

const TOKEN_KEY = 'haki_token'

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

function App() {
  const [token, setToken] = useState<string | null>(() =>
    localStorage.getItem(TOKEN_KEY),
  )
  const [user, setUser] = useState<User | null>(null)

  function handleLoggedIn(newToken: string) {
    localStorage.setItem(TOKEN_KEY, newToken)
    setToken(newToken)
  }

  function handleLogout() {
    localStorage.removeItem(TOKEN_KEY)
    setToken(null)
    setUser(null)
  }

  // Whenever we have a token, load the profile; drop the token if it is rejected
  useEffect(() => {
    if (!token) return
    let cancelled = false
    fetchMe(token)
      .then((me) => {
        if (!cancelled) setUser(me)
      })
      .catch(() => {
        if (!cancelled) {
          localStorage.removeItem(TOKEN_KEY)
          setToken(null)
          setUser(null)
        }
      })
    return () => {
      cancelled = true
    }
  }, [token])

  return (
    <main className="container">
      <h1>Haki</h1>
      <p className="tagline">Train your Haki. Track your fuel.</p>
      {!token && <AuthForm onLoggedIn={handleLoggedIn} />}
      {token && !user && <p>Loading…</p>}
      {token && user && <Profile user={user} onLogout={handleLogout} />}
    </main>
  )
}

export default App
