import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import '@maxhub/max-ui/dist/styles.css'
import '@/index.css'
import '@/styles/screen.css'
import '@/styles/p1.css'
import { App } from '@/App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
