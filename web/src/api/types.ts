export interface Me {
  id: number
  username: string
  full_name: string
  phone: string | null
  email: string | null
  roles: string[]
  permissions: string[]
  scopes: { type: string; id: number }[]
  approval_limit: number | null
}

export interface OtpChallenge {
  challenge_id: string
  channel: string
  expires_at: string
  sent_to: string | null
}

export interface Tokens {
  access_token: string
  refresh_token: string
  expires_in: number
}

export interface Scope { type: 'branch' | 'warehouse' | 'site' | 'client'; id: number }

export interface UserRow {
  id: number
  username: string
  full_name: string
  phone: string | null
  email: string | null
  is_active: boolean
  roles: string[]
  scopes: Scope[]
  approval_limit: string | null
}

export interface Role {
  id: number
  code: string
  name: string
  description: string | null
  is_system: boolean
  permissions: string[]
  user_count: number
}

export interface Permission { code: string; module: string; description: string }

export interface Branch {
  id: number
  code: string
  name: string
  city: string | null
  state: string
  gstin: string | null
  address: string | null
  is_active: boolean
}

export interface Warehouse {
  id: number
  branch_id: number
  code: string
  name: string
  address: string | null
  is_active: boolean
}

export interface AuditRow {
  id: number
  at: string
  user_id: number | null
  action: string
  entity: string | null
  entity_id: string | null
  data: Record<string, unknown> | null
  ip: string | null
}
