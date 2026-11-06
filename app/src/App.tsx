import { useCallback, useEffect, useState } from 'react'
import { IonApp, IonLoading, setupIonicReact } from '@ionic/react'
import '@ionic/react/css/core.css'
import '@ionic/react/css/normalize.css'
import '@ionic/react/css/structure.css'
import '@ionic/react/css/typography.css'
import '@ionic/react/css/padding.css'
import '@ionic/react/css/flex-utils.css'
import './theme.css'
import { api, post, tokens, type Me } from './api/client'
import LoginPage from './pages/LoginPage'
import HomePage from './pages/HomePage'

setupIonicReact({ mode: 'md' })

export default function App() {
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)

  const loadMe = useCallback(async () => {
    if (!(await tokens.get())) return setMe(null)
    try { setMe(await api<Me>('/auth/me')) } catch { await tokens.set(null); setMe(null) }
  }, [])

  useEffect(() => { loadMe().finally(() => setLoading(false)) }, [loadMe])

  const logout = async () => {
    const t = await tokens.get()
    if (t) await post('/auth/logout', { refresh_token: t.refresh_token }).catch(() => undefined)
    await tokens.set(null)
    setMe(null)
  }

  return (
    <IonApp>
      {loading ? <IonLoading isOpen /> : me ? <HomePage me={me} onLogout={logout} /> : <LoginPage onLoggedIn={loadMe} />}
    </IonApp>
  )
}
