import { useCallback, useEffect, useState } from 'react'
import { Redirect, Route } from 'react-router-dom'
import { IonApp, IonLoading, IonRouterOutlet, setupIonicReact } from '@ionic/react'
import { IonReactRouter } from '@ionic/react-router'
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
import LeadsPage from './pages/LeadsPage'
import LeadNewPage from './pages/LeadNewPage'
import LeadDetailPage from './pages/LeadDetailPage'
import StockPage from './pages/StockPage'

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

  if (loading) return <IonApp><IonLoading isOpen /></IonApp>
  if (!me) return <IonApp><LoginPage onLoggedIn={loadMe} /></IonApp>
  return (
    <IonApp>
      <IonReactRouter>
        <IonRouterOutlet>
          <Route exact path="/home"><HomePage me={me} onLogout={logout} /></Route>
          <Route exact path="/leads"><LeadsPage me={me} /></Route>
          <Route exact path="/leads/new"><LeadNewPage /></Route>
          <Route exact path="/leads/:id(\d+)"><LeadDetailPage me={me} /></Route>
          <Route exact path="/stock"><StockPage /></Route>
          <Route exact path="/"><Redirect to="/home" /></Route>
        </IonRouterOutlet>
      </IonReactRouter>
    </IonApp>
  )
}
