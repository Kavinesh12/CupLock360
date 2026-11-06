import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Col, DatePicker, Descriptions, Empty, Form, Input, Modal, Progress, Row, Select, Space, Table, Tag, Typography } from 'antd'
import { EditOutlined, PlusOutlined } from '@ant-design/icons'
import { api, patch, post } from '../api/client'
import { useBranches, useUserLookup } from '../api/hooks'
import type { Client, ClientDetail, Project, Site } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { inr, stateOptions } from '../format'
import ClientForm, { creditTag } from '../components/ClientForm'

export default function ClientDetailPage() {
  const { id } = useParams()
  const { can } = useAuth()
  const { message } = App.useApp()
  const qc = useQueryClient()
  const branches = useBranches()
  const users = useUserLookup()
  const [editing, setEditing] = useState(false)
  const [projectModal, setProjectModal] = useState(false)
  const [siteFor, setSiteFor] = useState<Project | null>(null)
  const [pForm] = Form.useForm()
  const [sForm] = Form.useForm()
  const key = ['client', id]
  const client = useQuery({ queryKey: key, queryFn: () => api<ClientDetail>(`/clients/${id}`) })
  const refresh = () => { qc.invalidateQueries({ queryKey: key }); qc.invalidateQueries({ queryKey: ['clients'] }) }
  const onError = (e: Error) => message.error(e.message)

  const update = useMutation({ mutationFn: (v: Partial<Client>) => patch(`/clients/${id}`, v), onError,
    onSuccess: () => { message.success('Saved'); setEditing(false); refresh() } })
  const addProject = useMutation({ onError,
    mutationFn: (v: { name: string; start_date?: { format: (f: string) => string } }) =>
      post(`/clients/${id}/projects`, { name: v.name, start_date: v.start_date?.format('YYYY-MM-DD') }),
    onSuccess: () => { message.success('Project added'); setProjectModal(false); refresh() } })
  const addSite = useMutation({ onError,
    mutationFn: (v: Partial<Site>) => post(`/projects/${siteFor!.id}/sites`, v),
    onSuccess: () => { message.success('Site added'); setSiteFor(null); refresh() } })

  const c = client.data
  if (!c) return <Card loading={client.isLoading} />
  const manage = can('clients.manage')

  return (
    <>
      <Card title={<Space>{c.name}<Typography.Text type="secondary">{c.code}</Typography.Text>{!c.is_active && <Tag>Inactive</Tag>}</Space>}
        extra={manage && <Button icon={<EditOutlined />} onClick={() => setEditing(true)}>Edit</Button>} style={{ marginBottom: 16 }}>
        <Row gutter={24}>
          <Col xs={24} lg={14}>
            <Descriptions column={{ xs: 1, sm: 2 }} size="small">
              <Descriptions.Item label="Branch">{branches.data?.find((b) => b.id === c.branch_id)?.name}</Descriptions.Item>
              <Descriptions.Item label="GSTIN">{c.gstin ?? '—'}</Descriptions.Item>
              <Descriptions.Item label="State">{c.state} ({c.state_code})</Descriptions.Item>
              <Descriptions.Item label="Contact">{[c.contact_name, c.phone].filter(Boolean).join(' · ') || '—'}</Descriptions.Item>
              <Descriptions.Item label="Email">{c.email ?? '—'}</Descriptions.Item>
              <Descriptions.Item label="Address">{c.billing_address ?? '—'}</Descriptions.Item>
            </Descriptions>
          </Col>
          <Col xs={24} lg={10}>
            <Card size="small" title={<Space>Credit profile {creditTag(c.credit_status)}</Space>}>
              <Descriptions column={2} size="small">
                <Descriptions.Item label="Terms">{c.payment_terms_days} days</Descriptions.Item>
                <Descriptions.Item label="Credit limit">{inr(c.credit_limit)}</Descriptions.Item>
                <Descriptions.Item label="Deposit">{inr(c.security_deposit)}</Descriptions.Item>
                <Descriptions.Item label="Outstanding">₹0 <Typography.Text type="secondary">(Day 5)</Typography.Text></Descriptions.Item>
              </Descriptions>
              <Progress percent={0} size="small" format={() => 'Credit used 0%'} />
            </Card>
          </Col>
        </Row>
      </Card>

      <Card title="Projects & sites" extra={manage && <Button icon={<PlusOutlined />} onClick={() => { pForm.resetFields(); setProjectModal(true) }}>Add project</Button>}>
        {c.projects.length === 0 && <Empty description="No projects yet" />}
        {c.projects.map((p) => (
          <Card key={p.id} type="inner" size="small" style={{ marginBottom: 12 }}
            title={<Space>{p.name}<Typography.Text type="secondary">{p.code}</Typography.Text></Space>}
            extra={manage && <Button size="small" icon={<PlusOutlined />} onClick={() => { sForm.resetFields(); sForm.setFieldsValue({ state_code: '33' }); setSiteFor(p) }}>Add site</Button>}>
            <Table rowKey="id" size="small" pagination={false} dataSource={p.sites} scroll={{ x: 600 }}
              locale={{ emptyText: 'No sites yet' }}
              columns={[
                { title: 'Code', dataIndex: 'code', width: 90 },
                { title: 'Site', dataIndex: 'name' },
                { title: 'City', dataIndex: 'city' },
                { title: 'Manager', dataIndex: 'manager_user_id', render: (u: number | null) => users.data?.find((x) => x.id === u)?.full_name },
                { title: 'Phone', dataIndex: 'contact_phone' },
                { title: 'Stock at site', key: 'stock', render: () => <Typography.Text type="secondary">Day 3</Typography.Text> },
              ]} />
          </Card>
        ))}
      </Card>

      <ClientForm open={editing} initial={c} saving={update.isPending} onCancel={() => setEditing(false)} onSubmit={(v) => update.mutate(v)} />

      <Modal open={projectModal} title="Add project" onCancel={() => setProjectModal(false)} onOk={() => pForm.submit()} confirmLoading={addProject.isPending} forceRender>
        <Form form={pForm} name="pForm_clientdetailpage" layout="vertical" onFinish={(v) => addProject.mutate(v)}>
          <Form.Item name="name" label="Project name" rules={[{ required: true }]}><Input placeholder="e.g. Ring Road Flyover" /></Form.Item>
          <Form.Item name="start_date" label="Start date"><DatePicker style={{ width: '100%' }} /></Form.Item>
        </Form>
      </Modal>

      <Modal open={!!siteFor} title={`Add site to ${siteFor?.name ?? ''}`} onCancel={() => setSiteFor(null)} onOk={() => sForm.submit()} confirmLoading={addSite.isPending} forceRender>
        <Form form={sForm} name="sForm_clientdetailpage" layout="vertical" onFinish={(v) => addSite.mutate(v)}>
          <Form.Item name="name" label="Site name" rules={[{ required: true }]}><Input placeholder="e.g. Tower A" /></Form.Item>
          <Form.Item name="address" label="Address"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item name="city" label="City"><Input /></Form.Item>
          <Form.Item name="state_code" label="State"><Select showSearch optionFilterProp="label" options={stateOptions} /></Form.Item>
          <Form.Item name="manager_user_id" label="Site manager">
            <Select allowClear showSearch optionFilterProp="label" options={users.data?.map((u) => ({ value: u.id, label: u.full_name }))} />
          </Form.Item>
          <Form.Item name="contact_phone" label="Site phone" rules={[{ pattern: /^[6-9]\d{9}$/, message: '10-digit mobile' }]}><Input /></Form.Item>
        </Form>
      </Modal>
    </>
  )
}
