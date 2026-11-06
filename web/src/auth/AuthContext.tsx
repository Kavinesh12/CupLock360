import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, post, tokenStore } from '../api/client'
import type { Me, OtpChallenge, Tokens } from '../api/types'

interface AuthState {
  me: Me | null
  loading: boolean
  startLogin: (login: string, password: string) => Promise<OtpChallenge>
  verifyOtp: (challengeId: string, code: string) => Promise<void>
  logout: () => Promise<void>
  can: (...perms: string[]) => boolean
}

const Ctx = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)

  const loadMe = useCallback(async () => {
    if (!tokenStore.get()) {
      setMe(null)
      return
    }
    try {
      setMe(await api<Me>('/auth/me'))
    } catch {
      tokenStore.set(null)
      setMe(null)
    }
  }, [])

  useEffect(() => {
    loadMe().finally(() => setLoading(false))
    const onLogout = () => {
      tokenStore.set(null)
      setMe(null)
    }
    window.addEventListener('cuplock:logout', onLogout)
    return () => window.removeEventListener('cuplock:logout', onLogout)
  }, [loadMe])

  const value: AuthState = {
    me,
    loading,
    startLogin: (login, password) => post<OtpChallenge>('/auth/login', { login, password }),
    verifyOtp: async (challenge_id, code) => {
      tokenStore.set(await post<Tokens>('/auth/verify-otp', { challenge_id, code }))
      await loadMe()
    },
    logout: async () => {
      const t = tokenStore.get()
      if (t) await post('/auth/logout', { refresh_token: t.refresh_token }).catch(() => undefined)
      tokenStore.set(null)
      setMe(null)
    },
    can: (...perms) => !!me && perms.every((p) => me.permissions.includes(p)),
  }
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAuth() {
  const c = useContext(Ctx)
  if (!c) throw new Error('useAuth outside AuthProvider')
  return c
}
