import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Switch, Table, Tag } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { api, patch, post } from '../api/client'
import type { Branch, Role, UserRow } from '../api/types'
import { useAuth } from '../auth/AuthContext'

interface FormValues {
  username: string
  full_name: string
  phone?: string
  email?: string
  password?: string
  roles: string[]
  branch_ids?: number[]
  approval_limit?: number | null
  is_active?: boolean
}

export default function UsersPage() {
  const { can } = useAuth()
  const { message } = App.useApp()
  const qc = useQueryClient()
  const [q, setQ] = useState('')
  const [editing, setEditing] = useState<UserRow | 'new' | null>(null)
  const [form] = Form.useForm<FormValues>()

  const users = useQuery({ queryKey: ['users', q], queryFn: () => api<UserRow[]>(`/users${q ? `?q=${encodeURIComponent(q)}` : ''}`) })
  const roles = useQuery({ queryKey: ['roles'], queryFn: () => api<Role[]>('/roles') })
  const branches = useQuery({ queryKey: ['branches'], queryFn: () => api<Branch[]>('/branches'), enabled: can('branches.view') })
  const roleName = (code: string) => roles.data?.find((r) => r.code === code)?.name ?? code

  const save = useMutation({
    mutationFn: async (v: FormValues) => {
      const scopes = (v.branch_ids ?? []).map((id) => ({ type: 'branch', id }))
      const body = { ...v, branch_ids: undefined, scopes, phone: v.phone || null, email: v.email || null,
        approval_limit: v.approval_limit ?? null }
      if (editing === 'new') return post('/users', body)
      if (!body.password) delete body.password
      const { username: _u, ...rest } = body
      return patch(`/users/${(editing as UserRow).id}`, rest)
    },
    onSuccess: () => { message.success('Saved'); setEditing(null); qc.invalidateQueries({ queryKey: ['users'] }) },
    onError: (e: Error) => message.error(e.message),
  })

  const revoke = useMutation({
    mutationFn: (id: number) => post(`/users/${id}/revoke-sessions`),
    onSuccess: () => message.success('All sessions for this user were signed out'),
    onError: (e: Error) => message.error(e.message),
  })

  const open = (u: UserRow | 'new') => {
    setEditing(u)
    form.resetFields()
    if (u !== 'new') {
      form.setFieldsValue({
        ...u, phone: u.phone ?? undefined, email: u.email ?? undefined,
        approval_limit: u.approval_limit ? Number(u.approval_limit) : null,
        branch_ids: u.scopes.filter((s) => s.type === 'branch').map((s) => s.id),
      })
    } else form.setFieldsValue({ is_active: true })
  }

  return (
    <Card title="Users" extra={can('users.manage') && <Button type="primary" icon={<PlusOutlined />} onClick={() => open('new')}>Add user</Button>}>
      <Input.Search placeholder="Search name, username or phone" allowClear onSearch={setQ} style={{ maxWidth: 320, marginBottom: 16 }} />
      <Table rowKey="id" loading={users.isLoading} dataSource={users.data} scroll={{ x: 800 }}
        columns={[
          { title: 'Name', dataIndex: 'full_name' },
          { title: 'Username', dataIndex: 'username' },
          { title: 'Phone', dataIndex: 'phone' },
          { title: 'Roles', dataIndex: 'roles', render: (r: string[]) => r.map((c) => <Tag key={c}>{roleName(c)}</Tag>) },
          { title: 'Branches', dataIndex: 'scopes', render: (s: UserRow['scopes']) => {
            const b = s.filter((x) => x.type === 'branch')
            return b.length ? b.map((x) => <Tag key={x.id}>{branches.data?.find((br) => br.id === x.id)?.code ?? x.id}</Tag>) : 'All'
          } },
          { title: 'Status', dataIndex: 'is_active', render: (a: boolean) => a ? <Tag color="green">Active</Tag> : <Tag>Disabled</Tag> },
          ...(can('users.manage') ? [{
            title: '', key: 'act', render: (_: unknown, u: UserRow) => (
              <Space>
                <Button size="small" onClick={() => open(u)}>Edit</Button>
                <Popconfirm title="Sign this user out everywhere?" onConfirm={() => revoke.mutate(u.id)}>
                  <Button size="small" danger>Revoke sessions</Button>
                </Popconfirm>
              </Space>
            ),
          }] : []),
        ]} />
      <Modal open={!!editing} title={editing === 'new' ? 'Add user' : 'Edit user'} onCancel={() => setEditing(null)}
        onOk={() => form.submit()} confirmLoading={save.isPending} forceRender>
        <Form form={form} name="form_userspage" layout="vertical" onFinish={(v) => save.mutate(v)}>
          <Form.Item name="username" label="Username" rules={[{ required: true, min: 3, pattern: /^[a-zA-Z0-9._-]+$/ }]}>
            <Input disabled={editing !== 'new'} />
          </Form.Item>
          <Form.Item name="full_name" label="Full name" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="phone" label="Mobile" rules={[{ pattern: /^[6-9]\d{9}$/, message: '10-digit Indian mobile' }]}><Input /></Form.Item>
          <Form.Item name="email" label="Email" rules={[{ type: 'email' }]}><Input /></Form.Item>
          <Form.Item name="password" label={editing === 'new' ? 'Password' : 'New password (leave blank to keep)'}
            rules={[{ required: editing === 'new', min: 8 }]}><Input.Password autoComplete="new-password" /></Form.Item>
          <Form.Item name="roles" label="Roles" rules={[{ required: true }]}>
            <Select mode="multiple" options={roles.data?.map((r) => ({ value: r.code, label: r.name }))} />
          </Form.Item>
          <Form.Item name="branch_ids" label="Limit to branches" extra="Leave empty for access to all branches">
            <Select mode="multiple" allowClear options={branches.data?.map((b) => ({ value: b.id, label: `${b.code} · ${b.name}` }))} />
          </Form.Item>
          <Form.Item name="approval_limit" label="Approval limit (₹)" extra="Highest value this user can approve. Empty = cannot approve.">
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          {editing !== 'new' && <Form.Item name="is_active" label="Active" valuePropName="checked"><Switch /></Form.Item>}
        </Form>
      </Modal>
    </Card>
  )
}
