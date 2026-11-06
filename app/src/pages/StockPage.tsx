import { useMemo, useState } from 'react'
import {
  IonBackButton, IonBadge, IonButtons, IonContent, IonHeader, IonItem, IonLabel, IonList, IonListHeader, IonModal, IonNote,
  IonPage, IonRefresher, IonRefresherContent, IonSearchbar, IonSelect, IonSelectOption, IonTitle, IonToolbar, IonButton,
  useIonViewWillEnter,
} from '@ionic/react'
import { api } from '../api/client'

type Row = { item_id: number; item_code: string; item_name: string; total: number } & Record<string, number | string>
type Wh = { id: number; code: string; name: string; mine: boolean }
type Loc = { location_type: string; location_name: string; status: string; qty: number }

const LABEL: Record<string, string> = {
  available: 'Available', reserved: 'Reserved', in_transit: 'In transit', at_site: 'At site', returned: 'Returned',
  inspection: 'Inspection', maintenance: 'Under repair', damaged: 'Damaged', missing: 'Missing',
}
const COLOR: Record<string, string> = { available: 'success', at_site: 'tertiary', damaged: 'danger', missing: 'danger', in_transit: 'primary' }

export default function StockPage() {
  const [rows, setRows] = useState<Row[]>([])
  const [whs, setWhs] = useState<Wh[]>([])
  const [wh, setWh] = useState<number | 0>(0)
  const [q, setQ] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState<Row | null>(null)
  const [where, setWhere] = useState<Loc[]>([])

  const load = async (w = wh) => {
    try {
      setRows(await api<Row[]>(`/stock/summary${w ? `?warehouse_id=${w}` : ''}`))
      setError(null)
    } catch (e) { setError((e as Error).message) }
  }
  useIonViewWillEnter(() => {
    load()
    api<Wh[]>('/stock/warehouses').then((r) => setWhs(r.filter((x) => x.mine))).catch(() => undefined)
  })
  const show = async (r: Row) => {
    setOpen(r); setWhere([])
    setWhere(await api<Loc[]>(`/stock/by-location?item_id=${r.item_id}`).catch(() => []))
  }
  const shown = useMemo(() => {
    const t = q.trim().toLowerCase()
    return rows.filter((r) => !t || r.item_code.toLowerCase().includes(t) || r.item_name.toLowerCase().includes(t))
  }, [rows, q])

  return (
    <IonPage>
      <IonHeader>
        <IonToolbar color="primary">
          <IonButtons slot="start"><IonBackButton defaultHref="/home" /></IonButtons>
          <IonTitle>Stock lookup</IonTitle>
        </IonToolbar>
        <IonToolbar>
          <IonSearchbar value={q} onIonInput={(e) => setQ(e.detail.value ?? '')} placeholder="Item code or name" />
        </IonToolbar>
      </IonHeader>
      <IonContent>
        <IonRefresher slot="fixed" onIonRefresh={(e) => load().finally(() => e.detail.complete())}>
          <IonRefresherContent />
        </IonRefresher>
        <IonItem>
          <IonSelect label="Warehouse" value={wh} onIonChange={(e) => { setWh(e.detail.value); load(e.detail.value) }}>
            <IonSelectOption value={0}>All locations</IonSelectOption>
            {whs.map((w) => <IonSelectOption key={w.id} value={w.id}>{w.code} · {w.name}</IonSelectOption>)}
          </IonSelect>
        </IonItem>
        {error && <IonItem color="danger"><IonLabel>{error}</IonLabel></IonItem>}
        <IonList>
          {shown.map((r) => (
            <IonItem key={r.item_id} button detail onClick={() => show(r)}>
              <IonLabel>
                <h2>{r.item_code}</h2>
                <p>{r.item_name}</p>
                <p>Available {Number(r.available)} · At site {Number(r.at_site)} · Damaged {Number(r.damaged)}</p>
              </IonLabel>
              <IonNote slot="end"><strong>{r.total}</strong></IonNote>
            </IonItem>
          ))}
          {shown.length === 0 && !error && <IonItem><IonLabel>No stock found.</IonLabel></IonItem>}
        </IonList>
        <IonModal isOpen={!!open} onDidDismiss={() => setOpen(null)} initialBreakpoint={0.6} breakpoints={[0, 0.6, 1]}>
          <IonContent className="ion-padding">
            <IonListHeader><IonLabel><h2>{open?.item_code}</h2><p>{open?.item_name}</p></IonLabel></IonListHeader>
            <IonList>
              {where.map((l, i) => (
                <IonItem key={i}>
                  <IonLabel><h3>{l.location_name}</h3><p>{l.location_type}</p></IonLabel>
                  <IonBadge slot="end" color={COLOR[l.status] ?? 'medium'}>{LABEL[l.status] ?? l.status} {l.qty}</IonBadge>
                </IonItem>
              ))}
            </IonList>
            <IonButton expand="block" fill="clear" onClick={() => setOpen(null)}>Close</IonButton>
          </IonContent>
        </IonModal>
      </IonContent>
    </IonPage>
  )
}
