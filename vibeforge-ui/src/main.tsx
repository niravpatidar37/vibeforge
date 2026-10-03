import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// Self-hosted fonts (SIL OFL): no third-party font requests leave the browser.
// Fraunces with the SOFT axis (~140 KB) rather than all axes (~270 KB).
import '@fontsource-variable/fraunces/soft.css'
import '@fontsource-variable/fraunces/soft-italic.css'
import '@fontsource-variable/instrument-sans/index.css'
import '@fontsource/dm-mono/400.css'
import '@fontsource/dm-mono/500.css'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
