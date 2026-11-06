import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Form, Input, Modal, Select, Table } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { api, post } from '../api/client'
import type { Branch, Warehouse } from '../api/types'
import { useAuth } from '../auth/AuthContext'

export default function BranchesPage() {
  const { can } = useAuth()
  const { message } = App.useApp()
  const qc = useQueryClient()
  const [modal, setModal] = useState<'branch' | 'warehouse' | null>(null)
  const [form] = Form.useForm()
  const branches = useQuery({ queryKey: ['branches'], queryFn: () => api<Branch[]>('/branches') })
  const warehouses = useQuery({ queryKey: ['warehouses'], queryFn: () => api<Warehouse[]>('/warehouses') })

  const save = useMutation({
    mutationFn: (v: Record<string, unknown>) => post(modal === 'branch' ? '/branches' : '/warehouses', v),
    onSuccess: () => {
      message.success('Saved')
      setModal(null)
      qc.invalidateQueries({ queryKey: ['branches'] })
      qc.invalidateQueries({ queryKey: ['warehouses'] })
    },
    onError: (e: Error) => message.error(e.message),
  })
  const manage = can('branches.manage')
  const open = (m: 'branch' | 'warehouse') => { form.resetFields(); setModal(m) }

  return (
    <>
      <Card title="Branches" style={{ marginBottom: 16 }}
        extra={manage && <Button icon={<PlusOutlined />} onClick={() => open('branch')}>Add branch</Button>}>
        <Table rowKey="id" size="small" loading={branches.isLoading} dataSource={branches.data} pagination={false} scroll={{ x: 600 }}
          columns={[{ title: 'Code', dataIndex: 'code' }, { title: 'Name', dataIndex: 'name' }, { title: 'City', dataIndex: 'city' },
            { title: 'GSTIN', dataIndex: 'gstin' }]} />
      </Card>
      <Card title="Warehouses" extra={manage && <Button icon={<PlusOutlined />} onClick={() => open('warehouse')}>Add warehouse</Button>}>
        <Table rowKey="id" size="small" loading={warehouses.isLoading} dataSource={warehouses.data} pagination={false} scroll={{ x: 500 }}
          columns={[{ title: 'Code', dataIndex: 'code' }, { title: 'Name', dataIndex: 'name' },
            { title: 'Branch', dataIndex: 'branch_id', render: (id: number) => branches.data?.find((b) => b.id === id)?.name }]} />
      </Card>
      <Modal open={!!modal} title={modal === 'branch' ? 'Add branch' : 'Add warehouse'} onCancel={() => setModal(null)}
        onOk={() => form.submit()} confirmLoading={save.isPending} destroyOnClose>
        <Form form={form} layout="vertical" onFinish={(v) => save.mutate(v)}>
          {modal === 'warehouse' && (
            <Form.Item name="branch_id" label="Branch" rules={[{ required: true }]}>
              <Select options={branches.data?.map((b) => ({ value: b.id, label: b.name }))} />
            </Form.Item>
          )}
          <Form.Item name="code" label="Code" rules={[{ required: true, pattern: /^[A-Z0-9-]+$/, message: 'Capital letters and digits, e.g. CHN' }]}
            normalize={(v: string) => v?.toUpperCase()}><Input /></Form.Item>
          <Form.Item name="name" label="Name" rules={[{ required: true }]}><Input /></Form.Item>
          {modal === 'branch' && <>
            <Form.Item name="city" label="City"><Input /></Form.Item>
            <Form.Item name="gstin" label="GSTIN" normalize={(v: string) => v?.toUpperCase() || undefined}><Input maxLength={15} /></Form.Item>
          </>}
          <Form.Item name="address" label="Address"><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>
    </>
  )
}
