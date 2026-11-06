import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert, App, Badge, Button, Card, Col, DatePicker, Descriptions, Drawer, Form, Input, InputNumber, Modal, Row, Select, Space,
  Statistic, Table, Tabs, Tag, Typography,
} from 'antd'
import { CheckOutlined, FilePdfOutlined, MinusCircleOutlined, PlusOutlined, SendOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { api, ApiError, openFile, post } from '../api/client'
import { useItems, useUserLookup } from '../api/hooks'
import type { DispatchRow, MaterialRequest, RequestDetail, RequestEstimate, SiteRow, StockWarehouse } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { dt, inr } from '../format'

const STATUS: Record<string, { label: string; color: string }> = {
  submitted: { label: 'Waiting approval', color: 'gold' },
  approved: { label: 'Approved', color: 'blue' },
  part_dispatched: { label: 'Part dispatched', color: 'geekblue' },
  dispatched: { label: 'Dispatched', color: 'green' },
  rejected: { label: 'Rejected', color: 'red' },
  cancelled: { label: 'Cancelled', color: 'default' },
  closed: { label: 'Closed', color: 'default' },
}
const statusTag = (s: string) => <Tag color={STATUS[s]?.color}>{STATUS[s]?.label ?? s}</Tag>

function useItemName() {
  const items = useItems()
  return (id: number) => {
    const it = items.data?.find((i) => i.id === id)
    return it ? `${it.code} · ${it.name}` : String(id)
  }
}

function refresh(qc: ReturnType<typeof useQueryClient>) {
  for (const k of ['requests', 'request', 'dispatches', 'stock-summary']) qc.invalidateQueries({ queryKey: [k] })
}

// ---------- New request ----------

function NewRequestModal({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: (id: number) => void }) {
  const { message } = App.useApp()
  const qc = useQueryClient()
  const [form] = Form.useForm()
  const items = useItems()
  const sites = useQuery({ queryKey: ['sites-all'], queryFn: () => api<SiteRow[]>('/sites'), enabled: open })
  const whs = useQuery({ queryKey: ['stock-warehouses'], queryFn: () => api<StockWarehouse[]>('/stock/warehouses'), enabled: open })
  const [est, setEst] = useState<RequestEstimate | null>(null)
  const values = Form.useWatch([], form)
  const key = JSON.stringify([values?.site_id, values?.warehouse_id, values?.duration_days, values?.transport_charge, values?.lines])

  useEffect(() => {
    const v = values
    const lines = (v?.lines ?? []).filter((l: { item_id?: number; qty?: number }) => l?.item_id && l?.qty)
    if (!v?.site_id || !v?.duration_days || !lines.length) { setEst(null); return }
    const t = setTimeout(() => {
      post<RequestEstimate>('/requests/estimate', {
        site_id: v.site_id, warehouse_id: v.warehouse_id, duration_days: v.duration_days,
        transport_charge: v.transport_charge ?? 0, lines,
      }).then(setEst).catch(() => setEst(null))
    }, 400)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  const save = useMutation({
    mutationFn: (v: Record<string, unknown>) => post<MaterialRequest>('/requests', {
      ...v, required_on: (v.required_on as dayjs.Dayjs).format('YYYY-MM-DD'),
    }),
    onSuccess: (r) => { message.success(`Request ${r.ref_no} raised`); form.resetFields(); setEst(null); onClose(); refresh(qc); onCreated(r.id) },
    onError: (e: Error) => message.error(e.message),
  })
  const avail = new Map(est?.availability.map((a) => [a.item_id, a]))
  return (
    <Modal open={open} title="New material request" onCancel={onClose} width={820} forceRender okText="Raise request"
      onOk={() => form.submit()} confirmLoading={save.isPending}>
      <Form form={form} name="form_new_request" layout="vertical" onFinish={(v) => save.mutate(v)}
        initialValues={{ duration_days: 30, transport_charge: 0, required_on: dayjs().add(1, 'day'), lines: [{}] }}>
        <Row gutter={12}>
          <Col xs={24} md={12}><Form.Item name="site_id" label="Site" rules={[{ required: true }]}>
            <Select showSearch optionFilterProp="label" placeholder="Client · site"
              options={sites.data?.map((s) => ({ value: s.id, label: `${s.client_name} · ${s.code} ${s.name}` }))} />
          </Form.Item></Col>
          <Col xs={24} md={12}><Form.Item name="warehouse_id" label="Ship from" rules={[{ required: true }]}>
            <Select options={whs.data?.map((w) => ({ value: w.id, label: `${w.code} · ${w.name}` }))} />
          </Form.Item></Col>
          <Col xs={12} md={8}><Form.Item name="required_on" label="Needed on" rules={[{ required: true }]}>
            <DatePicker style={{ width: '100%' }} format="DD MMM YYYY" />
          </Form.Item></Col>
          <Col xs={12} md={8}><Form.Item name="duration_days" label="Rental days" rules={[{ required: true }]}>
            <InputNumber min={1} precision={0} style={{ width: '100%' }} />
          </Form.Item></Col>
          <Col xs={24} md={8}><Form.Item name="transport_charge" label="Transport (₹)">
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item></Col>
        </Row>
        <Form.List name="lines">
          {(fields, { add, remove }) => (
            <>
              {fields.map((f) => {
                const itemId = values?.lines?.[f.name]?.item_id
                const a = itemId ? avail.get(itemId) : undefined
                return (
                  <Space key={f.key} align="baseline" wrap style={{ display: 'flex' }}>
                    <Form.Item name={[f.name, 'item_id']} rules={[{ required: true, message: 'Item' }]} style={{ width: 320 }}>
                      <Select showSearch optionFilterProp="label" placeholder="Item"
                        options={items.data?.filter((i) => i.is_active).map((i) => ({ value: i.id, label: `${i.code} · ${i.name}` }))} />
                    </Form.Item>
                    <Form.Item name={[f.name, 'qty']} rules={[{ required: true, message: 'Qty' }]}>
                      <InputNumber min={1} precision={0} placeholder="Qty" />
                    </Form.Item>
                    {a && a.available != null && (
                      a.short ? <Tag color="red">Only {a.available} available{a.elsewhere.length ? ` · ${a.elsewhere.map((e) => `${e.code}: ${e.available}`).join(', ')}` : ''}</Tag>
                        : <Tag color="green">{a.available} available</Tag>
                    )}
                    {fields.length > 1 && <MinusCircleOutlined onClick={() => remove(f.name)} />}
                  </Space>
                )
              })}
              <Button type="dashed" onClick={() => add()} icon={<PlusOutlined />}>Add item</Button>
            </>
          )}
        </Form.List>
        <Form.Item name="note" label="Note" style={{ marginTop: 16 }}><Input.TextArea rows={2} /></Form.Item>
      </Form>
      {est && (
        <Card size="small" title="Estimate">
          {est.client.credit_status === 'hold' && <Alert type="error" showIcon style={{ marginBottom: 8 }} message="Client is on credit hold. The request can be raised but not approved." />}
          {est.missing_rates.length > 0 && <Alert type="warning" showIcon style={{ marginBottom: 8 }} message="Some items have no rate card; they are priced at ₹0." />}
          <Space wrap size="large">
            <Statistic title="Rent" value={inr(est.rent)} />
            <Statistic title="Transport" value={inr(est.transport)} />
            <Statistic title={Number(est.igst) ? 'IGST' : 'CGST + SGST'} value={inr(est.gst)} />
            <Statistic title="Total" value={inr(est.total)} valueStyle={{ fontWeight: 600 }} />
          </Space>
          <Typography.Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
            Rent is charged for at least the rate card's minimum days ({est.lines.map((l) => l.days)[0]} days used).
          </Typography.Paragraph>
        </Card>
      )}
    </Modal>
  )
}

// ---------- Approval ----------

function ApproveModal({ req, onClose }: { req: RequestDetail | null; onClose: () => void }) {
  const { message } = App.useApp()
  const qc = useQueryClient()
  const itemName = useItemName()
  const [qty, setQty] = useState<Record<number, number>>({})
  const [challenge, setChallenge] = useState<{ challenge_id: string; channel: string; sent_to: string | null; estimate: RequestEstimate } | null>(null)
  const [code, setCode] = useState('')
  const [note, setNote] = useState('')
  const [devOtp, setDevOtp] = useState<string | null>(null)
  useEffect(() => {
    if (!req) return
    const av = new Map(req.availability.map((a) => [a.item_id, a.available ?? 0]))
    setQty(Object.fromEntries(req.lines.map((l) => [l.item_id, Math.min(l.qty_requested, av.get(l.item_id) ?? 0)])))
    setChallenge(null); setCode(''); setNote(''); setDevOtp(null)
  }, [req])
  const lines = req?.lines.map((l) => ({ item_id: l.item_id, qty: qty[l.item_id] ?? 0 })) ?? []
  const sendOtp = useMutation({
    mutationFn: () => post<typeof challenge>(`/requests/${req!.id}/approval-otp`, { lines }),
    onSuccess: (c) => { setChallenge(c); setCode('') },
    onError: (e: Error) => message.error(e.message),
  })
  const approve = useMutation({
    mutationFn: () => post<MaterialRequest>(`/requests/${req!.id}/approve`, { challenge_id: challenge!.challenge_id, code, lines, note: note || undefined }),
    onSuccess: (r) => { message.success(`${r.ref_no} approved and stock reserved`); onClose(); refresh(qc) },
    onError: (e: Error) => {
      message.error(e.message)
      if (e instanceof ApiError && ['otp_used', 'otp_expired', 'otp_locked', 'otp_wrong_transaction'].includes(e.code ?? '')) setChallenge(null)
    },
  })
  if (!req) return null
  const av = new Map(req.availability.map((a) => [a.item_id, a]))
  return (
    <Modal open={!!req} title={`Approve ${req.ref_no}`} onCancel={onClose} width={680} footer={null} destroyOnClose>
      <Table rowKey="item_id" size="small" pagination={false} dataSource={req.lines}
        columns={[
          { title: 'Item', dataIndex: 'item_id', render: itemName },
          { title: 'Requested', dataIndex: 'qty_requested', align: 'right' },
          { title: 'Available', align: 'right', render: (_, l) => {
            const a = av.get(l.item_id)
            return a?.short ? <Typography.Text type="danger">{a.available}</Typography.Text> : a?.available
          } },
          { title: 'Approve', render: (_, l) => (
            <InputNumber min={0} max={l.qty_requested} precision={0} disabled={!!challenge} value={qty[l.item_id]}
              onChange={(v) => setQty((q) => ({ ...q, [l.item_id]: v ?? 0 }))} />) },
        ]} />
      {!challenge ? (
        <Space direction="vertical" style={{ width: '100%', marginTop: 16 }}>
          <Typography.Text type="secondary">
            An OTP is sent to you for these exact quantities. Changing a quantity later needs a new OTP.
            {req.my_approval_limit != null && ` Your approval limit is ${inr(req.my_approval_limit)}.`}
          </Typography.Text>
          <Button type="primary" icon={<SendOutlined />} loading={sendOtp.isPending} onClick={() => sendOtp.mutate()}>Send OTP</Button>
        </Space>
      ) : (
        <Space direction="vertical" style={{ width: '100%', marginTop: 16 }}>
          <Alert type="info" showIcon message={`Approving ${inr(challenge.estimate.total)} (incl. GST). OTP sent${challenge.sent_to ? ` to ${challenge.sent_to}` : ''}.`} />
          <Input placeholder="6-digit OTP" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} style={{ maxWidth: 200, letterSpacing: 4 }}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} />
          <Input placeholder="Approval note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
          <Space wrap>
            <Button type="primary" icon={<CheckOutlined />} disabled={code.length !== 6} loading={approve.isPending} onClick={() => approve.mutate()}>Approve</Button>
            <Button onClick={() => setChallenge(null)}>Change quantities</Button>
            {challenge.channel === 'console' && (
              <Button type="dashed" onClick={async () => {
                const box = await fetch('/api/v1/dev/otp-outbox').then((r) => r.json())
                setDevOtp(box[0]?.code ?? 'none yet')
              }}>Show OTP (test mode)</Button>
            )}
            {devOtp && <Tag color="orange" style={{ cursor: 'pointer' }} onClick={() => setCode(devOtp)}>Test OTP: {devOtp} (click to fill)</Tag>}
          </Space>
        </Space>
      )}
    </Modal>
  )
}

// ---------- Dispatch & receipt ----------

function DispatchModal({ req, onClose }: { req: RequestDetail | null; onClose: () => void }) {
  const { message } = App.useApp()
  const qc = useQueryClient()
  const itemName = useItemName()
  const [form] = Form.useForm()
  useEffect(() => {
    if (req) form.setFieldsValue({ lines: req.lines.filter((l) => (l.qty_approved ?? 0) > l.qty_dispatched)
      .map((l) => ({ item_id: l.item_id, left: (l.qty_approved ?? 0) - l.qty_dispatched, qty: (l.qty_approved ?? 0) - l.qty_dispatched })) })
  }, [req, form])
  const save = useMutation({
    mutationFn: (v: { lines: { item_id: number; qty: number }[] } & Record<string, unknown>) =>
      post<DispatchRow>(`/requests/${req!.id}/dispatches`, { ...v, lines: v.lines.filter((l) => l.qty > 0).map((l) => ({ item_id: l.item_id, qty: l.qty })) }),
    onSuccess: (d) => { message.success(`Challan ${d.challan_no} created`); onClose(); refresh(qc); openFile(`/dispatches/${d.id}/challan.pdf`) },
    onError: (e: Error) => message.error(e.message),
  })
  return (
    <Modal open={!!req} title={`Dispatch ${req?.ref_no ?? ''}`} onCancel={onClose} width={640} forceRender okText="Dispatch and print challan"
      onOk={() => form.submit()} confirmLoading={save.isPending}>
      <Form form={form} name="form_dispatch" layout="vertical" onFinish={(v) => save.mutate(v)}>
        <Typography.Paragraph type="secondary">Enter the quantities actually loaded. Anything left stays reserved for a later trip.</Typography.Paragraph>
        <Form.List name="lines">
          {(fields) => fields.map((f) => {
            const l = form.getFieldValue(['lines', f.name])
            return (
              <Space key={f.key} align="baseline" style={{ display: 'flex' }}>
                <Form.Item name={[f.name, 'item_id']} hidden><Input /></Form.Item>
                <span style={{ width: 280, display: 'inline-block' }}>{itemName(l?.item_id)} <Typography.Text type="secondary">(left {l?.left})</Typography.Text></span>
                <Form.Item name={[f.name, 'qty']}><InputNumber min={0} max={l?.left} precision={0} /></Form.Item>
              </Space>
            )
          })}
        </Form.List>
        <Row gutter={12}>
          <Col span={8}><Form.Item name="vehicle_no" label="Vehicle no" rules={[{ required: true }]}><Input placeholder="TN 09 AB 1234" /></Form.Item></Col>
          <Col span={8}><Form.Item name="driver_name" label="Driver"><Input /></Form.Item></Col>
          <Col span={8}><Form.Item name="driver_phone" label="Driver phone"><Input /></Form.Item></Col>
        </Row>
        <Form.Item name="note" label="Note"><Input /></Form.Item>
      </Form>
    </Modal>
  )
}

export function ReceiveModal({ d, onClose }: { d: DispatchRow | null; onClose: () => void }) {
  const { message } = App.useApp()
  const qc = useQueryClient()
  const itemName = useItemName()
  const [form] = Form.useForm()
  useEffect(() => { if (d) form.setFieldsValue({ receiver_name: '', note: '', lines: d.lines.map((l) => ({ item_id: l.item_id, sent: l.qty, received: l.qty })) }) }, [d, form])
  const save = useMutation({
    mutationFn: (v: { lines: { item_id: number; received: number }[] } & Record<string, unknown>) =>
      post<DispatchRow>(`/dispatches/${d!.id}/receive`, { ...v, lines: v.lines.map((l) => ({ item_id: l.item_id, received: l.received ?? 0 })) }),
    onSuccess: (r) => {
      const short = r.lines.reduce((a, l) => a + (l.qty_short ?? 0), 0)
      message.success(`Receipt recorded${short ? `; ${short} pcs short marked missing` : ''}`); onClose(); refresh(qc)
    },
    onError: (e: Error) => message.error(e.message),
  })
  return (
    <Modal open={!!d} title={`Site receipt · ${d?.challan_no ?? ''}`} onCancel={onClose} forceRender okText="Confirm receipt"
      onOk={() => form.submit()} confirmLoading={save.isPending}>
      <Form form={form} name="form_site_receipt" layout="vertical" onFinish={(v) => save.mutate(v)}>
        <Form.List name="lines">
          {(fields) => fields.map((f) => {
            const l = form.getFieldValue(['lines', f.name])
            return (
              <Space key={f.key} align="baseline" style={{ display: 'flex' }}>
                <Form.Item name={[f.name, 'item_id']} hidden><Input /></Form.Item>
                <span style={{ width: 260, display: 'inline-block' }}>{itemName(l?.item_id)} <Typography.Text type="secondary">(sent {l?.sent})</Typography.Text></span>
                <Form.Item name={[f.name, 'received']} label="Received"><InputNumber min={0} max={l?.sent} precision={0} /></Form.Item>
              </Space>
            )
          })}
        </Form.List>
        <Form.Item name="receiver_name" label="Received by (name at site)" rules={[{ required: true, min: 2 }]}><Input /></Form.Item>
        <Form.Item name="note" label="Note"><Input /></Form.Item>
      </Form>
    </Modal>
  )
}

// ---------- Detail ----------

function RequestDrawer({ id, onClose }: { id: number | null; onClose: () => void }) {
  const { can, me: user } = useAuth()
  const { message, modal } = App.useApp()
  const qc = useQueryClient()
  const itemName = useItemName()
  const users = useUserLookup()
  const userName = (uid: number | null) => users.data?.find((u) => u.id === uid)?.full_name ?? (uid ?? '')
  const q = useQuery({ queryKey: ['request', id], enabled: !!id, queryFn: () => api<RequestDetail>(`/requests/${id}`) })
  const [approving, setApproving] = useState<RequestDetail | null>(null)
  const [dispatching, setDispatching] = useState<RequestDetail | null>(null)
  const [receiving, setReceiving] = useState<DispatchRow | null>(null)
  const r = q.data
  const act = (path: string, title: string, label: string) => {
    let reason = ''
    modal.confirm({
      title, okText: label,
      content: <Input.TextArea rows={2} placeholder="Reason" onChange={(e) => (reason = e.target.value)} />,
      onOk: () => post(`/requests/${r!.id}/${path}`, { reason }).then(() => { message.success('Done'); refresh(qc) })
        .catch((e: Error) => { message.error(e.message); throw e }),
    })
  }
  const av = new Map(r?.availability.map((a) => [a.item_id, a]))
  const canCancel = r && ['submitted', 'approved'].includes(r.status) && (can('requests.approve') || (r.created_by === user?.id && can('requests.create')))
  return (
    <Drawer open={!!id} onClose={onClose} width={760} title={r ? <Space>{r.ref_no} {statusTag(r.status)}{r.version > 1 && <Tag>v{r.version}</Tag>}</Space> : ''}
      extra={r && (
        <Space wrap>
          {r.can_approve && <Button type="primary" onClick={() => setApproving(r)}>Approve…</Button>}
          {r.status === 'submitted' && can('requests.approve') && <Button danger onClick={() => act('reject', `Reject ${r.ref_no}?`, 'Reject')}>Reject</Button>}
          {['approved', 'part_dispatched'].includes(r.status) && can('dispatch.manage') && <Button type="primary" onClick={() => setDispatching(r)}>Dispatch…</Button>}
          {r.status === 'part_dispatched' && (can('dispatch.manage') || can('requests.approve')) && <Button onClick={() => act('close', `Close ${r.ref_no} and release the rest?`, 'Close request')}>Close</Button>}
          {canCancel && <Button onClick={() => act('cancel', `Cancel ${r.ref_no}?`, 'Cancel request')}>Cancel request</Button>}
        </Space>
      )}>
      {r && (
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          {r.client.credit_status === 'hold' && r.status === 'submitted' && <Alert type="error" showIcon message="Client is on credit hold; this request cannot be approved until accounts release it." />}
          {r.status === 'submitted' && !r.can_approve && can('requests.approve') && (
            <Alert type="warning" showIcon message={r.created_by === user?.id ? 'You raised this request, so someone else must approve it.'
              : `This request is above your approval limit${r.my_approval_limit != null ? ` (${inr(r.my_approval_limit)})` : ''}.`} />
          )}
          <Descriptions size="small" column={{ xs: 1, sm: 2 }} bordered>
            <Descriptions.Item label="Client">{r.client.code} · {r.client.name}</Descriptions.Item>
            <Descriptions.Item label="Site">{r.site_name}</Descriptions.Item>
            <Descriptions.Item label="Ship from">{r.warehouse_code}</Descriptions.Item>
            <Descriptions.Item label="Needed on">{dayjs(r.required_on).format('DD MMM YYYY')}</Descriptions.Item>
            <Descriptions.Item label="Rental days">{r.duration_days}</Descriptions.Item>
            <Descriptions.Item label="Raised by">{userName(r.created_by)} · {dt(r.created_at)}</Descriptions.Item>
            {r.approved_by && <Descriptions.Item label="Approved by">{userName(r.approved_by)} · {dt(r.approved_at)} <Tag color="green">OTP</Tag></Descriptions.Item>}
            {r.decision_note && <Descriptions.Item label="Note">{r.decision_note}</Descriptions.Item>}
            {r.note && <Descriptions.Item label="Request note">{r.note}</Descriptions.Item>}
          </Descriptions>
          <Table rowKey="item_id" size="small" pagination={false} dataSource={r.lines}
            columns={[
              { title: 'Item', dataIndex: 'item_id', render: itemName },
              { title: 'Requested', dataIndex: 'qty_requested', align: 'right' },
              ...(r.status === 'submitted' ? [{ title: 'Available now', align: 'right' as const, render: (_: unknown, l: { item_id: number }) => {
                const a = av.get(l.item_id)
                if (!a) return null
                return a.short ? <Space direction="vertical" size={0}><Typography.Text type="danger">{a.available} (short {a.short})</Typography.Text>
                  {a.elsewhere.length > 0 && <Typography.Text type="secondary" style={{ fontSize: 12 }}>{a.elsewhere.map((e) => `${e.code}: ${e.available}`).join(', ')}</Typography.Text>}</Space>
                  : <Typography.Text type="success">{a.available}</Typography.Text>
              } }] : []),
              { title: 'Approved', dataIndex: 'qty_approved', align: 'right' },
              { title: 'Dispatched', dataIndex: 'qty_dispatched', align: 'right' },
              { title: 'Rate/day', dataIndex: 'rate_per_day', align: 'right', render: inr },
            ]} />
          <Space wrap size="large">
            <Statistic title="Rent" value={inr(r.est_rent)} />
            <Statistic title="Transport" value={inr(r.transport_charge)} />
            <Statistic title="GST" value={inr(r.est_gst)} />
            <Statistic title="Total" value={inr(r.est_total)} valueStyle={{ fontWeight: 600 }} />
          </Space>
          {r.dispatches.length > 0 && (
            <Card size="small" title="Challans">
              <Table rowKey="id" size="small" pagination={false} dataSource={r.dispatches}
                columns={[
                  { title: 'Challan', dataIndex: 'challan_no' },
                  { title: 'When', dataIndex: 'dispatched_at', render: dt },
                  { title: 'Vehicle', dataIndex: 'vehicle_no' },
                  { title: 'Pieces', align: 'right', render: (_, d) => d.lines.reduce((a, l) => a + l.qty, 0) },
                  { title: 'Status', render: (_, d) => d.status === 'received'
                    ? <Tag color="green">Received{d.lines.some((l) => l.qty_short) ? `, ${d.lines.reduce((a, l) => a + (l.qty_short ?? 0), 0)} short` : ''}</Tag>
                    : <Tag color="geekblue">On the way</Tag> },
                  { title: '', render: (_, d) => (
                    <Space>
                      <Button size="small" icon={<FilePdfOutlined />} onClick={() => openFile(`/dispatches/${d.id}/challan.pdf`).catch((e) => message.error(e.message))}>Challan</Button>
                      {d.status === 'in_transit' && (can('dispatch.manage') || can('requests.create')) && <Button size="small" onClick={() => setReceiving(d)}>Site receipt</Button>}
                    </Space>
                  ) },
                ]} />
            </Card>
          )}
        </Space>
      )}
      <ApproveModal req={approving} onClose={() => setApproving(null)} />
      <DispatchModal req={dispatching} onClose={() => setDispatching(null)} />
      <ReceiveModal d={receiving} onClose={() => setReceiving(null)} />
    </Drawer>
  )
}

// ---------- Page ----------

export default function RequestsPage() {
  const { can } = useAuth()
  const [tab, setTab] = useState(can('requests.approve') ? 'mine' : 'open')
  const [openId, setOpenId] = useState<number | null>(null)
  const [creating, setCreating] = useState(false)
  const params = tab === 'mine' ? '?pending_my_approval=true' : tab === 'open' ? '?status=open' : ''
  const list = useQuery({ queryKey: ['requests', tab], queryFn: () => api<MaterialRequest[]>(`/requests${params}`) })
  const pending = useQuery({ queryKey: ['requests', 'mine'], queryFn: () => api<MaterialRequest[]>('/requests?pending_my_approval=true'), enabled: can('requests.approve') })
  const tabs = useMemo(() => [
    ...(can('requests.approve') ? [{ key: 'mine', label: <Badge count={pending.data?.length ?? 0} offset={[12, 0]} size="small">Waiting for my approval</Badge> }] : []),
    { key: 'open', label: 'Open' },
    { key: 'all', label: 'All' },
  ], [can, pending.data])
  return (
    <>
      <Space style={{ width: '100%', justifyContent: 'space-between' }} wrap>
        <Typography.Title level={3} style={{ margin: 0 }}>Requests & dispatch</Typography.Title>
        {can('requests.create') && <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreating(true)}>New request</Button>}
      </Space>
      <Tabs activeKey={tab} onChange={setTab} items={tabs} />
      <Table rowKey="id" size="small" loading={list.isLoading} dataSource={list.data} scroll={{ x: 900 }}
        onRow={(r) => ({ onClick: () => setOpenId(r.id), style: { cursor: 'pointer' } })}
        locale={{ emptyText: tab === 'mine' ? 'Nothing waiting for your approval' : 'No requests' }}
        columns={[
          { title: 'Ref', dataIndex: 'ref_no' },
          { title: 'Client', dataIndex: 'client_name' },
          { title: 'Site', dataIndex: 'site_name' },
          { title: 'From', dataIndex: 'warehouse_code' },
          { title: 'Needed on', dataIndex: 'required_on', render: (d) => dayjs(d).format('DD MMM') },
          { title: 'Pieces', align: 'right', render: (_, r) => r.lines.reduce((a, l) => a + l.qty_requested, 0) },
          { title: 'Value', dataIndex: 'est_total', align: 'right', render: inr },
          { title: 'Status', dataIndex: 'status', render: statusTag },
          { title: 'Raised', dataIndex: 'created_at', render: dt },
        ]} />
      <NewRequestModal open={creating} onClose={() => setCreating(false)} onCreated={setOpenId} />
      <RequestDrawer id={openId} onClose={() => setOpenId(null)} />
    </>
  )
}
