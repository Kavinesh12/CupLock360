import { useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  IonBackButton, IonButton, IonButtons, IonCard, IonCardContent, IonContent, IonHeader,
  IonIcon, IonInput, IonItem, IonLabel, IonList, IonListHeader, IonNote, IonPage, IonSelect, IonSelectOption, IonText,
  IonTextarea, IonTitle, IonToolbar, useIonToast, useIonViewWillEnter,
} from '@ionic/react'
import { callOutline, logoWhatsapp } from 'ionicons/icons'
import { api, fmt, post, type LeadDetail, type Me } from '../api/client'

const CHANNELS = ['call', 'visit', 'whatsapp', 'email', 'meeting']

export default function LeadDetailPage({ me }: { me: Me }) {
  const { id } = useParams<{ id: string }>()
  const [lead, setLead] = useState<LeadDetail | null>(null)
  const [channel, setChannel] = useState('call')
  const [note, setNote] = useState('')
  const [status, setStatus] = useState('')
  const [next, setNext] = useState('')
  const [busy, setBusy] = useState(false)
  const [toast] = useIonToast()

  const load = () => api<LeadDetail>(`/leads/${id}`).then(setLead).catch((e) => toast({ message: e.message, duration: 2500, color: 'danger' }))
  useIonViewWillEnter(() => { load() })

  const save = async () => {
    setBusy(true)
    try {
      setLead(await post<LeadDetail>(`/leads/${id}/follow-ups`, { channel, note, status: status || undefined,
        next_follow_up_at: next ? new Date(next).toISOString() : null }))
      setNote(''); setStatus(''); setNext('')
      toast({ message: 'Follow-up saved', duration: 1500, color: 'success' })
    } catch (e) { toast({ message: (e as Error).message, duration: 2500, color: 'danger' }) } finally { setBusy(false) }
  }

  const open = lead && ['new', 'contacted', 'quoted'].includes(lead.status)
  return (
    <IonPage>
      <IonHeader>
        <IonToolbar color="primary">
          <IonButtons slot="start"><IonBackButton defaultHref="/leads" /></IonButtons>
          <IonTitle>{lead?.company_name ?? 'Lead'}</IonTitle>
        </IonToolbar>
      </IonHeader>
      <IonContent className="ion-padding">
        {lead && <>
          <IonCard>
            <IonCardContent>
              <p><strong>{lead.contact_name}</strong> {lead.city && `· ${lead.city}`}</p>
              {lead.requirement && <p>{lead.requirement}</p>}
              <p>Status: <strong>{lead.status}</strong>{lead.next_follow_up_at && ` · next ${fmt(lead.next_follow_up_at)}`}</p>
              {lead.phone && (
                <div className="ion-margin-top">
                  <IonButton size="small" href={`tel:${lead.phone}`}><IonIcon slot="start" icon={callOutline} />Call</IonButton>
                  <IonButton size="small" color="success" href={`https://wa.me/91${lead.phone}`} target="_blank">
                    <IonIcon slot="start" icon={logoWhatsapp} />WhatsApp</IonButton>
                </div>
              )}
            </IonCardContent>
          </IonCard>

          {open && me.permissions.includes('leads.manage') && (
            <IonList>
              <IonListHeader><IonLabel>Log follow-up</IonLabel></IonListHeader>
              <IonItem>
                <IonSelect label="How" value={channel} onIonChange={(e) => setChannel(e.detail.value)}>
                  {CHANNELS.map((c) => <IonSelectOption key={c} value={c}>{c}</IonSelectOption>)}
                </IonSelect>
              </IonItem>
              <IonItem><IonTextarea label="What happened" labelPlacement="stacked" autoGrow value={note} onIonInput={(e) => setNote(e.detail.value ?? '')} /></IonItem>
              <IonItem>
                <IonSelect label="Move to" value={status} placeholder="(no change)" onIonChange={(e) => setStatus(e.detail.value)}>
                  <IonSelectOption value="">(no change)</IonSelectOption>
                  <IonSelectOption value="contacted">contacted</IonSelectOption>
                  <IonSelectOption value="quoted">quoted</IonSelectOption>
                </IonSelect>
              </IonItem>
              <IonItem>
                <IonInput type="datetime-local" label="Next follow-up" labelPlacement="stacked" value={next}
                  onIonInput={(e) => setNext(String(e.detail.value ?? ''))} />
              </IonItem>
              <IonButton expand="block" className="ion-margin" disabled={busy || !note.trim()} onClick={save}>Save follow-up</IonButton>
            </IonList>
          )}

          <IonList>
            <IonListHeader><IonLabel>History</IonLabel></IonListHeader>
            {lead.follow_ups.map((f) => (
              <IonItem key={f.id}>
                <IonLabel className="ion-text-wrap">
                  <h3>{f.channel} · {fmt(f.at)}</h3>
                  <p>{f.note}</p>
                </IonLabel>
              </IonItem>
            ))}
            {lead.follow_ups.length === 0 && <IonItem><IonNote>No follow-ups yet.</IonNote></IonItem>}
          </IonList>
          {lead.status === 'won' && <IonText color="success"><p>Converted to a client.</p></IonText>}
        </>}
      </IonContent>
    </IonPage>
  )
}
