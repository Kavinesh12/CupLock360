import { useState } from 'react'
import {
  IonBadge, IonButton, IonButtons, IonCard, IonCardContent, IonCardHeader, IonCardSubtitle, IonCardTitle, IonContent,
  IonHeader, IonIcon, IonItem, IonLabel, IonList, IonPage, IonTitle, IonToolbar, useIonViewWillEnter,
} from '@ionic/react'
import { logOutOutline } from 'ionicons/icons'
import { api, type Lead, type Me } from '../api/client'

const MODULES = [
  { label: 'Leads & follow-ups', perm: 'leads.view', path: '/leads' },
  { label: 'Stock lookup', perm: 'stock.view', path: '/stock' },
  { label: 'Approvals (OTP)', perm: 'requests.approve', day: 4 },
  { label: 'Dispatch & site receipt', perm: 'dispatch.manage', day: 4 },
  { label: 'Returns & damage photos', perm: 'dispatch.manage', day: 5 },
  { label: 'Dues', perm: 'billing.view', day: 5 },
  { label: 'Owner dashboard', perm: 'dashboard.view', day: 6 },
  { label: 'My statements', perm: 'portal.self', day: 6 },
]

export default function HomePage({ me, onLogout }: { me: Me; onLogout: () => void }) {
  const [due, setDue] = useState<number | null>(null)
  const canLeads = me.permissions.includes('leads.view')
  useIonViewWillEnter(() => {
    if (canLeads) api<Lead[]>('/leads?due=true&mine=true').then((r) => setDue(r.length)).catch(() => setDue(null))
  })
  const mine = MODULES.filter((m) => me.permissions.includes(m.perm))
  return (
    <IonPage>
      <IonHeader>
        <IonToolbar color="primary">
          <IonTitle>CUPLOCK 360°</IonTitle>
          <IonButtons slot="end">
            <IonButton onClick={onLogout} aria-label="Log out"><IonIcon slot="icon-only" icon={logOutOutline} /></IonButton>
          </IonButtons>
        </IonToolbar>
      </IonHeader>
      <IonContent className="ion-padding">
        <IonCard>
          <IonCardHeader>
            <IonCardSubtitle>Welcome</IonCardSubtitle>
            <IonCardTitle>{me.full_name}</IonCardTitle>
          </IonCardHeader>
          <IonCardContent>
            {me.roles.join(', ')}
            {me.approval_limit != null && <> · approves up to ₹{me.approval_limit.toLocaleString('en-IN')}</>}
          </IonCardContent>
        </IonCard>
        {canLeads && due != null && due > 0 && (
          <IonCard color="warning" routerLink="/leads" button>
            <IonCardContent><strong>{due} follow-up{due > 1 ? 's' : ''} due today</strong> · tap to see</IonCardContent>
          </IonCard>
        )}
        <IonList>
          {mine.map((m) => (
            <IonItem key={m.label} routerLink={m.path} disabled={!m.path} detail={!!m.path}>
              <IonLabel>{m.label}</IonLabel>
              {m.day && <IonBadge slot="end" color="warning">Day {m.day}</IonBadge>}
            </IonItem>
          ))}
          {mine.length === 0 && <IonItem><IonLabel>No mobile modules for your role yet.</IonLabel></IonItem>}
        </IonList>
      </IonContent>
    </IonPage>
  )
}
