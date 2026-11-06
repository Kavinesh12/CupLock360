import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Alert, Button, Card, Input, Space, Table, Typography } from 'antd'
import { api } from '../api/client'
import type { AuditRow } from '../api/types'

export default function AuditPage() {
  const [action, setAction] = useState('')
  const rows = useQuery({ queryKey: ['audit', action], queryFn: () => api<AuditRow[]>(`/audit?limit=200${action ? `&action=${encodeURIComponent(action)}` : ''}`) })
  const verify = useQuery({ queryKey: ['audit-verify'], queryFn: () => api<{ ok: boolean; first_broken_id: number | null }>('/audit/verify'), enabled: false })

  return (
    <Card title="Audit trail" extra={<Button onClick={() => verify.refetch()} loading={verify.isFetching}>Verify chain</Button>}>
      {verify.data && (verify.data.ok
        ? <Alert type="success" showIcon message="Audit chain intact: no row has been altered or removed." style={{ marginBottom: 16 }} />
        : <Alert type="error" showIcon message={`Audit chain broken at row ${verify.data.first_broken_id}.`} style={{ marginBottom: 16 }} />)}
      <Space style={{ marginBottom: 16 }}>
        <Input.Search placeholder="Filter by action, e.g. auth." allowClear onSearch={setAction} />
      </Space>
      <Table rowKey="id" size="small" loading={rows.isLoading} dataSource={rows.data} scroll={{ x: 800 }}
        columns={[
          { title: '#', dataIndex: 'id', width: 70 },
          { title: 'When', dataIndex: 'at', render: (a: string) => new Date(a).toLocaleString('en-IN') },
          { title: 'User', dataIndex: 'user_id' },
          { title: 'Action', dataIndex: 'action', render: (a: string) => <Typography.Text code>{a}</Typography.Text> },
          { title: 'Entity', render: (_: unknown, r: AuditRow) => r.entity ? `${r.entity} ${r.entity_id ?? ''}` : '' },
          { title: 'IP', dataIndex: 'ip' },
        ]}
        expandable={{ expandedRowRender: (r) => <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{JSON.stringify(r.data, null, 2)}</pre>,
          rowExpandable: (r) => !!r.data }} />
    </Card>
  )
}
