import { useCallback, useEffect, useMemo, useState } from 'react'
import ChangePassword from './ChangePassword'
import {
  ApiError,
  describeError,
  fetchMe,
  login,
  setUnauthorizedHandler,
  signup,
} from './api'
import type { User } from './api'
import Credits from './Credits'
import FoodsPage from './FoodsPage'
import { I18nContext, useI18n } from './i18n/context'
import type { I18n } from './i18n/context'
import {
  LOCALE_NAMES,
  browserLanguages,
  detectLocale,
  loadLocaleChoice,
  setActiveLocale,
  parseLocaleChoice,
  resolveLocale,
  saveLocaleChoice,
  translator,
} from './i18n/i18n'
import type { Locale, LocaleChoice, MessageKey } from './i18n/i18n'
import ProgramsPage from './ProgramsPage'
import { RestBar } from './RestTimer'
import TodayPage from './TodayPage'
import { loadWeightUnit, parseWeightUnit, saveWeightUnit } from './units'
import type { WeightUnit } from './units'
import WorkoutsPage from './WorkoutsPage'
import './App.css'

const TOKEN_KEY = 'haki_token'

type Tab = 'today' | 'foods' | 'workouts' | 'programs' | 'profile'

const TABS: { id: Tab; label: MessageKey }[] = [
  { id: 'today', label: 'nav.today' },
  { id: 'foods', label: 'nav.foods' },
  { id: 'workouts', label: 'nav.workouts' },
  { id: 'programs', label: 'nav.programs' },
  { id: 'profile', label: 'nav.profile' },
]

type Mode = 'login' | 'signup'

function AuthForm({ onLoggedIn }: { onLoggedIn: (token: string) => void }) {
  const { t } = useI18n()
  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function handleSubmit() {
    setError(null)
    setBusy(true)
    let created = false
    try {
      if (mode === 'signup') {
        await signup(email, password)
        created = true
      }
      const { access_token } = await login(email, password)
      onLoggedIn(access_token)
    } catch (err) {
      // The API's own messages stay in English until it sends error codes
      const message = err instanceof ApiError ? err.message : t('app.cannotReach')
      if (created) {
        // The account exists, only the login after it failed (e.g. 429):
        // trying again must log in, not sign up a taken email again
        setMode('login')
        setError(`${t('auth.created')} ${message}`)
      } else {
        setError(message)
      }
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
      <h2>{isSignup ? t('auth.signUpTitle') : t('auth.logInTitle')}</h2>

      <label>
        {t('auth.email')}
        <input
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
          autoComplete="email"
        />
      </label>

      <label>
        {t('auth.password')}
        <input
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
          minLength={isSignup ? 8 : undefined}
          maxLength={128}
          autoComplete={isSignup ? 'new-password' : 'current-password'}
        />
      </label>

      {error && <p className="error">{error}</p>}

      <button type="submit" disabled={busy}>
        {busy ? t('auth.wait') : isSignup ? t('auth.signUp') : t('auth.logIn')}
      </button>

      <button
        type="button"
        className="link"
        onClick={() => {
          setMode(isSignup ? 'login' : 'signup')
          setError(null)
        }}
      >
        {isSignup ? t('auth.toLogIn') : t('auth.toSignUp')}
      </button>
    </form>
  )
}

function Profile({
  token,
  user,
  weightUnit,
  onWeightUnitChange,
  localeChoice,
  browserLocale,
  onLocaleChoiceChange,
  onNewToken,
}: {
  token: string
  user: User
  weightUnit: WeightUnit
  onWeightUnitChange: (unit: WeightUnit) => void
  localeChoice: LocaleChoice
  browserLocale: Locale
  onLocaleChoiceChange: (choice: LocaleChoice) => void
  onNewToken: (token: string) => void
}) {
  const { t, locale } = useI18n()
  const [showCredits, setShowCredits] = useState(false)
  const memberSince = new Date(user.created_at).toLocaleDateString(locale)

  if (showCredits) return <Credits token={token} onBack={() => setShowCredits(false)} />

  return (
    <section className="card">
      <h2>{t('profile.title')}</h2>
      <dl>
        <dt>{t('profile.email')}</dt>
        <dd>{user.email}</dd>
        <dt>{t('profile.memberSince')}</dt>
        <dd>{memberSince}</dd>
        <dt>{t('profile.crewNumber')}</dt>
        <dd>#{user.id}</dd>
      </dl>
      <label className="date-field">
        {t('profile.weightsIn')}
        <select
          value={weightUnit}
          onChange={(event) => onWeightUnitChange(parseWeightUnit(event.target.value))}
        >
          <option value="kg">{t('profile.kilograms')}</option>
          <option value="lb">{t('profile.pounds')}</option>
        </select>
      </label>
      <p className="muted">{t('profile.unitNote')}</p>
      <label className="date-field">
        {t('profile.language')}
        <select
          value={localeChoice}
          onChange={(event) => onLocaleChoiceChange(parseLocaleChoice(event.target.value))}
        >
          <option value="auto">
            {t('profile.languageAuto', { language: LOCALE_NAMES[browserLocale] })}
          </option>
          {/* Each language in itself, so anyone can find their own */}
          <option value="en" lang="en">
            {LOCALE_NAMES.en}
          </option>
          <option value="ro" lang="ro">
            {LOCALE_NAMES.ro}
          </option>
        </select>
      </label>
      <p className="muted">{t('profile.languageNote')}</p>
      <ChangePassword token={token} onNewToken={onNewToken} />
      <button type="button" className="link" onClick={() => setShowCredits(true)}>
        {t('credits.open')}
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
  const { t } = useI18n()
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
            {t(label)}
          </button>
        ))}
      </nav>
      <button type="button" className="link" onClick={onLogout}>
        {t('nav.logOut')}
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
  // A workout to open when the Workouts tab shows, e.g. one just started
  const [openWorkoutId, setOpenWorkoutId] = useState<number | null>(null)
  // Per device for now: accounts get a setting with the body weight work
  const [weightUnit, setWeightUnit] = useState<WeightUnit>(() => loadWeightUnit())
  // An explicit choice in Profile, kept on this device; 'auto' follows the browser
  const [localeChoice, setLocaleChoice] = useState<LocaleChoice>(() => loadLocaleChoice())
  const browserLocale = detectLocale(browserLanguages())
  const locale = resolveLocale(localeChoice, browserLanguages())
  const i18n = useMemo<I18n>(() => {
    // Before the children render: validation and formats outside components follow
    setActiveLocale(locale)
    return { locale, t: translator(locale) }
  }, [locale])
  const { t } = i18n
  const [loadError, setLoadError] = useState<string | null>(null)
  // Bumped by "Try again", to re-run the effect that loads the profile
  const [loadAttempt, setLoadAttempt] = useState(0)

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
    setLoadError(null)
  }, [])

  // Any 401 on an authenticated call means the token expired: log out
  useEffect(() => {
    setUnauthorizedHandler(handleLogout)
    return () => setUnauthorizedHandler(null)
  }, [handleLogout])

  // Whenever we have a token, load the profile. A rejected token (401) already
  // logs out via the handler above; other errors (server or database down) are
  // usually temporary, so keep the token and offer to retry.
  useEffect(() => {
    if (!token) return
    let cancelled = false
    fetchMe(token)
      .then((me) => {
        if (cancelled) return
        setUser(me)
        setLoadError(null)
      })
      .catch((err) => {
        if (!cancelled) setLoadError(describeError(err))
      })
    return () => {
      cancelled = true
    }
  }, [token, loadAttempt])

  // Screen readers, hyphenation and the browser's own messages follow it
  useEffect(() => {
    document.documentElement.lang = locale
  }, [locale])

  if (!token) {
    return (
      <I18nContext.Provider value={i18n}>
        <main className="container">
          <h1>Haki</h1>
          <p className="tagline">{t('app.tagline')}</p>
          <AuthForm onLoggedIn={handleLoggedIn} />
        </main>
      </I18nContext.Provider>
    )
  }

  return (
    <I18nContext.Provider value={i18n}>
    <main className="container">
      <Header
        tab={tab}
        onTabChange={(next) => {
          setOpenWorkoutId(null)
          setTab(next)
        }}
        onLogout={handleLogout}
      />
      {/* Outside the pages: a running rest shows on every screen */}
      <RestBar />
      {!user && !loadError && <p>{t('app.loading')}</p>}
      {!user && loadError && (
        <section className="card">
          <p className="error">{loadError}</p>
          <button
            type="button"
            onClick={() => {
              setLoadError(null)
              setLoadAttempt((attempt) => attempt + 1)
            }}
          >
            {t('app.tryAgain')}
          </button>
        </section>
      )}
      {user && tab === 'today' && (
        <TodayPage token={token} onGoToFoods={() => setTab('foods')} />
      )}
      {user && tab === 'foods' && <FoodsPage token={token} />}
      {user && tab === 'workouts' && (
        <WorkoutsPage token={token} weightUnit={weightUnit} openWorkoutId={openWorkoutId} />
      )}
      {user && tab === 'programs' && (
        <ProgramsPage
          token={token}
          weightUnit={weightUnit}
          onWorkoutStarted={(workoutId) => {
            setOpenWorkoutId(workoutId)
            setTab('workouts')
          }}
        />
      )}
      {user && tab === 'profile' && (
        <Profile
          token={token}
          user={user}
          weightUnit={weightUnit}
          onWeightUnitChange={(unit) => {
            saveWeightUnit(unit)
            setWeightUnit(unit)
          }}
          localeChoice={localeChoice}
          browserLocale={browserLocale}
          onNewToken={handleLoggedIn}
          onLocaleChoiceChange={(choice) => {
            saveLocaleChoice(choice)
            setLocaleChoice(choice)
          }}
        />
      )}
    </main>
    </I18nContext.Provider>
  )
}

export default App
