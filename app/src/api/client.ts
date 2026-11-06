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

export type LeadStatus = 'new' | 'contacted' | 'quoted' | 'won' | 'lost'

export interface Lead {
  id: number
  company_name: string
  contact_name: string | null
  phone: string | null
  city: string | null
  requirement: string | null
  status: LeadStatus
  next_follow_up_at: string | null
  branch_id: number
}

export interface FollowUp { id: number; at: string; channel: string; note: string; next_follow_up_at: string | null }
export interface LeadDetail extends Lead { follow_ups: FollowUp[]; lost_reason: string | null }
export interface Branch { id: number; code: string; name: string }

export const fmt = (v: string | null) =>
  v ? new Date(v).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : ''

/** Test mode only (console OTP delivery): read the latest OTP from the dev outbox. */
export const devOtp = async (): Promise<string | null> => {
  try { return (await fetch(`${BASE}/dev/otp-outbox`).then((r) => r.json()))[0]?.code ?? null } catch { return null }
}

export interface ReqLine { item_id: number; qty_requested: number; qty_approved: number | null; qty_dispatched: number; rate_per_day: string }
export interface DispatchRow {
  id: number; challan_no: string; request_id: number; request_ref: string; site_id: number; site_name: string
  status: 'in_transit' | 'received'; vehicle_no: string | null; driver_name: string | null; dispatched_at: string
  lines: { item_id: number; qty: number; qty_received: number | null; qty_short: number | null }[]
}
export interface MatRequest {
  id: number; ref_no: string; status: string; client_name: string; site_name: string; warehouse_code: string
  required_on: string; duration_days: number; est_total: string; est_gst: string; created_at: string; version: number
  lines: ReqLine[]; dispatches: DispatchRow[]
}
export interface MatRequestDetail extends MatRequest {
  availability: { item_id: number; need: number; available: number | null; short: number | null }[]
  client: { credit_status: string }
  can_approve: boolean
  my_approval_limit: string | null
}
export interface ItemLite { id: number; code: string; name: string }
export const inr = (v: string | number | null | undefined) =>
  v == null || v === '' ? '' : `₹${Number(v).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`
