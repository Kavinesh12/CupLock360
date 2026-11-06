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

export type CreditStatus = 'pending' | 'approved' | 'hold'

export interface Client {
  id: number
  code: string
  name: string
  branch_id: number
  gstin: string | null
  pan: string | null
  billing_address: string | null
  state: string
  state_code: string
  contact_name: string | null
  phone: string | null
  email: string | null
  notes: string | null
  is_active: boolean
  payment_terms_days: number
  credit_limit: string
  security_deposit: string
  credit_status: CreditStatus
}

export interface Site {
  id: number
  project_id: number
  code: string
  name: string
  address: string | null
  city: string | null
  state: string
  state_code: string
  manager_user_id: number | null
  contact_phone: string | null
  is_active: boolean
}

export interface Project {
  id: number
  client_id: number
  code: string
  name: string
  branch_id: number
  start_date: string | null
  is_active: boolean
  sites: Site[]
}

export interface ClientDetail extends Client { projects: Project[] }

export type ItemCategory = 'standard' | 'ledger' | 'transom' | 'jack' | 'plank' | 'brace' | 'accessory' | 'other'

export interface Item {
  id: number
  code: string
  name: string
  category: ItemCategory
  size_m: string | null
  unit: string
  weight_kg: string | null
  hsn_sac: string | null
  replacement_cost: string
  is_active: boolean
}

export interface RateLine { item_id: number; rate_per_day: string; rate_per_month: string | null }

export interface RateCard {
  id: number
  name: string
  client_id: number | null
  project_id: number | null
  valid_from: string
  valid_to: string | null
  min_days: number
  grace_days: number
  is_active: boolean
  lines: RateLine[]
}

export type LeadStatus = 'new' | 'contacted' | 'quoted' | 'won' | 'lost'

export interface FollowUp {
  id: number
  at: string
  by_user_id: number
  channel: string
  note: string
  next_follow_up_at: string | null
}

export interface Lead {
  id: number
  company_name: string
  contact_name: string | null
  phone: string | null
  email: string | null
  city: string | null
  source: string | null
  requirement: string | null
  est_value: string | null
  status: LeadStatus
  lost_reason: string | null
  branch_id: number
  assigned_to: number | null
  created_by: number
  next_follow_up_at: string | null
  converted_client_id: number | null
  created_at: string
}

export interface LeadDetail extends Lead { follow_ups: FollowUp[] }

export interface StockWarehouse {
  id: number
  code: string
  name: string
  branch_id: number
  mine: boolean
}

export interface StockMeta {
  statuses: string[]
  transitions: { from: string; to: string; label: string }[]
  write_off_from: string[]
}

export type StockSummaryRow = {
  item_id: number
  item_code: string
  item_name: string
  category: string
  total: number
} & Record<string, number | string>

export interface StockLocationRow {
  location_type: 'warehouse' | 'site' | 'transit'
  location_id: number
  location_name: string
  item_id: number
  item_code: string
  item_name: string
  status: string
  qty: number
}

export interface StockMovement {
  id: number
  ref_no: string
  kind: string
  warehouse_id: number | null
  reason: string | null
  note: string | null
  source_type: string | null
  source_id: number | null
  created_by: number
  created_at: string
  entries: { location_type: string; location_id: number; item_id: number; status: string; qty: number }[]
}

export interface StockTransfer {
  id: number
  ref_no: string
  from_warehouse_id: number
  to_warehouse_id: number
  status: 'in_transit' | 'received'
  vehicle_no: string | null
  note: string | null
  sent_by: number
  sent_at: string
  received_by: number | null
  received_at: string | null
  lines: { item_id: number; qty_sent: number; qty_received: number | null; qty_damaged: number | null; qty_missing: number | null }[]
}

export interface StockCheck {
  id: number
  ref_no: string
  warehouse_id: number
  note: string | null
  counted_by: number
  counted_at: string
  lines: { item_id: number; system_qty: number; counted_qty: number; variance: number }[]
}

export interface OpeningPreview {
  ok: boolean
  committed: boolean
  errors: string[]
  rows: { row: number; warehouse_code: string; item_code: string; item_name?: string; errors: string[]; qty: Record<string, number> }[]
  totals?: Record<string, number>
  movements?: string[]
}

export interface DispatchRow {
  id: number
  challan_no: string
  request_id: number
  request_ref: string
  warehouse_id: number
  site_id: number
  site_name: string
  status: 'in_transit' | 'received'
  vehicle_no: string | null
  driver_name: string | null
  driver_phone: string | null
  note: string | null
  dispatched_by: number
  dispatched_at: string
  received_by: number | null
  received_at: string | null
  receiver_name: string | null
  receipt_note: string | null
  lines: { item_id: number; qty: number; qty_received: number | null; qty_short: number | null }[]
}

export interface MaterialRequest {
  id: number
  ref_no: string
  client_id: number
  project_id: number
  site_id: number
  branch_id: number
  warehouse_id: number
  status: 'submitted' | 'approved' | 'rejected' | 'cancelled' | 'part_dispatched' | 'dispatched' | 'closed'
  version: number
  required_on: string
  duration_days: number
  transport_charge: string
  est_rent: string
  est_taxable: string
  est_gst: string
  est_total: string
  note: string | null
  created_by: number
  created_at: string
  approved_by: number | null
  approved_at: string | null
  decision_note: string | null
  client_name: string
  site_name: string
  warehouse_code: string
  lines: { item_id: number; qty_requested: number; qty_approved: number | null; qty_dispatched: number; rate_per_day: string }[]
  dispatches: DispatchRow[]
}

export interface AvailabilityRow {
  item_id: number
  need: number
  available: number | null
  short: number | null
  elsewhere: { warehouse_id: number; code: string; available: number }[]
}

export interface RequestDetail extends MaterialRequest {
  availability: AvailabilityRow[]
  client: { id: number; code: string; name: string; credit_status: string }
  can_approve: boolean
  my_approval_limit: string | null
}

export interface RequestEstimate {
  lines: { item_id: number; qty: number; rate_per_day: string; days: number; amount: string }[]
  rent: string
  transport: string
  taxable: string
  cgst: string
  sgst: string
  igst: string
  gst: string
  total: string
  missing_rates: number[]
  availability: AvailabilityRow[]
  client: { id: number; name: string; credit_status: string }
}

export interface SiteRow {
  id: number
  code: string
  name: string
  project_id: number
  project_name: string
  client_id: number
  client_name: string
  state_code: string
}
