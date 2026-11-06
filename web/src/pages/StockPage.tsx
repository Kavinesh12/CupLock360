import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert, App, Button, Card, Drawer, Form, Input, InputNumber, Modal, Select, Space, Statistic, Table, Tabs, Tag, Typography, Upload,
} from 'antd'
import { DownloadOutlined, MinusCircleOutlined, PlusOutlined, SwapOutlined, UploadOutlined } from '@ant-design/icons'
import { api, download, post, upload } from '../api/client'
import { useItems, useUserLookup } from '../api/hooks'
import type {
  OpeningPreview, StockCheck, StockLocationRow, StockMeta, StockMovement, StockSummaryRow, StockTransfer, StockWarehouse,
} from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { dt } from '../format'

export const STATUS_LABEL: Record<string, string> = {
  available: 'Available', reserved: 'Reserved', in_transit: 'In transit', at_site: 'At site', returned: 'Returned',
  inspection: 'Inspection', maintenance: 'Under repair', damaged: 'Damaged', missing: 'Missing',
}
const STATUS_COLOR: Record<string, string> = {
  available: 'green', reserved: 'blue', in_transit: 'geekblue', at_site: 'purple', returned: 'cyan',
  inspection: 'gold', maintenance: 'orange', damaged: 'red', missing: 'magenta',
}
const KIND_LABEL: Record<string, string> = {
  opening: 'Opening stock', transfer_send: 'Transfer sent', transfer_receive: 'Transfer received',
  status_change: 'Status change', write_off: 'Write-off', stock_check: 'Stock check',
}

function useStockWarehouses() {
  return useQuery({ queryKey: ['stock-warehouses'], queryFn: () => api<StockWarehouse[]>('/stock/warehouses') })
}
function useMeta() {
  return useQuery({ queryKey: ['stock-meta'], queryFn: () => api<StockMeta>('/stock/meta'), staleTime: Infinity })
}
const whLabel = (w?: StockWarehouse) => (w ? `${w.code} · ${w.name}` : '')

function invalidateStock(qc: ReturnType<typeof useQueryClient>) {
  for (const k of ['stock-summary', 'stock-movements', 'stock-transfers', 'stock-checks', 'stock-where']) {
    qc.invalidateQueries({ queryKey: [k] })
  }
}

// ---------- Summary ----------

function SummaryTab() {
  const { can } = useAuth()
  const whs = useStockWarehouses()
  const meta = useMeta()
  const [wh, setWh] = useState<number | undefined>()
  const [where, setWhere] = useState<StockSummaryRow | null>(null)
  const [action, setAction] = useState<'status' | 'writeoff' | null>(null)
  const summary = useQuery({
    queryKey: ['stock-summary', wh],
    queryFn: () => api<StockSummaryRow[]>(`/stock/summary${wh ? `?warehouse_id=${wh}` : ''}`),
  })
  const statuses = meta.data?.statuses ?? []
  const shown = statuses.filter((s) => summary.data?.some((r) => Number(r[s]) > 0) || ['available', 'at_site', 'damaged'].includes(s))
  const totals = useMemo(() => {
    const t: Record<string, number> = {}
    for (const r of summary.data ?? []) for (const s of statuses) t[s] = (t[s] ?? 0) + Number(r[s] ?? 0)
    return t
  }, [summary.data, statuses])
  const grand = Object.values(totals).reduce((a, b) => a + b, 0)

  return (
    <>
      <Space wrap style={{ marginBottom: 16 }}>
        <Select style={{ width: 260 }} placeholder="All warehouses, sites and transit" allowClear value={wh} onChange={setWh}
          options={whs.data?.filter((w) => w.mine).map((w) => ({ value: w.id, label: whLabel(w) }))} />
        {can('stock.move') && <Button icon={<SwapOutlined />} onClick={() => setAction('status')}>Change status</Button>}
        {can('stock.adjust') && <Button danger onClick={() => setAction('writeoff')}>Write off</Button>}
      </Space>
      <Space wrap size="large" style={{ marginBottom: 16 }}>
        <Card size="small"><Statistic title="Total pieces" value={grand} /></Card>
        {['available', 'at_site', 'in_transit', 'damaged', 'missing'].map((s) => (
          <Card size="small" key={s}><Statistic title={STATUS_LABEL[s]} value={totals[s] ?? 0} /></Card>
        ))}
      </Space>
      <Table rowKey="item_id" size="small" loading={summary.isLoading} dataSource={summary.data} scroll={{ x: 900 }} pagination={false}
        onRow={(r) => ({ onClick: () => setWhere(r), style: { cursor: 'pointer' } })}
        locale={{ emptyText: 'No stock yet. Load opening stock from the Opening stock tab.' }}
        columns={[
          { title: 'Item', dataIndex: 'item_code', fixed: 'left', render: (c, r) => <><b>{c}</b><br /><Typography.Text type="secondary">{r.item_name}</Typography.Text></> },
          ...shown.map((s) => ({ title: STATUS_LABEL[s], dataIndex: s, align: 'right' as const, render: (v: number) => (v ? v : <Typography.Text type="secondary">0</Typography.Text>) })),
          { title: 'Total', dataIndex: 'total', align: 'right' as const, render: (v: number) => <b>{v}</b> },
        ]} />
      <WhereDrawer row={where} onClose={() => setWhere(null)} />
      <StatusModal mode={action} onClose={() => setAction(null)} />
    </>
  )
}

function WhereDrawer({ row, onClose }: { row: StockSummaryRow | null; onClose: () => void }) {
  const where = useQuery({
    queryKey: ['stock-where', row?.item_id], enabled: !!row,
    queryFn: () => api<StockLocationRow[]>(`/stock/by-location?item_id=${row!.item_id}`),
  })
  return (
    <Drawer open={!!row} onClose={onClose} title={row ? `${row.item_code}: where is it?` : ''} width={480}>
      <Table rowKey={(r) => `${r.location_type}-${r.location_id}-${r.status}`} size="small" pagination={false}
        loading={where.isLoading} dataSource={where.data}
        columns={[
          { title: 'Location', dataIndex: 'location_name', render: (n, r) => <>{n} <Tag>{r.location_type}</Tag></> },
          { title: 'Status', dataIndex: 'status', render: (s) => <Tag color={STATUS_COLOR[s]}>{STATUS_LABEL[s]}</Tag> },
          { title: 'Qty', dataIndex: 'qty', align: 'right' },
        ]} />
    </Drawer>
  )
}

function StatusModal({ mode, onClose }: { mode: 'status' | 'writeoff' | null; onClose: () => void }) {
  const { message } = App.useApp()
  const qc = useQueryClient()
  const whs = useStockWarehouses()
  const items = useItems()
  const meta = useMeta()
  const [form] = Form.useForm()
  const save = useMutation({
    mutationFn: (v: Record<string, unknown>) => {
      if (mode === 'writeoff') return post<StockMovement>('/stock/write-off', v)
      const [from_status, to_status] = String(v.transition).split('>')
      return post<StockMovement>('/stock/status-change', { ...v, from_status, to_status, transition: undefined })
    },
    onSuccess: (m) => { message.success(`Posted ${m.ref_no}`); form.resetFields(); onClose(); invalidateStock(qc) },
    onError: (e: Error) => message.error(e.message),
  })
  return (
    <Modal open={!!mode} title={mode === 'writeoff' ? 'Write off damaged or missing stock' : 'Change stock status'}
      onCancel={onClose} onOk={() => form.submit()} confirmLoading={save.isPending} forceRender okText="Post">
      <Form form={form} name="form_stock_status" layout="vertical" onFinish={(v) => save.mutate(v)}>
        <Form.Item name="warehouse_id" label="Warehouse" rules={[{ required: true }]}>
          <Select options={whs.data?.filter((w) => w.mine).map((w) => ({ value: w.id, label: whLabel(w) }))} />
        </Form.Item>
        <Form.Item name="item_id" label="Item" rules={[{ required: true }]}>
          <Select showSearch optionFilterProp="label" options={items.data?.map((i) => ({ value: i.id, label: `${i.code} · ${i.name}` }))} />
        </Form.Item>
        {mode === 'writeoff' ? (
          <Form.Item name="from_status" label="From" rules={[{ required: true }]}>
            <Select options={meta.data?.write_off_from.map((s) => ({ value: s, label: STATUS_LABEL[s] }))} />
          </Form.Item>
        ) : (
          <Form.Item name="transition" label="Change" rules={[{ required: true }]}>
            <Select options={meta.data?.transitions.map((t) => ({
              value: `${t.from}>${t.to}`, label: `${STATUS_LABEL[t.from]} → ${STATUS_LABEL[t.to]} (${t.label})` }))} />
          </Form.Item>
        )}
        <Form.Item name="qty" label="Quantity" rules={[{ required: true }]}><InputNumber min={1} precision={0} style={{ width: '100%' }} /></Form.Item>
        <Form.Item name="reason" label="Reason" rules={mode === 'writeoff' ? [{ required: true, min: 3 }] : []}><Input /></Form.Item>
      </Form>
    </Modal>
  )
}

// ---------- Movements ----------

function MovementsTab() {
  const whs = useStockWarehouses()
  const items = useItems()
  const users = useUserLookup()
  const [kind, setKind] = useState<string | undefined>()
  const [item, setItem] = useState<number | undefined>()
  const mv = useQuery({
    queryKey: ['stock-movements', kind, item],
    queryFn: () => {
      const q = new URLSearchParams({ limit: '200' })
      if (kind) q.set('kind', kind)
      if (item) q.set('item_id', String(item))
      return api<StockMovement[]>(`/stock/movements?${q}`)
    },
  })
  const whName = (id: number | null) => whs.data?.find((w) => w.id === id)?.code ?? ''
  const itemCode = (id: number) => items.data?.find((i) => i.id === id)?.code ?? id
  return (
    <>
      <Space wrap style={{ marginBottom: 16 }}>
        <Select style={{ width: 200 }} placeholder="All kinds" allowClear value={kind} onChange={setKind}
          options={Object.entries(KIND_LABEL).map(([value, label]) => ({ value, label }))} />
        <Select style={{ width: 240 }} placeholder="All items" allowClear showSearch optionFilterProp="label" value={item} onChange={setItem}
          options={items.data?.map((i) => ({ value: i.id, label: `${i.code} · ${i.name}` }))} />
      </Space>
      <Table rowKey="id" size="small" loading={mv.isLoading} dataSource={mv.data} scroll={{ x: 800 }}
        expandable={{
          expandedRowRender: (m) => (
            <Table rowKey={(_, i) => String(i)} size="small" pagination={false} dataSource={m.entries}
              columns={[
                { title: 'Item', dataIndex: 'item_id', render: itemCode },
                { title: 'Location', render: (_, e) => (e.location_type === 'warehouse' ? whName(e.location_id) : `${e.location_type} #${e.location_id}`) },
                { title: 'Status', dataIndex: 'status', render: (s) => <Tag color={STATUS_COLOR[s]}>{STATUS_LABEL[s]}</Tag> },
                { title: 'Qty', dataIndex: 'qty', align: 'right', render: (q: number) => <Typography.Text type={q < 0 ? 'danger' : 'success'}>{q > 0 ? `+${q}` : q}</Typography.Text> },
              ]} />
          ),
        }}
        columns={[
          { title: 'Ref', dataIndex: 'ref_no' },
          { title: 'When', dataIndex: 'created_at', render: dt },
          { title: 'Kind', dataIndex: 'kind', render: (k) => <Tag>{KIND_LABEL[k] ?? k}</Tag> },
          { title: 'Warehouse', dataIndex: 'warehouse_id', render: whName },
          { title: 'Reason', dataIndex: 'reason' },
          { title: 'By', dataIndex: 'created_by', render: (id) => users.data?.find((u) => u.id === id)?.full_name ?? id },
        ]} />
    </>
  )
}

// ---------- Transfers ----------

function TransfersTab() {
  const { can } = useAuth()
  const { message } = App.useApp()
  const qc = useQueryClient()
  const whs = useStockWarehouses()
  const items = useItems()
  const [sending, setSending] = useState(false)
  const [receiving, setReceiving] = useState<StockTransfer | null>(null)
  const [form] = Form.useForm()
  const [rform] = Form.useForm()
  const list = useQuery({ queryKey: ['stock-transfers'], queryFn: () => api<StockTransfer[]>('/stock/transfers') })
  const wh = (id: number) => whs.data?.find((w) => w.id === id)
  const itemCode = (id: number) => items.data?.find((i) => i.id === id)?.code ?? id
  const send = useMutation({
    mutationFn: (v: Record<string, unknown>) => post<StockTransfer>('/stock/transfers', v),
    onSuccess: (t) => { message.success(`Transfer ${t.ref_no} sent`); setSending(false); form.resetFields(); invalidateStock(qc) },
    onError: (e: Error) => message.error(e.message),
  })
  const receive = useMutation({
    mutationFn: (v: { lines: { item_id: number; received: number; damaged: number }[] }) =>
      post<StockTransfer>(`/stock/transfers/${receiving!.id}/receive`, v),
    onSuccess: (t) => {
      const missing = t.lines.reduce((a, l) => a + (l.qty_missing ?? 0), 0)
      message.success(`Received ${t.ref_no}${missing ? `; ${missing} pcs marked missing` : ''}`)
      setReceiving(null); invalidateStock(qc)
    },
    onError: (e: Error) => message.error(e.message),
  })
  const openReceive = (t: StockTransfer) => {
    rform.setFieldsValue({ lines: t.lines.map((l) => ({ item_id: l.item_id, sent: l.qty_sent, received: l.qty_sent, damaged: 0 })) })
    setReceiving(t)
  }
  return (
    <>
      {can('stock.move') && <Button type="primary" icon={<PlusOutlined />} style={{ marginBottom: 16 }} onClick={() => setSending(true)}>New transfer</Button>}
      <Table rowKey="id" size="small" loading={list.isLoading} dataSource={list.data} scroll={{ x: 800 }}
        expandable={{ expandedRowRender: (t) => (
          <Table rowKey="item_id" size="small" pagination={false} dataSource={t.lines} columns={[
            { title: 'Item', dataIndex: 'item_id', render: itemCode },
            { title: 'Sent', dataIndex: 'qty_sent', align: 'right' },
            { title: 'Received', dataIndex: 'qty_received', align: 'right' },
            { title: 'Damaged', dataIndex: 'qty_damaged', align: 'right' },
            { title: 'Missing', dataIndex: 'qty_missing', align: 'right' },
          ]} />) }}
        columns={[
          { title: 'Ref', dataIndex: 'ref_no' },
          { title: 'From', dataIndex: 'from_warehouse_id', render: (id) => wh(id)?.code },
          { title: 'To', dataIndex: 'to_warehouse_id', render: (id) => wh(id)?.code },
          { title: 'Vehicle', dataIndex: 'vehicle_no' },
          { title: 'Sent', dataIndex: 'sent_at', render: dt },
          { title: 'Pieces', render: (_, t) => t.lines.reduce((a, l) => a + l.qty_sent, 0), align: 'right' },
          { title: 'Status', dataIndex: 'status', render: (s) => <Tag color={s === 'received' ? 'green' : 'geekblue'}>{s === 'received' ? 'Received' : 'In transit'}</Tag> },
          { title: '', render: (_, t) => t.status === 'in_transit' && can('stock.move') && wh(t.to_warehouse_id)?.mine &&
            <Button size="small" onClick={() => openReceive(t)}>Receive</Button> },
        ]} />

      <Modal open={sending} title="Send stock to another warehouse" onCancel={() => setSending(false)} width={640}
        onOk={() => form.submit()} confirmLoading={send.isPending} forceRender okText="Send">
        <Form form={form} name="form_transfer" layout="vertical" onFinish={(v) => send.mutate(v)} initialValues={{ lines: [{}] }}>
          <Space.Compact block>
            <Form.Item name="from_warehouse_id" label="From" rules={[{ required: true }]} style={{ flex: 1 }}>
              <Select options={whs.data?.filter((w) => w.mine).map((w) => ({ value: w.id, label: whLabel(w) }))} />
            </Form.Item>
            <Form.Item name="to_warehouse_id" label="To" rules={[{ required: true }]} style={{ flex: 1, marginLeft: 8 }}>
              <Select options={whs.data?.map((w) => ({ value: w.id, label: whLabel(w) }))} />
            </Form.Item>
          </Space.Compact>
          <Form.Item name="vehicle_no" label="Vehicle number"><Input placeholder="TN 01 AB 1234" /></Form.Item>
          <Form.List name="lines">
            {(fields, { add, remove }) => (
              <>
                {fields.map((f) => (
                  <Space key={f.key} align="baseline" style={{ display: 'flex' }}>
                    <Form.Item name={[f.name, 'item_id']} rules={[{ required: true, message: 'Item' }]} style={{ width: 360 }}>
                      <Select showSearch optionFilterProp="label" placeholder="Item"
                        options={items.data?.map((i) => ({ value: i.id, label: `${i.code} · ${i.name}` }))} />
                    </Form.Item>
                    <Form.Item name={[f.name, 'qty']} rules={[{ required: true, message: 'Qty' }]}>
                      <InputNumber min={1} precision={0} placeholder="Qty" />
                    </Form.Item>
                    {fields.length > 1 && <MinusCircleOutlined onClick={() => remove(f.name)} />}
                  </Space>
                ))}
                <Button type="dashed" onClick={() => add()} icon={<PlusOutlined />}>Add item</Button>
              </>
            )}
          </Form.List>
          <Form.Item name="note" label="Note" style={{ marginTop: 16 }}><Input /></Form.Item>
        </Form>
      </Modal>

      <Modal open={!!receiving} title={`Receive ${receiving?.ref_no ?? ''}`} onCancel={() => setReceiving(null)} width={600}
        onOk={() => rform.submit()} confirmLoading={receive.isPending} forceRender okText="Confirm receipt">
        <Typography.Paragraph type="secondary">Anything not counted as received or damaged is marked missing at the sending warehouse.</Typography.Paragraph>
        <Form form={rform} name="form_receive" onFinish={(v) => receive.mutate({ lines: v.lines.map((l: Record<string, number>) => ({ item_id: l.item_id, received: l.received ?? 0, damaged: l.damaged ?? 0 })) })}>
          <Form.List name="lines">
            {(fields) => fields.map((f) => {
              const line = rform.getFieldValue(['lines', f.name])
              return (
                <Space key={f.key} align="baseline" style={{ display: 'flex' }}>
                  <Form.Item name={[f.name, 'item_id']} hidden><Input /></Form.Item>
                  <span style={{ width: 160, display: 'inline-block' }}><b>{itemCode(line?.item_id)}</b> (sent {line?.sent})</span>
                  <Form.Item name={[f.name, 'received']} label="Good"><InputNumber min={0} max={line?.sent} precision={0} /></Form.Item>
                  <Form.Item name={[f.name, 'damaged']} label="Damaged"><InputNumber min={0} max={line?.sent} precision={0} /></Form.Item>
                </Space>
              )
            })}
          </Form.List>
        </Form>
      </Modal>
    </>
  )
}

// ---------- Opening stock ----------

function OpeningTab() {
  const { message } = App.useApp()
  const qc = useQueryClient()
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<OpeningPreview | null>(null)
  const run = useMutation({
    mutationFn: (commit: boolean) => {
      const fd = new FormData()
      fd.append('file', file!)
      fd.append('commit', String(commit))
      return upload<OpeningPreview>('/stock/opening/import', fd)
    },
    onSuccess: (p) => {
      setPreview(p)
      if (p.committed) { message.success(`Opening stock loaded: ${p.movements?.join(', ')}`); invalidateStock(qc) }
    },
    onError: (e: Error) => message.error(e.message),
  })
  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Alert type="info" showIcon message="Load each warehouse's opening stock once, before any other stock movement there."
        description="Download the template, fill one row per warehouse and item, then upload it. You'll see a preview first; nothing is saved until you confirm." />
      <Space wrap>
        <Button icon={<DownloadOutlined />} onClick={() => download('/stock/opening/template', 'cuplock360-opening-stock.xlsx').catch((e) => message.error(e.message))}>
          Download template
        </Button>
        <Upload accept=".xlsx" maxCount={1} beforeUpload={(f) => { setFile(f); setPreview(null); return false }}
          onRemove={() => { setFile(null); setPreview(null) }}>
          <Button icon={<UploadOutlined />}>Choose filled file</Button>
        </Upload>
        <Button type="primary" disabled={!file} loading={run.isPending && !preview} onClick={() => run.mutate(false)}>Check file</Button>
      </Space>
      {preview && (
        <>
          {preview.errors.length > 0 && (
            <Alert type="error" showIcon message={`${preview.errors.length} problem(s). Fix the file and upload again.`}
              description={<ul style={{ margin: 0, paddingLeft: 18 }}>{preview.errors.slice(0, 20).map((e) => <li key={e}>{e}</li>)}</ul>} />
          )}
          {preview.committed && <Alert type="success" showIcon message={`Saved as ${preview.movements?.join(', ')}`} />}
          <Table rowKey="row" size="small" dataSource={preview.rows} pagination={{ pageSize: 50 }} scroll={{ x: 700 }}
            columns={[
              { title: 'Row', dataIndex: 'row', width: 60 },
              { title: 'Warehouse', dataIndex: 'warehouse_code' },
              { title: 'Item', dataIndex: 'item_code', render: (c, r) => <>{c} <Typography.Text type="secondary">{r.item_name}</Typography.Text></> },
              { title: 'Available', align: 'right', render: (_, r) => r.qty.available },
              { title: 'Damaged', align: 'right', render: (_, r) => r.qty.damaged },
              { title: 'Under repair', align: 'right', render: (_, r) => r.qty.maintenance },
              { title: 'Problems', dataIndex: 'errors', render: (e: string[]) => e.map((x) => <Tag color="red" key={x}>{x}</Tag>) },
            ]} />
          {preview.ok && !preview.committed && (
            <Space>
              <Typography.Text>
                Totals: {Object.entries(preview.totals ?? {}).map(([s, q]) => `${STATUS_LABEL[s]} ${q}`).join(' · ')}
              </Typography.Text>
              <Button type="primary" loading={run.isPending} onClick={() => run.mutate(true)}>Confirm and load stock</Button>
            </Space>
          )}
        </>
      )}
    </Space>
  )
}

// ---------- Stock check ----------

function CheckTab() {
  const { can } = useAuth()
  const { message, modal } = App.useApp()
  const qc = useQueryClient()
  const whs = useStockWarehouses()
  const items = useItems()
  const [wh, setWh] = useState<number | undefined>()
  const [counts, setCounts] = useState<Record<number, number | null>>({})
  const sys = useQuery({
    queryKey: ['stock-summary', 'check', wh], enabled: !!wh,
    queryFn: () => api<StockSummaryRow[]>(`/stock/summary?warehouse_id=${wh}`),
  })
  const history = useQuery({ queryKey: ['stock-checks'], queryFn: () => api<StockCheck[]>('/stock/checks') })
  const rows = useMemo(() => {
    const byItem = new Map((sys.data ?? []).map((r) => [r.item_id, Number(r.available ?? 0)]))
    return (items.data ?? []).filter((i) => i.is_active || byItem.get(i.id))
      .map((i) => ({ item_id: i.id, code: i.code, name: i.name, system: byItem.get(i.id) ?? 0 }))
  }, [items.data, sys.data])
  const submit = useMutation({
    mutationFn: (lines: { item_id: number; counted: number }[]) => post<StockCheck>('/stock/checks', { warehouse_id: wh, lines }),
    onSuccess: (c) => { message.success(`Stock check ${c.ref_no} posted`); setCounts({}); invalidateStock(qc) },
    onError: (e: Error) => message.error(e.message),
  })
  const entered = rows.filter((r) => counts[r.item_id] != null)
  const confirm = () => {
    const short = entered.reduce((a, r) => a + Math.max(0, r.system - (counts[r.item_id] ?? 0)), 0)
    const extra = entered.reduce((a, r) => a + Math.max(0, (counts[r.item_id] ?? 0) - r.system), 0)
    modal.confirm({
      title: 'Post this stock check?',
      content: `${entered.length} item(s) counted. ${short} pcs short will be marked missing; ${extra} pcs extra will be added back.`,
      onOk: () => submit.mutateAsync(entered.map((r) => ({ item_id: r.item_id, counted: counts[r.item_id]! }))),
    })
  }
  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      {can('stock.adjust') && (
        <Card size="small" title="Count available stock">
          <Space wrap style={{ marginBottom: 12 }}>
            <Select style={{ width: 260 }} placeholder="Choose warehouse" value={wh} onChange={(v) => { setWh(v); setCounts({}) }}
              options={whs.data?.filter((w) => w.mine).map((w) => ({ value: w.id, label: whLabel(w) }))} />
            <Button type="primary" disabled={!wh || !entered.length} loading={submit.isPending} onClick={confirm}>
              Post check ({entered.length})
            </Button>
          </Space>
          {wh && (
            <Table rowKey="item_id" size="small" pagination={false} loading={sys.isLoading} dataSource={rows} scroll={{ x: 600 }}
              columns={[
                { title: 'Item', dataIndex: 'code', render: (c, r) => <>{c} <Typography.Text type="secondary">{r.name}</Typography.Text></> },
                { title: 'System (available)', dataIndex: 'system', align: 'right' },
                { title: 'Counted', render: (_, r) => (
                  <InputNumber min={0} precision={0} value={counts[r.item_id] ?? null} placeholder="not counted"
                    onChange={(v) => setCounts((c) => ({ ...c, [r.item_id]: v }))} />) },
                { title: 'Variance', align: 'right', render: (_, r) => {
                  const c = counts[r.item_id]
                  if (c == null) return null
                  const v = c - r.system
                  return <Typography.Text type={v < 0 ? 'danger' : v > 0 ? 'warning' : 'success'}>{v > 0 ? `+${v}` : v}</Typography.Text>
                } },
              ]} />
          )}
        </Card>
      )}
      <Card size="small" title="Past stock checks">
        <Table rowKey="id" size="small" loading={history.isLoading} dataSource={history.data}
          expandable={{ expandedRowRender: (c) => (
            <Table rowKey="item_id" size="small" pagination={false} dataSource={c.lines} columns={[
              { title: 'Item', dataIndex: 'item_id', render: (id) => items.data?.find((i) => i.id === id)?.code },
              { title: 'System', dataIndex: 'system_qty', align: 'right' },
              { title: 'Counted', dataIndex: 'counted_qty', align: 'right' },
              { title: 'Variance', dataIndex: 'variance', align: 'right' },
            ]} />) }}
          columns={[
            { title: 'Ref', dataIndex: 'ref_no' },
            { title: 'Warehouse', dataIndex: 'warehouse_id', render: (id) => whs.data?.find((w) => w.id === id)?.code },
            { title: 'When', dataIndex: 'counted_at', render: dt },
            { title: 'Short', render: (_, c) => c.lines.reduce((a, l) => a + Math.max(0, -l.variance), 0), align: 'right' },
            { title: 'Extra', render: (_, c) => c.lines.reduce((a, l) => a + Math.max(0, l.variance), 0), align: 'right' },
          ]} />
      </Card>
    </Space>
  )
}

export default function StockPage() {
  const { can } = useAuth()
  const tabs = [
    { key: 'summary', label: 'Summary', children: <SummaryTab /> },
    { key: 'movements', label: 'Movements', children: <MovementsTab /> },
    { key: 'transfers', label: 'Transfers', children: <TransfersTab /> },
    { key: 'check', label: 'Stock check', children: <CheckTab /> },
    ...(can('stock.adjust') ? [{ key: 'opening', label: 'Opening stock', children: <OpeningTab /> }] : []),
  ]
  return (
    <>
      <Typography.Title level={3}>Stock</Typography.Title>
      <Tabs items={tabs} destroyInactiveTabPane={false} />
    </>
  )
}
