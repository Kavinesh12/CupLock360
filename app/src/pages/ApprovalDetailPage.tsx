import { useState } from 'react'
import { useHistory, useParams } from 'react-router-dom'
import {
  IonBackButton, IonButton, IonButtons, IonCard, IonCardContent, IonContent, IonHeader, IonInput, IonItem, IonLabel, IonList,
  IonListHeader, IonNote, IonPage, IonText, IonTitle, IonToolbar, useIonAlert, useIonToast, useIonViewWillEnter,
} from '@ionic/react'
import { api, devOtp, inr, post, type ItemLite, type MatRequestDetail, type OtpChallenge } from '../api/client'

type Challenge = OtpChallenge & { estimate: { total: string } }

export default function ApprovalDetailPage() {
  const { id } = useParams<{ id: string }>()
  const history = useHistory()
  const [req, setReq] = useState<MatRequestDetail | null>(null)
  const [items, setItems] = useState<Record<number, ItemLite>>({})
  const [qty, setQty] = useState<Record<number, number>>({})
  const [challenge, setChallenge] = useState<Challenge | null>(null)
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [toast] = useIonToast()
  const [alert] = useIonAlert()
  const fail = (e: Error) => toast({ message: e.message, duration: 3000, color: 'danger' })

  useIonViewWillEnter(() => {
    setChallenge(null); setCode('')
    api<MatRequestDetail>(`/requests/${id}`).then((r) => {
      setReq(r)
      const av = new Map(r.availability.map((a) => [a.item_id, a.available ?? 0]))
      setQty(Object.fromEntries(r.lines.map((l) => [l.item_id, Math.min(l.qty_requested, av.get(l.item_id) ?? 0)])))
    }).catch(fail)
    api<ItemLite[]>('/items').then((r) => setItems(Object.fromEntries(r.map((i) => [i.id, i])))).catch(() => undefined)
  })
  const lines = req?.lines.map((l) => ({ item_id: l.item_id, qty: qty[l.item_id] ?? 0 })) ?? []
  const run = async (f: () => Promise<void>) => { setBusy(true); try { await f() } catch (e) { fail(e as Error) } finally { setBusy(false) } }
  const sendOtp = () => run(async () => { setChallenge(await post<Challenge>(`/requests/${id}/approval-otp`, { lines })); setCode('') })
  const approve = () => run(async () => {
    await post(`/requests/${id}/approve`, { challenge_id: challenge!.challenge_id, code, lines })
    toast({ message: `${req!.ref_no} approved; stock reserved`, duration: 2500, color: 'success' })
    history.replace('/approvals')
  })
  const reject = () => alert({
    header: `Reject ${req?.ref_no}?`, inputs: [{ name: 'reason', placeholder: 'Reason', type: 'textarea' }],
    buttons: ['Back', { text: 'Reject', role: 'destructive', handler: (v) => {
      run(async () => { await post(`/requests/${id}/reject`, { reason: v.reason }); history.replace('/approvals') })
    } }],
  })
  const av = new Map(req?.availability.map((a) => [a.item_id, a]))
  return (
    <IonPage>
      <IonHeader>
        <IonToolbar color="primary">
          <IonButtons slot="start"><IonBackButton defaultHref="/approvals" /></IonButtons>
          <IonTitle>{req?.ref_no ?? 'Request'}</IonTitle>
        </IonToolbar>
      </IonHeader>
      <IonContent>
        {req && (
          <>
            <IonCard>
              <IonCardContent>
                <h2><strong>{req.client_name}</strong></h2>
                <p>{req.site_name} · from {req.warehouse_code}</p>
                <p>{req.duration_days} days · needed {new Date(req.required_on).toLocaleDateString('en-IN')}</p>
                <p>Estimate <strong>{inr(req.est_total)}</strong> incl. GST</p>
                {req.client.credit_status === 'hold' && <IonText color="danger"><p>Client is on credit hold. It cannot be approved.</p></IonText>}
                {!req.can_approve && req.status === 'submitted' && <IonText color="warning"><p>You can't approve this one (your own request or above your limit).</p></IonText>}
              </IonCardContent>
            </IonCard>
            <IonList>
              <IonListHeader><IonLabel>Approve quantities</IonLabel></IonListHeader>
              {req.lines.map((l) => {
                const a = av.get(l.item_id)
                return (
                  <IonItem key={l.item_id}>
                    <IonLabel>
                      <h3>{items[l.item_id]?.code ?? l.item_id}</h3>
                      <p>Asked {l.qty_requested} · <IonText color={a?.short ? 'danger' : 'success'}>available {a?.available ?? '-'}</IonText></p>
                    </IonLabel>
                    <IonInput slot="end" type="number" inputmode="numeric" min={0} max={l.qty_requested} style={{ maxWidth: 90, textAlign: 'right' }}
                      disabled={!!challenge} value={qty[l.item_id]}
                      onIonInput={(e) => setQty((q) => ({ ...q, [l.item_id]: Math.min(l.qty_requested, Math.max(0, Number(e.detail.value) || 0)) }))} />
                  </IonItem>
                )
              })}
            </IonList>
            <div className="ion-padding">
              {req.can_approve && !challenge && (
                <>
                  <IonButton expand="block" disabled={busy} onClick={sendOtp}>Send approval OTP</IonButton>
                  <IonButton expand="block" fill="outline" color="danger" disabled={busy} onClick={reject}>Reject</IonButton>
                </>
              )}
              {challenge && (
                <>
                  <IonNote>Approving {inr(challenge.estimate.total)}. OTP sent{challenge.sent_to ? ` to ${challenge.sent_to}` : ''}; valid 5 minutes.</IonNote>
                  <IonItem>
                    <IonInput label="6-digit OTP" labelPlacement="stacked" inputmode="numeric" maxlength={6} value={code}
                      autocomplete="one-time-code" onIonInput={(e) => setCode(String(e.detail.value ?? ''))} />
                  </IonItem>
                  <IonButton expand="block" className="ion-margin-top" disabled={busy || code.length !== 6} onClick={approve}>Approve with OTP</IonButton>
                  <IonButton expand="block" fill="clear" disabled={busy} onClick={() => setChallenge(null)}>Change quantities</IonButton>
                  {challenge.channel === 'console' && (
                    <IonButton expand="block" fill="outline" color="warning" onClick={async () => setCode((await devOtp()) ?? '')}>Fill OTP (test mode)</IonButton>
                  )}
                </>
              )}
            </div>
          </>
        )}
      </IonContent>
    </IonPage>
  )
}
