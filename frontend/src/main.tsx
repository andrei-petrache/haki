import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// Inter for text, Space Grotesk for numerals: bundled, not from a font CDN.
// Each file declares its subsets with unicode-range, so a browser fetches
// only what a page uses (latin and latin-ext cover a-breve, s- and t-comma).
import '@fontsource/inter/400.css'
import '@fontsource/inter/500.css'
import '@fontsource/inter/600.css'
import '@fontsource/inter/700.css'
import '@fontsource/space-grotesk/500.css'
import '@fontsource/space-grotesk/700.css'
import './index.css'
import App from './App.tsx'
import { takeResetToken } from './reset'

// Once, before React renders (StrictMode runs initializers twice): on
// /reset the token leaves the address bar and history right away
const resetToken = takeResetToken(window.location, window.history)

// Installable, and the app shell opens offline (public/sw.js). Only in a
// built app: the dev server's modules are not hashed files to cache
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {})
  })
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App resetToken={resetToken} />
  </StrictMode>,
)
