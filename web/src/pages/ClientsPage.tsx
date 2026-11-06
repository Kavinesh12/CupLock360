import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Input, Select, Space, Table, Tag } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { api, post } from '../api/client'
import { useBranches } from '../api/hooks'
import type { Client } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { inr } from '../format'
import ClientForm, { creditTag } from '../components/ClientForm'

export default function ClientsPage() {
  const { can } = useAuth()
  const nav = useNavigate()
  const qc = useQueryClient()
  const { message } = App.useApp()
  const [q, setQ] = useState('')
  const [branchId, setBranchId] = useState<number | undefined>()
  const [open, setOpen] = useState(false)
  const branches = useBranches()
  const params = new URLSearchParams()
  if (q) params.set('q', q)
  if (branchId) params.set('branch_id', String(branchId))
  const clients = useQuery({ queryKey: ['clients', q, branchId], queryFn: () => api<Client[]>(`/clients?${params}`) })

  const create = useMutation({
    mutationFn: (v: Partial<Client>) => post<Client>('/clients', v),
    onSuccess: (c) => {
      message.success(`Client ${c.code} created`)
      setOpen(false)
      qc.invalidateQueries({ queryKey: ['clients'] })
      nav(`/clients/${c.id}`)
    },
    onError: (e: Error) => message.error(e.message),
  })

  return (
    <Card title="Clients" extra={can('clients.manage') && <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>Add client</Button>}>
      <Space wrap style={{ marginBottom: 16 }}>
        <Input.Search placeholder="Name, code, GSTIN or phone" allowClear onSearch={setQ} style={{ width: 280 }} />
        <Select placeholder="All branches" allowClear style={{ width: 200 }} value={branchId} onChange={setBranchId}
          options={branches.data?.map((b) => ({ value: b.id, label: b.name }))} />
      </Space>
      <Table rowKey="id" loading={clients.isLoading} dataSource={clients.data} scroll={{ x: 900 }}
        onRow={(c) => ({ onClick: () => nav(`/clients/${c.id}`), style: { cursor: 'pointer' } })}
        columns={[
          { title: 'Code', dataIndex: 'code', width: 100 },
          { title: 'Name', dataIndex: 'name' },
          { title: 'Branch', dataIndex: 'branch_id', render: (id: number) => branches.data?.find((b) => b.id === id)?.code },
          { title: 'GSTIN', dataIndex: 'gstin' },
          { title: 'Phone', dataIndex: 'phone' },
          { title: 'Credit limit', dataIndex: 'credit_limit', align: 'right', render: inr },
          { title: 'Credit', dataIndex: 'credit_status', render: creditTag },
          { title: '', dataIndex: 'is_active', render: (a: boolean) => !a && <Tag>Inactive</Tag> },
        ]} />
      <ClientForm open={open} onCancel={() => setOpen(false)} onSubmit={(v) => create.mutate(v)} saving={create.isPending} />
    </Card>
  )
}
