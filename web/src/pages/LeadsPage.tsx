import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import {
  App, Badge, Button, Card, Col, DatePicker, Descriptions, Drawer, Form, Input, InputNumber, Modal, Radio, Row, Select,
  Space, Table, Tag, Timeline, Typography,
} from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { api, patch, post } from '../api/client'
import { useBranches, useUserLookup } from '../api/hooks'
import type { Client, Lead, LeadDetail, LeadStatus } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { dt, inr } from '../format'

const STATUS_COLOR: Record<LeadStatus, string> = { new: 'blue', contacted: 'cyan', quoted: 'purple', won: 'green', lost: 'default' }
const SOURCES = ['Referral', 'Walk-in', 'Phone call', 'Website', 'Site visit', 'Existing client', 'Other']
const CHANNELS = ['call', 'visit', 'whatsapp', 'email', 'meeting']

const isOverdue = (l: Lead) => !!l.next_follow_up_at && ['new', 'contacted', 'quoted'].includes(l.status)
  && dayjs(l.next_follow_up_at).isBefore(dayjs())

export default function LeadsPage() {
  const { can } = useAuth()
  const { message } = App.useApp()
  const qc = useQueryClient()
  const nav = useNavigate()
  const branches = useBranches()
  const users = useUserLookup()
  const [view, setView] = useState<'open' | 'due' | 'won' | 'lost' | 'all'>('open')
  const [q, setQ] = useState('')
  const [creating, setCreating] = useState(false)
  const [selected, setSelected] = useState<number | null>(null)
  const [converting, setConverting] = useState(false)
  const [lostOpen, setLostOpen] = useState(false)
  const [cForm] = Form.useForm()
  const [fForm] = Form.useForm()
  const [vForm] = Form.useForm()
  const [lForm] = Form.useForm()
  const manage = can('leads.manage')

  const params = new URLSearchParams()
  if (view === 'due') params.set('due', 'true')
  else if (view !== 'all') params.set('status', view)
  if (q) params.set('q', q)
  const leads = useQuery({ queryKey: ['leads', view, q], queryFn: () => api<Lead[]>(`/leads?${params}`) })
  const detail = useQuery({ queryKey: ['lead', selected], queryFn: () => api<LeadDetail>(`/leads/${selected}`), enabled: !!selected })
  const clients = useQuery({ queryKey: ['clients', '', undefined], queryFn: () => api<Client[]>('/clients'), enabled: converting })
  const userName = (id: number | null) => users.data?.find((u) => u.id === id)?.full_name ?? ''
  const refresh = () => { qc.invalidateQueries({ queryKey: ['leads'] }); qc.invalidateQueries({ queryKey: ['lead', selected] }) }
  const onError = (e: Error) => message.error(e.message)

  const create = useMutation({ onError,
    mutationFn: (v: Record<string, unknown>) => post<Lead>('/leads', v),
    onSuccess: (l) => { message.success('Lead added'); setCreating(false); refresh(); setSelected(l.id) } })
  const followUp = useMutation({ onError,
    mutationFn: (v: { channel: string; note: string; next?: dayjs.Dayjs; status?: string }) =>
      post(`/leads/${selected}/follow-ups`, { channel: v.channel, note: v.note, status: v.status || undefined,
        next_follow_up_at: v.next?.toISOString() ?? null }),
    onSuccess: () => { message.success('Follow-up saved'); fForm.resetFields(); fForm.setFieldsValue({ channel: 'call' }); refresh() } })
  const markLost = useMutation({ onError,
    mutationFn: (v: { lost_reason: string }) => patch(`/leads/${selected}`, { status: 'lost', lost_reason: v.lost_reason }),
    onSuccess: () => { message.success('Marked lost'); setLostOpen(false); refresh() } })
  const convert = useMutation({ onError,
    mutationFn: (v: Record<string, unknown>) => post<{ client: Client }>(`/leads/${selected}/convert`, v),
    onSuccess: (r) => { message.success(`Converted to client ${r.client.code}`); setConverting(false); refresh(); nav(`/clients/${r.client.id}`) } })

  const lead = detail.data
  const open = lead && ['new', 'contacted', 'quoted'].includes(lead.status)

  return (
    <Card title="Leads & follow-ups" extra={manage && <Button type="primary" icon={<PlusOutlined />} onClick={() => {
      cForm.resetFields(); cForm.setFieldsValue({ branch_id: branches.data?.[0]?.id }); setCreating(true) }}>Add lead</Button>}>
      <Space wrap style={{ marginBottom: 16 }}>
        <Radio.Group value={view} onChange={(e) => setView(e.target.value)} optionType="button" options={[
          { value: 'open', label: 'Open' }, { value: 'due', label: 'Due today' }, { value: 'won', label: 'Won' },
          { value: 'lost', label: 'Lost' }, { value: 'all', label: 'All' }]} />
        <Input.Search placeholder="Company, contact or phone" allowClear onSearch={setQ} style={{ width: 260 }} />
      </Space>
      <Table rowKey="id" loading={leads.isLoading} dataSource={leads.data} scroll={{ x: 900 }}
        onRow={(l) => ({ onClick: () => { setSelected(l.id); fForm.resetFields(); fForm.setFieldsValue({ channel: 'call' }) }, style: { cursor: 'pointer' } })}
        columns={[
          { title: 'Company', dataIndex: 'company_name' },
          { title: 'Contact', key: 'c', render: (_: unknown, l: Lead) => [l.contact_name, l.phone].filter(Boolean).join(' · ') },
          { title: 'City', dataIndex: 'city' },
          { title: 'Est. value', dataIndex: 'est_value', align: 'right', render: inr },
          { title: 'Status', dataIndex: 'status', render: (s: LeadStatus) => <Tag color={STATUS_COLOR[s]}>{s}</Tag> },
          { title: 'Next follow-up', dataIndex: 'next_follow_up_at', render: (v: string | null, l: Lead) =>
            v && <Badge status={isOverdue(l) ? 'error' : 'processing'} text={dt(v)} /> },
          { title: 'Owner', dataIndex: 'assigned_to', render: userName },
        ]} />

      <Drawer open={!!selected} onClose={() => setSelected(null)} width={Math.min(560, window.innerWidth)}
        title={lead && <Space>{lead.company_name}<Tag color={STATUS_COLOR[lead.status]}>{lead.status}</Tag></Space>}
        extra={lead && manage && open && <Space>
          <Button onClick={() => { lForm.resetFields(); setLostOpen(true) }}>Mark lost</Button>
          {can('clients.manage') && <Button type="primary" onClick={() => {
            vForm.resetFields(); vForm.setFieldsValue({ mode: 'new', client_name: lead.company_name, site_city: lead.city }); setConverting(true) }}>Convert to client</Button>}
        </Space>}>
        {lead && <>
          <Descriptions column={1} size="small" style={{ marginBottom: 16 }}>
            <Descriptions.Item label="Contact">{[lead.contact_name, lead.phone, lead.email].filter(Boolean).join(' · ')}</Descriptions.Item>
            <Descriptions.Item label="City">{lead.city}</Descriptions.Item>
            <Descriptions.Item label="Source">{lead.source}</Descriptions.Item>
            <Descriptions.Item label="Requirement">{lead.requirement}</Descriptions.Item>
            <Descriptions.Item label="Est. value">{inr(lead.est_value)}</Descriptions.Item>
            <Descriptions.Item label="Owner">{userName(lead.assigned_to)}</Descriptions.Item>
            {lead.lost_reason && <Descriptions.Item label="Lost reason">{lead.lost_reason}</Descriptions.Item>}
            {lead.converted_client_id && <Descriptions.Item label="Client">
              <Typography.Link onClick={() => nav(`/clients/${lead.converted_client_id}`)}>Open client</Typography.Link></Descriptions.Item>}
          </Descriptions>
          {manage && open && (
            <Card size="small" title="Log a follow-up" style={{ marginBottom: 16 }}>
              <Form form={fForm} name="fForm_leadspage" layout="vertical" onFinish={(v) => followUp.mutate(v)}>
                <Row gutter={8}>
                  <Col span={12}><Form.Item name="channel" label="How"><Select options={CHANNELS.map((c) => ({ value: c, label: c }))} /></Form.Item></Col>
                  <Col span={12}><Form.Item name="status" label="Move to"><Select allowClear placeholder="(no change)"
                    options={['contacted', 'quoted'].map((s) => ({ value: s, label: s }))} /></Form.Item></Col>
                  <Col span={24}><Form.Item name="note" label="What happened" rules={[{ required: true }]}><Input.TextArea rows={2} /></Form.Item></Col>
                  <Col span={24}><Form.Item name="next" label="Next follow-up"><DatePicker showTime={{ format: 'HH:mm' }} format="DD MMM YYYY HH:mm" style={{ width: '100%' }} /></Form.Item></Col>
                </Row>
                <Button type="primary" htmlType="submit" loading={followUp.isPending}>Save follow-up</Button>
              </Form>
            </Card>
          )}
          <Typography.Title level={5}>History</Typography.Title>
          <Timeline items={[
            ...lead.follow_ups.map((f) => ({ children: <>
              <Typography.Text strong>{f.channel}</Typography.Text> · {dt(f.at)} · {userName(f.by_user_id)}
              <div>{f.note}</div>
              {f.next_follow_up_at && <Typography.Text type="secondary">Next: {dt(f.next_follow_up_at)}</Typography.Text>}
            </> })),
            { color: 'gray', children: <>Lead created {dt(lead.created_at)}</> },
          ]} />
        </>}
      </Drawer>

      <Modal open={creating} title="Add lead" onCancel={() => setCreating(false)} onOk={() => cForm.submit()} confirmLoading={create.isPending} forceRender>
        <Form form={cForm} name="cForm_leadspage" layout="vertical" onFinish={(v) => create.mutate({ ...v, next_follow_up_at: v.next_follow_up_at?.toISOString() })}>
          <Form.Item name="company_name" label="Company" rules={[{ required: true, min: 2 }]}><Input /></Form.Item>
          <Row gutter={8}>
            <Col span={12}><Form.Item name="contact_name" label="Contact person"><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="phone" label="Mobile" rules={[{ pattern: /^[6-9]\d{9}$/, message: '10-digit mobile' }]}><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="city" label="City"><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="source" label="Source"><Select allowClear options={SOURCES.map((s) => ({ value: s, label: s }))} /></Form.Item></Col>
            <Col span={12}><Form.Item name="branch_id" label="Branch" rules={[{ required: true }]}>
              <Select options={branches.data?.map((b) => ({ value: b.id, label: b.name }))} /></Form.Item></Col>
            <Col span={12}><Form.Item name="est_value" label="Est. value (₹)"><InputNumber min={0} style={{ width: '100%' }} /></Form.Item></Col>
          </Row>
          <Form.Item name="requirement" label="Requirement"><Input.TextArea rows={2} placeholder="e.g. 1,200 standards and 2,400 ledgers for 3 months" /></Form.Item>
          <Form.Item name="assigned_to" label="Assign to (default: me)">
            <Select allowClear showSearch optionFilterProp="label" options={users.data?.map((u) => ({ value: u.id, label: u.full_name }))} /></Form.Item>
          <Form.Item name="next_follow_up_at" label="First follow-up"><DatePicker showTime={{ format: 'HH:mm' }} format="DD MMM YYYY HH:mm" style={{ width: '100%' }} /></Form.Item>
        </Form>
      </Modal>

      <Modal open={lostOpen} forceRender title="Mark lead lost" onCancel={() => setLostOpen(false)} onOk={() => lForm.submit()} confirmLoading={markLost.isPending}>
        <Form form={lForm} name="lForm_leadspage" layout="vertical" onFinish={(v) => markLost.mutate(v)}>
          <Form.Item name="lost_reason" label="Reason" rules={[{ required: true }]}><Input placeholder="e.g. Price too high, went with competitor" /></Form.Item>
        </Form>
      </Modal>

      <Modal open={converting} title="Convert to client" onCancel={() => setConverting(false)} onOk={() => vForm.submit()} confirmLoading={convert.isPending} forceRender>
        <Form form={vForm} name="vForm_leadspage" layout="vertical" onFinish={(v) => {
          const { mode, ...rest } = v
          convert.mutate(mode === 'new' ? { ...rest, existing_client_id: null } : { ...rest, client_name: null, gstin: null })
        }}>
          <Form.Item name="mode"><Radio.Group options={[{ value: 'new', label: 'New client' }, { value: 'existing', label: 'Existing client' }]} /></Form.Item>
          <Form.Item noStyle shouldUpdate={(a, b) => a.mode !== b.mode}>
            {({ getFieldValue }) => getFieldValue('mode') === 'existing' ? (
              <Form.Item name="existing_client_id" label="Client" rules={[{ required: true }]}>
                <Select showSearch optionFilterProp="label" options={clients.data?.map((c) => ({ value: c.id, label: `${c.code} · ${c.name}` }))} />
              </Form.Item>
            ) : <>
              <Form.Item name="client_name" label="Client name" rules={[{ required: true }]}><Input /></Form.Item>
              <Form.Item name="gstin" label="GSTIN" normalize={(x: string) => x?.toUpperCase()}
                rules={[{ pattern: /^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/, message: 'Invalid GSTIN' }]}><Input maxLength={15} /></Form.Item>
              <Form.Item name="billing_address" label="Billing address"><Input.TextArea rows={2} /></Form.Item>
            </>}
          </Form.Item>
          <Form.Item name="project_name" label="Project" rules={[{ required: true }]}><Input placeholder="e.g. OMR Tech Park" /></Form.Item>
          <Row gutter={8}>
            <Col span={12}><Form.Item name="site_name" label="First site" rules={[{ required: true }]}><Input placeholder="e.g. Tower A" /></Form.Item></Col>
            <Col span={12}><Form.Item name="site_city" label="Site city"><Input /></Form.Item></Col>
          </Row>
          <Form.Item name="site_address" label="Site address"><Input.TextArea rows={2} /></Form.Item>
          <Typography.Text type="secondary">Credit terms start as pending; accounts sets the limit and deposit.</Typography.Text>
        </Form>
      </Modal>
    </Card>
  )
}
