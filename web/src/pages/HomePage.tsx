import { Card, Col, Descriptions, Row, Tag, Typography } from 'antd'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { MENU } from '../components/menu'

export default function HomePage() {
  const { me, can } = useAuth()
  const nav = useNavigate()
  if (!me) return null
  const modules = MENU.filter((m) => m.key !== '/' && (!m.perm || can(m.perm)))
  return (
    <>
      <Typography.Title level={3}>Welcome, {me.full_name}</Typography.Title>
      <Card style={{ marginBottom: 16 }}>
        <Descriptions column={{ xs: 1, sm: 2 }} size="small">
          <Descriptions.Item label="Roles">{me.roles.map((r) => <Tag key={r}>{r}</Tag>)}</Descriptions.Item>
          <Descriptions.Item label="Approval limit">
            {me.approval_limit == null ? 'None' : `₹${me.approval_limit.toLocaleString('en-IN')}`}
          </Descriptions.Item>
          <Descriptions.Item label="Data scope">
            {me.scopes.length ? me.scopes.map((s) => <Tag key={`${s.type}${s.id}`}>{s.type} #{s.id}</Tag>) : 'All'}
          </Descriptions.Item>
        </Descriptions>
      </Card>
      <Row gutter={[16, 16]}>
        {modules.map((m) => (
          <Col key={m.key} xs={24} sm={12} lg={8}>
            <Card hoverable onClick={() => nav(m.key)}>
              <Card.Meta avatar={m.icon} title={m.label}
                description={m.day ? <Tag color="orange">Arrives Day {m.day}</Tag> : <Tag color="green">Live</Tag>} />
            </Card>
          </Col>
        ))}
      </Row>
    </>
  )
}
