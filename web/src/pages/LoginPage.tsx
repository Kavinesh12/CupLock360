import { useState } from 'react'
import { Alert, Button, Card, Form, Input, Typography } from 'antd'
import { LockOutlined, UserOutlined } from '@ant-design/icons'
import { useAuth } from '../auth/AuthContext'
import type { OtpChallenge } from '../api/types'

export default function LoginPage() {
  const { startLogin, verifyOtp } = useAuth()
  const [challenge, setChallenge] = useState<OtpChallenge | null>(null)
  const [creds, setCreds] = useState<{ login: string; password: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [devOtp, setDevOtp] = useState<string | null>(null)

  const run = async (fn: () => Promise<void>) => {
    setBusy(true)
    setError(null)
    try { await fn() } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  return (
    <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', background: '#1f2937', padding: 16 }}>
      <Card style={{ width: '100%', maxWidth: 380 }}>
        <Typography.Title level={3} style={{ marginTop: 0 }}>CUPLOCK 360°</Typography.Title>
        <Typography.Paragraph type="secondary">
          {challenge ? `Enter the 6-digit OTP sent ${challenge.sent_to ? `to ${challenge.sent_to}` : `via ${challenge.channel}`}.`
            : 'Sign in with your username, phone or email.'}
        </Typography.Paragraph>
        {devOtp && challenge && <Alert type="info" message={`Dev OTP: ${devOtp}`} style={{ marginBottom: 16 }} />}
        {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
        {!challenge ? (
          <Form layout="vertical" onFinish={(v) => run(async () => { setChallenge(await startLogin(v.login, v.password)); setCreds(v) })}>
            <Form.Item name="login" label="Username, phone or email" rules={[{ required: true }]}>
              <Input prefix={<UserOutlined />} autoFocus autoComplete="username" />
            </Form.Item>
            <Form.Item name="password" label="Password" rules={[{ required: true }]}>
              <Input.Password prefix={<LockOutlined />} autoComplete="current-password" />
            </Form.Item>
            <Button type="primary" htmlType="submit" block loading={busy}>Continue</Button>
          </Form>
        ) : (
          <Form layout="vertical" onFinish={(v) => run(() => verifyOtp(challenge.challenge_id, v.code))}>
            <Form.Item name="code" label="OTP" rules={[{ required: true, len: 6 }]}>
              <Input.OTP length={6} autoFocus />
            </Form.Item>
            <Button type="primary" htmlType="submit" block loading={busy}>Verify and sign in</Button>
            <Button type="link" block disabled={busy}
              onClick={() => creds && run(async () => setChallenge(await startLogin(creds.login, creds.password)))}>
              Resend OTP
            </Button>
            <Button type="text" block onClick={() => { setChallenge(null); setError(null); setDevOtp(null) }}>Back</Button>
            {import.meta.env.DEV && challenge.channel === 'console' && (
              <Button type="dashed" block onClick={async () => {
                const box = await fetch('/api/v1/dev/otp-outbox').then((r) => r.json())
                setDevOtp(box[0]?.code ?? 'none yet')
              }}>Dev: show OTP</Button>
            )}
          </Form>
        )}
      </Card>
    </div>
  )
}
