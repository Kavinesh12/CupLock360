import { useState } from 'react'
import {
  IonBadge, IonButton, IonButtons, IonCard, IonCardContent, IonCardHeader, IonCardSubtitle, IonCardTitle, IonContent,
  IonHeader, IonIcon, IonItem, IonLabel, IonList, IonPage, IonTitle, IonToolbar, useIonViewWillEnter,
} from '@ionic/react'
import { logOutOutline } from 'ionicons/icons'
import { api, type Lead, type MatRequest, type Me } from '../api/client'

const MODULES: { label: string; perm: string | string[]; path?: string; day?: number }[] = [
  { label: 'Leads & follow-ups', perm: 'leads.view', path: '/leads' },
  { label: 'Stock lookup', perm: 'stock.view', path: '/stock' },
  { label: 'Approvals (OTP)', perm: 'requests.approve', path: '/approvals' },
  { label: 'Site receipt', perm: ['requests.create', 'dispatch.manage'], path: '/deliveries' },
  { label: 'Returns & damage photos', perm: 'dispatch.manage', day: 5 },
  { label: 'Dues', perm: 'billing.view', day: 5 },
  { label: 'Owner dashboard', perm: 'dashboard.view', day: 6 },
  { label: 'My statements', perm: 'portal.self', day: 6 },
]

export default function HomePage({ me, onLogout }: { me: Me; onLogout: () => void }) {
  const [due, setDue] = useState<number | null>(null)
  const [pending, setPending] = useState<MatRequest[]>([])
  const canApprove = me.permissions.includes('requests.approve')
  const canLeads = me.permissions.includes('leads.view')
  useIonViewWillEnter(() => {
    if (canLeads) api<Lead[]>('/leads?due=true&mine=true').then((r) => setDue(r.length)).catch(() => setDue(null))
    if (canApprove) api<MatRequest[]>('/requests?pending_my_approval=true').then(setPending).catch(() => setPending([]))
  })
  const mine = MODULES.filter((m) => [m.perm].flat().some((p) => me.permissions.includes(p)))
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
        {pending.length > 0 && (
          <IonCard color="tertiary" routerLink="/approvals" button>
            <IonCardContent><strong>{pending.length} request{pending.length > 1 ? 's' : ''} waiting for your approval</strong> · tap to approve with OTP</IonCardContent>
          </IonCard>
        )}
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
