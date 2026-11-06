import type { ReactNode } from 'react'
import {
  AuditOutlined, BankOutlined, DashboardOutlined, DollarOutlined, HomeOutlined, InboxOutlined,
  SafetyCertificateOutlined, SendOutlined, ShopOutlined, TeamOutlined, UserOutlined, BarChartOutlined,
  AppstoreOutlined, AimOutlined,
} from '@ant-design/icons'

export interface MenuEntry {
  key: string
  label: string
  icon: ReactNode
  perm?: string
  group: 'main' | 'admin'
  day?: number // module arrives on this day of the build
}

export const MENU: MenuEntry[] = [
  { key: '/', label: 'Home', icon: <HomeOutlined />, group: 'main' },
  { key: '/dashboard', label: 'Owner dashboard', icon: <DashboardOutlined />, perm: 'dashboard.view', group: 'main', day: 6 },
  { key: '/leads', label: 'Leads', icon: <AimOutlined />, perm: 'leads.view', group: 'main' },
  { key: '/clients', label: 'Clients & sites', icon: <ShopOutlined />, perm: 'clients.view', group: 'main' },
  { key: '/items', label: 'Items & rates', icon: <AppstoreOutlined />, perm: 'items.view', group: 'main' },
  { key: '/stock', label: 'Stock', icon: <InboxOutlined />, perm: 'stock.view', group: 'main' },
  { key: '/requests', label: 'Requests & dispatch', icon: <SendOutlined />, perm: 'requests.view', group: 'main' },
  { key: '/billing', label: 'Billing & dues', icon: <DollarOutlined />, perm: 'billing.view', group: 'main', day: 5 },
  { key: '/reports', label: 'Reports', icon: <BarChartOutlined />, perm: 'reports.view', group: 'main', day: 6 },
  { key: '/branches', label: 'Branches & warehouses', icon: <BankOutlined />, perm: 'branches.view', group: 'admin' },
  { key: '/users', label: 'Users', icon: <UserOutlined />, perm: 'users.view', group: 'admin' },
  { key: '/roles', label: 'Roles & permissions', icon: <TeamOutlined />, perm: 'roles.view', group: 'admin' },
  { key: '/audit', label: 'Audit trail', icon: <AuditOutlined />, perm: 'audit.view', group: 'admin' },
]

export const ADMIN_ICON = <SafetyCertificateOutlined />
