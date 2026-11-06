import { useState } from 'react'
import {
  IonBackButton, IonBadge, IonButtons, IonContent, IonHeader, IonItem, IonLabel, IonList, IonNote, IonPage, IonRefresher,
  IonRefresherContent, IonTitle, IonToolbar, useIonViewWillEnter,
} from '@ionic/react'
import { api, inr, type MatRequest } from '../api/client'

export default function ApprovalsPage() {
  const [rows, setRows] = useState<MatRequest[]>([])
  const [error, setError] = useState<string | null>(null)
  const load = () => api<MatRequest[]>('/requests?pending_my_approval=true').then((r) => { setRows(r); setError(null) })
    .catch((e) => setError(e.message))
  useIonViewWillEnter(() => { load() })
  return (
    <IonPage>
      <IonHeader>
        <IonToolbar color="primary">
          <IonButtons slot="start"><IonBackButton defaultHref="/home" /></IonButtons>
          <IonTitle>Approvals</IonTitle>
        </IonToolbar>
      </IonHeader>
      <IonContent>
        <IonRefresher slot="fixed" onIonRefresh={(e) => load().finally(() => e.detail.complete())}><IonRefresherContent /></IonRefresher>
        {error && <IonItem color="danger"><IonLabel>{error}</IonLabel></IonItem>}
        <IonList>
          {rows.map((r) => (
            <IonItem key={r.id} routerLink={`/approvals/${r.id}`} detail>
              <IonLabel>
                <h2>{r.ref_no} · {r.client_name}</h2>
                <p>{r.site_name} · from {r.warehouse_code}</p>
                <p>{r.lines.reduce((a, l) => a + l.qty_requested, 0)} pcs · {r.duration_days} days · needed {new Date(r.required_on).toLocaleDateString('en-IN')}</p>
              </IonLabel>
              <IonNote slot="end"><strong>{inr(r.est_total)}</strong></IonNote>
              {r.version > 1 && <IonBadge slot="end" color="medium">v{r.version}</IonBadge>}
            </IonItem>
          ))}
          {rows.length === 0 && !error && <IonItem><IonLabel>Nothing waiting for your approval.</IonLabel></IonItem>}
        </IonList>
      </IonContent>
    </IonPage>
  )
}
