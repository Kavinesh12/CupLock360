import { useEffect } from 'react'
import { Col, Divider, Form, Input, InputNumber, Modal, Row, Select, Switch, Tag } from 'antd'
import { useBranches } from '../api/hooks'
import type { Client, CreditStatus } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { stateOptions } from '../format'

export const creditTag = (s: CreditStatus) =>
  <Tag color={s === 'approved' ? 'green' : s === 'hold' ? 'red' : 'gold'}>{s}</Tag>

interface Props {
  open: boolean
  initial?: Client
  saving: boolean
  onCancel: () => void
  onSubmit: (v: Partial<Client>) => void
}

export default function ClientForm({ open, initial, saving, onCancel, onSubmit }: Props) {
  const [form] = Form.useForm()
  const { can } = useAuth()
  const branches = useBranches()
  const credit = can('clients.credit')

  useEffect(() => {
    if (!open) return
    form.resetFields()
    form.setFieldsValue(initial ? { ...initial, credit_limit: Number(initial.credit_limit),
      security_deposit: Number(initial.security_deposit) }
      : { state_code: '33', payment_terms_days: 30, credit_status: 'pending', is_active: true })
  }, [open, initial, form])

  const submit = (v: Record<string, unknown>) => {
    const clean = Object.fromEntries(Object.entries(v).map(([k, x]) => [k, x === '' ? null : x]))
    if (!credit) for (const f of ['payment_terms_days', 'credit_limit', 'security_deposit', 'credit_status']) delete clean[f]
    onSubmit(clean as Partial<Client>)
  }

  return (
    <Modal open={open} title={initial ? `Edit ${initial.code}` : 'Add client'} onCancel={onCancel} onOk={() => form.submit()}
      confirmLoading={saving} width={720} forceRender>
      <Form form={form} name="form_clientform" layout="vertical" onFinish={submit}>
        <Row gutter={16}>
          <Col xs={24} md={16}><Form.Item name="name" label="Company name" rules={[{ required: true, min: 2 }]}><Input /></Form.Item></Col>
          <Col xs={24} md={8}>
            <Form.Item name="branch_id" label="Home branch" rules={[{ required: true }]}>
              <Select options={branches.data?.map((b) => ({ value: b.id, label: b.name }))} />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item name="gstin" label="GSTIN" normalize={(v: string) => v?.toUpperCase()}
              rules={[{ pattern: /^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/, message: 'Invalid GSTIN' }]}>
              <Input maxLength={15} />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item name="pan" label="PAN" normalize={(v: string) => v?.toUpperCase()}
              rules={[{ pattern: /^[A-Z]{5}\d{4}[A-Z]$/, message: 'Invalid PAN' }]}><Input maxLength={10} /></Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item name="state_code" label="State (place of supply)" extra="Taken from GSTIN when given">
              <Select showSearch optionFilterProp="label" options={stateOptions} />
            </Form.Item>
          </Col>
          <Col span={24}><Form.Item name="billing_address" label="Billing address"><Input.TextArea rows={2} /></Form.Item></Col>
          <Col xs={24} md={8}><Form.Item name="contact_name" label="Contact person"><Input /></Form.Item></Col>
          <Col xs={24} md={8}>
            <Form.Item name="phone" label="Mobile" rules={[{ pattern: /^[6-9]\d{9}$/, message: '10-digit mobile' }]}><Input /></Form.Item>
          </Col>
          <Col xs={24} md={8}><Form.Item name="email" label="Email" rules={[{ type: 'email' }]}><Input /></Form.Item></Col>
        </Row>
        <Divider orientation="left" plain>Credit profile {!credit && '(set by accounts)'}</Divider>
        <Row gutter={16}>
          <Col xs={12} md={6}><Form.Item name="payment_terms_days" label="Terms (days)"><InputNumber min={0} max={365} disabled={!credit} style={{ width: '100%' }} /></Form.Item></Col>
          <Col xs={12} md={6}><Form.Item name="credit_limit" label="Credit limit (₹)"><InputNumber min={0} disabled={!credit} style={{ width: '100%' }} /></Form.Item></Col>
          <Col xs={12} md={6}><Form.Item name="security_deposit" label="Deposit (₹)"><InputNumber min={0} disabled={!credit} style={{ width: '100%' }} /></Form.Item></Col>
          <Col xs={12} md={6}>
            <Form.Item name="credit_status" label="Credit status">
              <Select disabled={!credit} options={['pending', 'approved', 'hold'].map((v) => ({ value: v, label: v }))} />
            </Form.Item>
          </Col>
          <Col span={24}><Form.Item name="notes" label="Notes"><Input.TextArea rows={2} /></Form.Item></Col>
          {initial && <Col span={24}><Form.Item name="is_active" label="Active" valuePropName="checked"><Switch /></Form.Item></Col>}
        </Row>
      </Form>
    </Modal>
  )
}
