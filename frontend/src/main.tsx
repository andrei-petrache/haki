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

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
