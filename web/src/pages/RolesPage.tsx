import { useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Card, Checkbox, Table, Tooltip, Typography } from 'antd'
import { api, put } from '../api/client'
import type { Permission, Role } from '../api/types'
import { useAuth } from '../auth/AuthContext'

export default function RolesPage() {
  const { can } = useAuth()
  const { message } = App.useApp()
  const qc = useQueryClient()
  const roles = useQuery({ queryKey: ['roles'], queryFn: () => api<Role[]>('/roles') })
  const perms = useQuery({ queryKey: ['permissions'], queryFn: () => api<Permission[]>('/permissions') })
  const editable = can('roles.manage')

  const save = useMutation({
    mutationFn: ({ role, permissions }: { role: Role; permissions: string[] }) =>
      put<Role>(`/roles/${role.id}/permissions`, { permissions }),
    onSuccess: () => { message.success('Role updated'); qc.invalidateQueries({ queryKey: ['roles'] }) },
    onError: (e: Error) => message.error(e.message),
  })

  const toggle = (role: Role, code: string, on: boolean) => {
    const next = on ? [...role.permissions, code] : role.permissions.filter((p) => p !== code)
    save.mutate({ role, permissions: next })
  }

  const columns = useMemo(() => [
    { title: 'Permission', dataIndex: 'code', fixed: 'left' as const, width: 220,
      render: (c: string, p: Permission) => <Tooltip title={p.description}><Typography.Text code>{c}</Typography.Text></Tooltip> },
    ...(roles.data ?? []).map((r) => ({
      title: <Tooltip title={r.description}>{r.name}<br /><Typography.Text type="secondary">{r.user_count} users</Typography.Text></Tooltip>,
      key: r.code, width: 120, align: 'center' as const,
      render: (_: unknown, p: Permission) => (
        <Checkbox checked={r.permissions.includes(p.code)} disabled={!editable || r.code === 'owner' || save.isPending}
          onChange={(e) => toggle(r, p.code, e.target.checked)} />
      ),
    })),
  ], [roles.data, editable, save.isPending])

  return (
    <Card title="Roles & permissions">
      <Typography.Paragraph type="secondary">
        Permissions are enforced by the API. Changing a role here takes effect on each user's next request.
      </Typography.Paragraph>
      <Table rowKey="code" size="small" pagination={false} loading={roles.isLoading || perms.isLoading}
        dataSource={perms.data} columns={columns} scroll={{ x: 220 + 120 * (roles.data?.length ?? 0) }} />
    </Card>
  )
}
