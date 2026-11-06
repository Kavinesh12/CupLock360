import { useEffect, useState } from 'react'
import { useHistory } from 'react-router-dom'
import {
  IonBackButton, IonButton, IonButtons, IonContent, IonHeader, IonInput, IonItem,
  IonList, IonPage, IonSelect, IonSelectOption, IonText, IonTextarea, IonTitle, IonToolbar,
} from '@ionic/react'
import { api, post, type Branch, type Lead } from '../api/client'

const SOURCES = ['Referral', 'Walk-in', 'Phone call', 'Website', 'Site visit', 'Existing client', 'Other']

export default function LeadNewPage() {
  const history = useHistory()
  const [branches, setBranches] = useState<Branch[]>([])
  const [f, setF] = useState({ company_name: '', contact_name: '', phone: '', city: '', source: '', requirement: '',
    branch_id: 0, next: '' })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const set = (k: keyof typeof f) => (e: CustomEvent) => setF((x) => ({ ...x, [k]: e.detail.value ?? '' }))

  useEffect(() => {
    api<Branch[]>('/branches').then((b) => { setBranches(b); if (b[0]) setF((x) => ({ ...x, branch_id: x.branch_id || b[0].id })) })
      .catch(() => undefined)
  }, [])

  const save = async () => {
    setBusy(true); setError(null)
    try {
      const body = { company_name: f.company_name, contact_name: f.contact_name || null, phone: f.phone || null,
        city: f.city || null, source: f.source || null, requirement: f.requirement || null, branch_id: f.branch_id,
        next_follow_up_at: f.next ? new Date(f.next).toISOString() : null }
      const lead = await post<Lead>('/leads', body)
      history.replace(`/leads/${lead.id}`)
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  return (
    <IonPage>
      <IonHeader>
        <IonToolbar color="primary">
          <IonButtons slot="start"><IonBackButton defaultHref="/leads" /></IonButtons>
          <IonTitle>New lead</IonTitle>
        </IonToolbar>
      </IonHeader>
      <IonContent className="ion-padding">
        {error && <IonText color="danger"><p role="alert">{error}</p></IonText>}
        <IonList>
          <IonItem><IonInput label="Company *" labelPlacement="stacked" value={f.company_name} onIonInput={set('company_name')} /></IonItem>
          <IonItem><IonInput label="Contact person" labelPlacement="stacked" value={f.contact_name} onIonInput={set('contact_name')} /></IonItem>
          <IonItem><IonInput label="Mobile" labelPlacement="stacked" type="tel" inputmode="tel" maxlength={10} value={f.phone} onIonInput={set('phone')} /></IonItem>
          <IonItem><IonInput label="City" labelPlacement="stacked" value={f.city} onIonInput={set('city')} /></IonItem>
          <IonItem>
            <IonSelect label="Source" labelPlacement="stacked" value={f.source} onIonChange={set('source')}>
              {SOURCES.map((s) => <IonSelectOption key={s} value={s}>{s}</IonSelectOption>)}
            </IonSelect>
          </IonItem>
          {branches.length > 1 && (
            <IonItem>
              <IonSelect label="Branch" labelPlacement="stacked" value={f.branch_id} onIonChange={set('branch_id')}>
                {branches.map((b) => <IonSelectOption key={b.id} value={b.id}>{b.name}</IonSelectOption>)}
              </IonSelect>
            </IonItem>
          )}
          <IonItem><IonTextarea label="Requirement" labelPlacement="stacked" autoGrow value={f.requirement} onIonInput={set('requirement')} /></IonItem>
          <IonItem>
            <IonInput type="datetime-local" label="First follow-up" labelPlacement="stacked" value={f.next} onIonInput={set('next')} />
          </IonItem>
        </IonList>
        <IonButton expand="block" className="ion-margin-top" disabled={busy || f.company_name.length < 2 || !f.branch_id} onClick={save}>
          Save lead
        </IonButton>
      </IonContent>
    </IonPage>
  )
}
