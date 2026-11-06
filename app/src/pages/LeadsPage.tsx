import { useState } from 'react'
import {
  IonBackButton, IonButtons, IonContent, IonFab, IonFabButton, IonHeader, IonIcon, IonItem, IonLabel, IonList, IonNote,
  IonPage, IonRefresher, IonRefresherContent, IonSearchbar, IonSegment, IonSegmentButton, IonTitle, IonToolbar,
  useIonViewWillEnter,
} from '@ionic/react'
import { add } from 'ionicons/icons'
import { api, fmt, type Lead, type Me } from '../api/client'

type View = 'due' | 'open' | 'all'

export default function LeadsPage({ me }: { me: Me }) {
  const [view, setView] = useState<View>('due')
  const [q, setQ] = useState('')
  const [leads, setLeads] = useState<Lead[]>([])
  const [error, setError] = useState<string | null>(null)

  const load = async (v: View = view, query: string = q) => {
    const p = new URLSearchParams()
    if (v === 'due') p.set('due', 'true')
    if (v === 'open') p.set('status', 'open')
    if (query) p.set('q', query)
    try { setLeads(await api<Lead[]>(`/leads?${p}`)); setError(null) } catch (e) { setError((e as Error).message) }
  }
  useIonViewWillEnter(() => { load() })

  const overdue = (l: Lead) => l.next_follow_up_at && new Date(l.next_follow_up_at) < new Date()
  return (
    <IonPage>
      <IonHeader>
        <IonToolbar color="primary">
          <IonButtons slot="start"><IonBackButton defaultHref="/home" /></IonButtons>
          <IonTitle>Leads</IonTitle>
        </IonToolbar>
        <IonToolbar>
          <IonSegment value={view} onIonChange={(e) => { const v = e.detail.value as View; setView(v); load(v) }}>
            <IonSegmentButton value="due"><IonLabel>Due today</IonLabel></IonSegmentButton>
            <IonSegmentButton value="open"><IonLabel>Open</IonLabel></IonSegmentButton>
            <IonSegmentButton value="all"><IonLabel>All</IonLabel></IonSegmentButton>
          </IonSegment>
        </IonToolbar>
        <IonToolbar>
          <IonSearchbar debounce={400} value={q} placeholder="Company, contact or phone"
            onIonInput={(e) => { const v = e.detail.value ?? ''; setQ(v); load(view, v) }} />
        </IonToolbar>
      </IonHeader>
      <IonContent>
        <IonRefresher slot="fixed" onIonRefresh={async (e) => { await load(); e.detail.complete() }}>
          <IonRefresherContent />
        </IonRefresher>
        {error && <IonNote color="danger" className="ion-padding">{error}</IonNote>}
        <IonList>
          {leads.map((l) => (
            <IonItem key={l.id} routerLink={`/leads/${l.id}`} detail>
              <IonLabel>
                <h2>{l.company_name}</h2>
                <p>{[l.contact_name, l.phone, l.city].filter(Boolean).join(' · ')}</p>
                {l.next_follow_up_at && <p style={{ color: overdue(l) ? 'var(--ion-color-danger)' : undefined }}>Next: {fmt(l.next_follow_up_at)}</p>}
              </IonLabel>
              <IonNote slot="end">{l.status}</IonNote>
            </IonItem>
          ))}
          {leads.length === 0 && !error && <IonItem><IonLabel color="medium">{view === 'due' ? 'Nothing due today.' : 'No leads.'}</IonLabel></IonItem>}
        </IonList>
        {me.permissions.includes('leads.manage') && (
          <IonFab slot="fixed" vertical="bottom" horizontal="end">
            <IonFabButton routerLink="/leads/new" aria-label="Add lead"><IonIcon icon={add} /></IonFabButton>
          </IonFab>
        )}
      </IonContent>
    </IonPage>
  )
}
