import {
  IonBadge, IonButton, IonButtons, IonCard, IonCardContent, IonCardHeader, IonCardSubtitle, IonCardTitle, IonContent,
  IonHeader, IonIcon, IonItem, IonLabel, IonList, IonPage, IonTitle, IonToolbar,
} from '@ionic/react'
import { logOutOutline } from 'ionicons/icons'
import type { Me } from '../api/client'

const MODULES = [
  { label: 'Leads & follow-ups', perm: 'leads.view', day: 2 },
  { label: 'Stock lookup', perm: 'stock.view', day: 3 },
  { label: 'Approvals (OTP)', perm: 'requests.approve', day: 4 },
  { label: 'Dispatch & site receipt', perm: 'dispatch.manage', day: 4 },
  { label: 'Returns & damage photos', perm: 'dispatch.manage', day: 5 },
  { label: 'Dues', perm: 'billing.view', day: 5 },
  { label: 'Owner dashboard', perm: 'dashboard.view', day: 6 },
  { label: 'My statements', perm: 'portal.self', day: 6 },
]

export default function HomePage({ me, onLogout }: { me: Me; onLogout: () => void }) {
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
        <IonList>
          {mine.map((m) => (
            <IonItem key={m.label} disabled>
              <IonLabel>{m.label}</IonLabel>
              <IonBadge slot="end" color="warning">Day {m.day}</IonBadge>
            </IonItem>
          ))}
          {mine.length === 0 && <IonItem><IonLabel>No mobile modules for your role yet.</IonLabel></IonItem>}
        </IonList>
      </IonContent>
    </IonPage>
  )
}
