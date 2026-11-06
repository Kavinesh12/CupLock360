import { useState } from 'react'
import {
  IonButton, IonContent, IonInput, IonInputPasswordToggle, IonItem, IonList, IonNote, IonPage, IonText,
} from '@ionic/react'
import { post, tokens, type OtpChallenge, type Tokens } from '../api/client'
import { devOtp } from '../api/client'

export default function LoginPage({ onLoggedIn }: { onLoggedIn: () => Promise<void> }) {
  const [login, setLogin] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [challenge, setChallenge] = useState<OtpChallenge | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const run = async (fn: () => Promise<void>) => {
    setBusy(true); setError(null)
    try { await fn() } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  const sendOtp = () => run(async () => { setChallenge(await post<OtpChallenge>('/auth/login', { login, password })); setCode('') })
  const verify = () => run(async () => {
    await tokens.set(await post<Tokens>('/auth/verify-otp', { challenge_id: challenge!.challenge_id, code }))
    await onLoggedIn()
  })

  return (
    <IonPage>
      <IonContent className="ion-padding">
        <div className="login-wrap">
          <p className="brand">CUPLOCK 360°</p>
          <IonText color="medium">
            <p>{challenge ? `Enter the OTP sent ${challenge.sent_to ? `to ${challenge.sent_to}` : `via ${challenge.channel}`}.` : 'Sign in to continue'}</p>
          </IonText>
          {error && <IonText color="danger"><p role="alert">{error}</p></IonText>}
          {!challenge ? (
            <form onSubmit={(e) => { e.preventDefault(); sendOtp() }}>
              <IonList inset={false}>
                <IonItem>
                  <IonInput label="Username or phone" labelPlacement="stacked" value={login} autocomplete="username"
                    onIonInput={(e) => setLogin(String(e.detail.value ?? ''))} required />
                </IonItem>
                <IonItem>
                  <IonInput type="password" label="Password" labelPlacement="stacked" value={password} autocomplete="current-password"
                    onIonInput={(e) => setPassword(String(e.detail.value ?? ''))} required>
                    <IonInputPasswordToggle slot="end" />
                  </IonInput>
                </IonItem>
              </IonList>
              <IonButton expand="block" type="submit" className="ion-margin-top" disabled={busy || !login || !password}>Continue</IonButton>
            </form>
          ) : (
            <form onSubmit={(e) => { e.preventDefault(); verify() }}>
              <IonItem>
                <IonInput label="6-digit OTP" labelPlacement="stacked" inputmode="numeric" maxlength={6} value={code}
                  autocomplete="one-time-code" onIonInput={(e) => setCode(String(e.detail.value ?? ''))} />
              </IonItem>
              <IonNote className="ion-padding-start">Valid for 5 minutes, 3 attempts.</IonNote>
              <IonButton expand="block" type="submit" className="ion-margin-top" disabled={busy || code.length !== 6}>Verify and sign in</IonButton>
              <IonButton expand="block" fill="clear" disabled={busy} onClick={sendOtp}>Resend OTP</IonButton>
              <IonButton expand="block" fill="clear" color="medium" onClick={() => { setChallenge(null); setError(null) }}>Back</IonButton>
              {challenge.channel === 'console' && (
                <IonButton expand="block" fill="outline" color="warning" onClick={async () => setCode((await devOtp()) ?? '')}>Fill OTP (test mode)</IonButton>
              )}
            </form>
          )}
        </div>
      </IonContent>
    </IonPage>
  )
}
