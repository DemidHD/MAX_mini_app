import { MaxUI } from '@maxhub/max-ui'
import { RouterProvider } from 'react-router-dom'

import { router } from '@/app/router'
import { AuthProvider } from '@/auth/AuthContext'

export function App() {
  return (
    <MaxUI>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </MaxUI>
  )
}
