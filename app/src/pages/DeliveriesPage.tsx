import { useState } from 'react'
import {
  IonBackButton, IonButton, IonButtons, IonContent, IonHeader, IonInput, IonItem, IonLabel, IonList, IonListHeader, IonModal,
  IonPage, IonRefresher, IonRefresherContent, IonText, IonTitle, IonToolbar, useIonToast, useIonViewWillEnter,
} from '@ionic/react'
import { api, post, type DispatchRow, type ItemLite } from '../api/client'

export default function DeliveriesPage() {
  const [rows, setRows] = useState<DispatchRow[]>([])
  const [items, setItems] = useState<Record<number, ItemLite>>({})
  const [open, setOpen] = useState<DispatchRow | null>(null)
  const [got, setGot] = useState<Record<number, number>>({})
  const [receiver, setReceiver] = useState('')
  const [busy, setBusy] = useState(false)
  const [toast] = useIonToast()
  const load = () => api<DispatchRow[]>('/dispatches?status=in_transit').then(setRows)
    .catch((e) => toast({ message: e.message, duration: 2500, color: 'danger' }))
  useIonViewWillEnter(() => {
    load()
    api<ItemLite[]>('/items').then((r) => setItems(Object.fromEntries(r.map((i) => [i.id, i])))).catch(() => undefined)
  })
  const start = (d: DispatchRow) => { setOpen(d); setReceiver(''); setGot(Object.fromEntries(d.lines.map((l) => [l.item_id, l.qty]))) }
  const confirm = async () => {
    setBusy(true)
    try {
      const r = await post<DispatchRow>(`/dispatches/${open!.id}/receive`, {
        receiver_name: receiver, lines: open!.lines.map((l) => ({ item_id: l.item_id, received: got[l.item_id] ?? 0 })),
      })
      const short = r.lines.reduce((a, l) => a + (l.qty_short ?? 0), 0)
      toast({ message: `Receipt saved${short ? `; ${short} short` : ''}`, duration: 2500, color: 'success' })
      setOpen(null); load()
    } catch (e) { toast({ message: (e as Error).message, duration: 3000, color: 'danger' }) } finally { setBusy(false) }
  }
  return (
    <IonPage>
      <IonHeader>
        <IonToolbar color="primary">
          <IonButtons slot="start"><IonBackButton defaultHref="/home" /></IonButtons>
          <IonTitle>Site receipt</IonTitle>
        </IonToolbar>
      </IonHeader>
      <IonContent>
        <IonRefresher slot="fixed" onIonRefresh={(e) => load().finally(() => e.detail.complete())}><IonRefresherContent /></IonRefresher>
        <IonList>
          {rows.map((d) => (
            <IonItem key={d.id} button detail onClick={() => start(d)}>
              <IonLabel>
                <h2>{d.challan_no}</h2>
                <p>{d.site_name} · {d.request_ref}</p>
                <p>{d.vehicle_no ?? ''} · {d.lines.reduce((a, l) => a + l.qty, 0)} pcs · {new Date(d.dispatched_at).toLocaleString('en-IN')}</p>
              </IonLabel>
            </IonItem>
          ))}
          {rows.length === 0 && <IonItem><IonLabel>No deliveries on the way.</IonLabel></IonItem>}
        </IonList>
        <IonModal isOpen={!!open} onDidDismiss={() => setOpen(null)}>
          <IonHeader><IonToolbar><IonTitle>{open?.challan_no}</IonTitle>
            <IonButtons slot="end"><IonButton onClick={() => setOpen(null)}>Close</IonButton></IonButtons></IonToolbar></IonHeader>
          <IonContent>
            <IonList>
              <IonListHeader><IonLabel>Count what arrived</IonLabel></IonListHeader>
              {open?.lines.map((l) => (
                <IonItem key={l.item_id}>
                  <IonLabel><h3>{items[l.item_id]?.code ?? l.item_id}</h3><p>Sent {l.qty}</p></IonLabel>
                  <IonInput slot="end" type="number" inputmode="numeric" style={{ maxWidth: 90, textAlign: 'right' }} value={got[l.item_id]}
                    onIonInput={(e) => setGot((g) => ({ ...g, [l.item_id]: Math.min(l.qty, Math.max(0, Number(e.detail.value) || 0)) }))} />
                </IonItem>
              ))}
              <IonItem>
                <IonInput label="Received by (name)" labelPlacement="stacked" value={receiver} onIonInput={(e) => setReceiver(String(e.detail.value ?? ''))} />
              </IonItem>
            </IonList>
            <div className="ion-padding">
              <IonText color="medium"><p>Anything not received is marked short and followed up with the warehouse.</p></IonText>
              <IonButton expand="block" disabled={busy || receiver.trim().length < 2} onClick={confirm}>Confirm receipt</IonButton>
            </div>
          </IonContent>
        </IonModal>
      </IonContent>
    </IonPage>
  )
}
