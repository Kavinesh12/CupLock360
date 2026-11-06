import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import { App, Button, Card, Col, DatePicker, Form, Input, InputNumber, Modal, Row, Select, Space, Switch, Table, Tabs, Tag } from 'antd'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import { api, post, put } from '../api/client'
import { useItems } from '../api/hooks'
import type { Client, ClientDetail, Item, RateCard } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { inr } from '../format'

const CATEGORIES = ['standard', 'ledger', 'transom', 'jack', 'plank', 'brace', 'accessory', 'other']

function ItemsTab() {
  const { can } = useAuth()
  const { message } = App.useApp()
  const qc = useQueryClient()
  const items = useItems()
  const [editing, setEditing] = useState<Item | 'new' | null>(null)
  const [cat, setCat] = useState<string | undefined>()
  const [form] = Form.useForm()
  const save = useMutation({
    mutationFn: (v: Partial<Item>) => editing === 'new' ? post('/items', v) : put(`/items/${(editing as Item).id}`, v),
    onSuccess: () => { message.success('Saved'); setEditing(null); qc.invalidateQueries({ queryKey: ['items'] }) },
    onError: (e: Error) => message.error(e.message),
  })
  const open = (it: Item | 'new') => {
    form.resetFields()
    form.setFieldsValue(it === 'new' ? { unit: 'nos', is_active: true, replacement_cost: 0 }
      : { ...it, size_m: it.size_m && Number(it.size_m), weight_kg: it.weight_kg && Number(it.weight_kg), replacement_cost: Number(it.replacement_cost) })
    setEditing(it)
  }
  const data = items.data?.filter((i) => !cat || i.category === cat)
  return (
    <>
      <Space style={{ marginBottom: 16 }} wrap>
        <Select placeholder="All categories" allowClear style={{ width: 180 }} value={cat} onChange={setCat}
          options={CATEGORIES.map((c) => ({ value: c, label: c }))} />
        {can('items.manage') && <Button type="primary" icon={<PlusOutlined />} onClick={() => open('new')}>Add item</Button>}
      </Space>
      <Table rowKey="id" size="small" loading={items.isLoading} dataSource={data} scroll={{ x: 800 }}
        onRow={(it) => ({ onClick: () => can('items.manage') && open(it), style: { cursor: can('items.manage') ? 'pointer' : undefined } })}
        columns={[
          { title: 'Code', dataIndex: 'code' },
          { title: 'Name', dataIndex: 'name' },
          { title: 'Category', dataIndex: 'category', render: (c: string) => <Tag>{c}</Tag> },
          { title: 'Size (m)', dataIndex: 'size_m', align: 'right', render: (v) => v && Number(v) },
          { title: 'Weight (kg)', dataIndex: 'weight_kg', align: 'right', render: (v) => v && Number(v) },
          { title: 'HSN/SAC', dataIndex: 'hsn_sac' },
          { title: 'Replacement cost', dataIndex: 'replacement_cost', align: 'right', render: inr },
          { title: '', dataIndex: 'is_active', render: (a: boolean) => !a && <Tag>Inactive</Tag> },
        ]} />
      <Modal open={!!editing} title={editing === 'new' ? 'Add item' : 'Edit item'} onCancel={() => setEditing(null)}
        onOk={() => form.submit()} confirmLoading={save.isPending} forceRender>
        <Form form={form} name="form_itemspage" layout="vertical" onFinish={(v) => save.mutate(v)}>
          <Row gutter={12}>
            <Col span={12}><Form.Item name="code" label="Code" normalize={(v: string) => v?.toUpperCase()}
              rules={[{ required: true, pattern: /^[A-Z0-9.\-/]+$/, message: 'e.g. STD-3.0' }]}><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="category" label="Category" rules={[{ required: true }]}>
              <Select options={CATEGORIES.map((c) => ({ value: c, label: c }))} /></Form.Item></Col>
            <Col span={24}><Form.Item name="name" label="Name" rules={[{ required: true, min: 2 }]}><Input placeholder="Cuplock standard 3.0 m" /></Form.Item></Col>
            <Col span={8}><Form.Item name="size_m" label="Size (m)"><InputNumber min={0} step={0.5} style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={8}><Form.Item name="weight_kg" label="Weight (kg)"><InputNumber min={0} style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={8}><Form.Item name="unit" label="Unit"><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="hsn_sac" label="HSN/SAC" rules={[{ pattern: /^\d{4,8}$/, message: '4–8 digits' }]}><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="replacement_cost" label="Replacement cost (₹)" extra="Charged for lost or scrapped units">
              <InputNumber min={0} style={{ width: '100%' }} /></Form.Item></Col>
            {editing !== 'new' && <Col span={24}><Form.Item name="is_active" label="Active" valuePropName="checked"><Switch /></Form.Item></Col>}
          </Row>
        </Form>
      </Modal>
    </>
  )
}

function RateCardsTab() {
  const { can } = useAuth()
  const { message } = App.useApp()
  const qc = useQueryClient()
  const items = useItems()
  const cards = useQuery({ queryKey: ['rate-cards'], queryFn: () => api<RateCard[]>('/rate-cards') })
  const clients = useQuery({ queryKey: ['clients', '', undefined], queryFn: () => api<Client[]>('/clients') })
  const [editing, setEditing] = useState<RateCard | 'new' | null>(null)
  const [form] = Form.useForm()
  const clientId = Form.useWatch('client_id', form)
  const clientDetail = useQuery({ queryKey: ['client', String(clientId)], queryFn: () => api<ClientDetail>(`/clients/${clientId}`), enabled: !!clientId })
  const itemName = (id: number) => items.data?.find((i) => i.id === id)?.code ?? id
  const clientName = (id: number | null) => (id ? clients.data?.find((c) => c.id === id)?.name : null)

  const save = useMutation({
    mutationFn: (v: Record<string, unknown> & { period: [dayjs.Dayjs, dayjs.Dayjs | null] }) => {
      const { period, ...rest } = v
      const body = { ...rest, valid_from: period[0].format('YYYY-MM-DD'), valid_to: period[1]?.format('YYYY-MM-DD') ?? null }
      return editing === 'new' ? post('/rate-cards', body) : put(`/rate-cards/${(editing as RateCard).id}`, body)
    },
    onSuccess: () => { message.success('Rate card saved'); setEditing(null); qc.invalidateQueries({ queryKey: ['rate-cards'] }) },
    onError: (e: Error) => message.error(e.message),
  })
  const open = (rc: RateCard | 'new') => {
    form.resetFields()
    form.setFieldsValue(rc === 'new'
      ? { min_days: 30, grace_days: 0, is_active: true, period: [dayjs(), null], lines: [{}] }
      : { ...rc, period: [dayjs(rc.valid_from), rc.valid_to ? dayjs(rc.valid_to) : null],
          lines: rc.lines.map((l) => ({ ...l, rate_per_day: Number(l.rate_per_day), rate_per_month: l.rate_per_month && Number(l.rate_per_month) })) })
    setEditing(rc)
  }

  return (
    <>
      {can('items.manage') && <Button type="primary" icon={<PlusOutlined />} onClick={() => open('new')} style={{ marginBottom: 16 }}>Add rate card</Button>}
      <Table rowKey="id" size="small" loading={cards.isLoading} dataSource={cards.data} scroll={{ x: 800 }}
        onRow={(rc) => ({ onClick: () => can('items.manage') && open(rc), style: { cursor: 'pointer' } })}
        expandable={{ expandedRowRender: (rc) => (
          <Table rowKey="item_id" size="small" pagination={false} dataSource={rc.lines}
            columns={[{ title: 'Item', dataIndex: 'item_id', render: itemName },
              { title: '₹ / day', dataIndex: 'rate_per_day', align: 'right' },
              { title: '₹ / month', dataIndex: 'rate_per_month', align: 'right' }]} />) }}
        columns={[
          { title: 'Name', dataIndex: 'name' },
          { title: 'Applies to', key: 'to', render: (_: unknown, rc: RateCard) => rc.project_id ? <Tag color="purple">Project of {clientName(rc.client_id)}</Tag>
            : rc.client_id ? <Tag color="blue">{clientName(rc.client_id)}</Tag> : <Tag>Standard</Tag> },
          { title: 'Valid', key: 'v', render: (_: unknown, rc: RateCard) => `${rc.valid_from} → ${rc.valid_to ?? 'open'}` },
          { title: 'Min days', dataIndex: 'min_days', align: 'right' },
          { title: 'Grace', dataIndex: 'grace_days', align: 'right' },
          { title: 'Items', key: 'n', align: 'right', render: (_: unknown, rc: RateCard) => rc.lines.length },
          { title: '', dataIndex: 'is_active', render: (a: boolean) => !a && <Tag>Inactive</Tag> },
        ]} />
      <Modal open={!!editing} width={760} title={editing === 'new' ? 'Add rate card' : 'Edit rate card'} onCancel={() => setEditing(null)}
        onOk={() => form.submit()} confirmLoading={save.isPending} forceRender>
        <Form form={form} name="form_ratecard" layout="vertical" onFinish={(v) => save.mutate(v)}>
          <Row gutter={12}>
            <Col xs={24} md={12}><Form.Item name="name" label="Name" rules={[{ required: true, min: 2 }]}><Input placeholder="Standard rates 2026-27" /></Form.Item></Col>
            <Col xs={24} md={12}><Form.Item name="period" label="Valid from → to (leave end open)" rules={[{ required: true }]}>
              <DatePicker.RangePicker allowEmpty={[false, true]} style={{ width: '100%' }} /></Form.Item></Col>
            <Col xs={24} md={12}><Form.Item name="client_id" label="Client (empty = standard card)">
              <Select allowClear showSearch optionFilterProp="label" onChange={() => form.setFieldValue('project_id', null)}
                options={clients.data?.map((c) => ({ value: c.id, label: `${c.code} · ${c.name}` }))} /></Form.Item></Col>
            <Col xs={24} md={12}><Form.Item name="project_id" label="Project (optional)">
              <Select allowClear disabled={!clientId} options={clientDetail.data?.projects.map((p) => ({ value: p.id, label: p.name }))} /></Form.Item></Col>
            <Col span={8}><Form.Item name="min_days" label="Minimum days"><InputNumber min={0} style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={8}><Form.Item name="grace_days" label="Grace days"><InputNumber min={0} style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={8}><Form.Item name="is_active" label="Active" valuePropName="checked"><Switch /></Form.Item></Col>
          </Row>
          <Form.List name="lines">
            {(fields, { add, remove }) => (
              <>
                {fields.map((f) => (
                  <Row key={f.key} gutter={8} align="top">
                    <Col xs={24} md={11}><Form.Item name={[f.name, 'item_id']} rules={[{ required: true, message: 'Item' }]}>
                      <Select placeholder="Item" showSearch optionFilterProp="label"
                        options={items.data?.filter((i) => i.is_active).map((i) => ({ value: i.id, label: `${i.code} · ${i.name}` }))} /></Form.Item></Col>
                    <Col xs={10} md={5}><Form.Item name={[f.name, 'rate_per_day']} rules={[{ required: true, message: 'Rate' }]}>
                      <InputNumber placeholder="₹/day" min={0.01} step={0.25} style={{ width: '100%' }} /></Form.Item></Col>
                    <Col xs={10} md={6}><Form.Item name={[f.name, 'rate_per_month']}>
                      <InputNumber placeholder="₹/month (optional)" min={0.01} style={{ width: '100%' }} /></Form.Item></Col>
                    <Col xs={4} md={2}><Button icon={<DeleteOutlined />} onClick={() => remove(f.name)} /></Col>
                  </Row>
                ))}
                <Button type="dashed" block icon={<PlusOutlined />} onClick={() => add()}>Add item rate</Button>
              </>
            )}
          </Form.List>
        </Form>
      </Modal>
    </>
  )
}

export default function ItemsPage() {
  return (
    <Card title="Items & rates">
      <Tabs items={[{ key: 'items', label: 'Item master', children: <ItemsTab /> },
        { key: 'rates', label: 'Rate cards', children: <RateCardsTab /> }]} />
    </Card>
  )
}
