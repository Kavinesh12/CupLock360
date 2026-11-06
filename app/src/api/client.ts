import { Preferences } from '@capacitor/preferences'

const BASE = (import.meta.env.VITE_API_URL ?? '') + '/api/v1'
const KEY = 'cuplock.tokens'

export interface Tokens { access_token: string; refresh_token: string; expires_in: number }
export interface OtpChallenge { challenge_id: string; channel: string; expires_at: string; sent_to: string | null }
export interface Me {
  id: number
  username: string
  full_name: string
  roles: string[]
  permissions: string[]
  approval_limit: number | null
}

let cached: Tokens | null | undefined

export const tokens = {
  async get(): Promise<Tokens | null> {
    if (cached !== undefined) return cached
    const { value } = await Preferences.get({ key: KEY })
    cached = value ? (JSON.parse(value) as Tokens) : null
    return cached
  },
  async set(t: Tokens | null) {
    cached = t
    if (t) await Preferences.set({ key: KEY, value: JSON.stringify(t) })
    else await Preferences.remove({ key: KEY })
  },
}

async function errorMessage(r: Response): Promise<string> {
  try {
    const d = (await r.json()).detail
    if (typeof d === 'string') return d
    if (d?.message) return d.message
  } catch { /* ignore */ }
  return r.statusText || 'Request failed'
}

async function refresh(): Promise<boolean> {
  const t = await tokens.get()
  if (!t) return false
  const r = await fetch(`${BASE}/auth/refresh`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: t.refresh_token }),
  })
  if (!r.ok) { await tokens.set(null); return false }
  await tokens.set(await r.json())
  return true
}

export async function api<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const t = await tokens.get()
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (t) headers.Authorization = `Bearer ${t.access_token}`
  const r = await fetch(`${BASE}${path}`, { ...init, headers })
  if (r.status === 401 && retry && t && (await refresh())) return api<T>(path, init, false)
  if (!r.ok) throw new Error(await errorMessage(r))
  return (r.status === 204 ? undefined : await r.json()) as T
}

export const post = <T>(path: string, body: unknown) => api<T>(path, { method: 'POST', body: JSON.stringify(body) })
