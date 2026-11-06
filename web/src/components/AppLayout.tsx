import { useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { Avatar, Button, Dropdown, Grid, Layout, Menu, Space, Typography } from 'antd'
import { LogoutOutlined, MenuOutlined } from '@ant-design/icons'
import { useAuth } from '../auth/AuthContext'
import { ADMIN_ICON, MENU } from './menu'

const { Sider, Header, Content } = Layout

export default function AppLayout() {
  const { me, can, logout } = useAuth()
  const nav = useNavigate()
  const loc = useLocation()
  const screens = Grid.useBreakpoint()
  const [collapsed, setCollapsed] = useState(false)

  const visible = MENU.filter((m) => !m.perm || can(m.perm))
  const toItem = (m: (typeof MENU)[number]) => ({ key: m.key, icon: m.icon, label: m.label })
  const admin = visible.filter((m) => m.group === 'admin')
  const items = [
    ...visible.filter((m) => m.group === 'main').map(toItem),
    ...(admin.length ? [{ key: 'admin', icon: ADMIN_ICON, label: 'Administration', children: admin.map(toItem) }] : []),
  ]
  const selected = '/' + (loc.pathname.split('/')[1] ?? '')

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider breakpoint="lg" collapsedWidth={screens.lg ? 80 : 0} collapsed={collapsed}
        onCollapse={setCollapsed} trigger={null} width={232} theme="dark">
        <div style={{ color: '#fff', padding: '18px 20px', fontWeight: 700, fontSize: 18, whiteSpace: 'nowrap' }}>
          {collapsed ? 'C360' : 'CUPLOCK 360°'}
        </div>
        <Menu theme="dark" mode="inline" selectedKeys={[selected]} defaultOpenKeys={['admin']} items={items}
          onClick={(e) => { nav(e.key); if (!screens.lg) setCollapsed(true) }} />
      </Sider>
      <Layout>
        <Header style={{ background: '#fff', padding: '0 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Button type="text" icon={<MenuOutlined />} onClick={() => setCollapsed(!collapsed)} />
          <Dropdown menu={{ items: [{ key: 'logout', icon: <LogoutOutlined />, label: 'Log out', onClick: () => logout() }] }}>
            <Space style={{ cursor: 'pointer' }}>
              <Avatar style={{ background: '#c2410c' }}>{me?.full_name[0]}</Avatar>
              {screens.sm && <Typography.Text>{me?.full_name}</Typography.Text>}
            </Space>
          </Dropdown>
        </Header>
        <Content style={{ margin: 16 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
