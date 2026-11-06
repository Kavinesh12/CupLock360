import type { Tokens } from './types'

const BASE = (import.meta.env.VITE_API_URL ?? '') + '/api/v1'
const KEY = 'cuplock.tokens'

export class ApiError extends Error {
  constructor(public status: number, message: string, public code?: string) {
    super(message)
  }
}

export const tokenStore = {
  get(): Tokens | null {
    try {
      const raw = localStorage.getItem(KEY)
      return raw ? (JSON.parse(raw) as Tokens) : null
    } catch {
      return null
    }
  },
  set(t: Tokens | null) {
    try {
      if (t) localStorage.setItem(KEY, JSON.stringify(t))
      else localStorage.removeItem(KEY)
    } catch {
      /* storage unavailable */
    }
  },
}

let refreshing: Promise<boolean> | null = null

async function refresh(): Promise<boolean> {
  const t = tokenStore.get()
  if (!t) return false
  const r = await fetch(`${BASE}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: t.refresh_token }),
  })
  if (!r.ok) {
    tokenStore.set(null)
    return false
  }
  tokenStore.set(await r.json())
  return true
}

async function toError(r: Response): Promise<ApiError> {
  let msg = r.statusText
  let code: string | undefined
  try {
    const body = await r.json()
    const d = body.detail
    if (typeof d === 'string') msg = d
    else if (d && typeof d === 'object' && 'message' in d) {
      msg = d.message
      code = d.code
    } else if (Array.isArray(d)) msg = d.map((e: { msg: string }) => e.msg).join('; ')
  } catch {
    /* not json */
  }
  return new ApiError(r.status, msg, code)
}

export async function api<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const t = tokenStore.get()
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (t) headers.Authorization = `Bearer ${t.access_token}`
  const r = await fetch(`${BASE}${path}`, { ...init, headers: { ...headers, ...(init.headers as object) } })
  if (r.status === 401 && retry && t) {
    refreshing ??= refresh().finally(() => (refreshing = null))
    if (await refreshing) return api<T>(path, init, false)
    window.dispatchEvent(new Event('cuplock:logout'))
  }
  if (!r.ok) throw await toError(r)
  if (r.status === 204) return undefined as T
  return r.json() as Promise<T>
}

export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })
export const patch = <T>(path: string, body: unknown) => api<T>(path, { method: 'PATCH', body: JSON.stringify(body) })
export const put = <T>(path: string, body: unknown) => api<T>(path, { method: 'PUT', body: JSON.stringify(body) })
