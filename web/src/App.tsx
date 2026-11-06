import { Navigate, Route, Routes } from 'react-router-dom'
import { Spin } from 'antd'
import { useAuth } from './auth/AuthContext'
import AppLayout from './components/AppLayout'
import LoginPage from './pages/LoginPage'
import HomePage from './pages/HomePage'
import UsersPage from './pages/UsersPage'
import RolesPage from './pages/RolesPage'
import BranchesPage from './pages/BranchesPage'
import AuditPage from './pages/AuditPage'
import ComingSoon from './pages/ComingSoon'
import ClientsPage from './pages/ClientsPage'
import ClientDetailPage from './pages/ClientDetailPage'
import ItemsPage from './pages/ItemsPage'
import LeadsPage from './pages/LeadsPage'
import { MENU } from './components/menu'

function Guard({ perm, children }: { perm?: string; children: JSX.Element }) {
  const { can } = useAuth()
  if (perm && !can(perm)) return <Navigate to="/" replace />
  return children
}

export default function App() {
  const { me, loading } = useAuth()
  if (loading) return <Spin fullscreen />
  if (!me) {
    return (
      <Routes>
        <Route path="*" element={<LoginPage />} />
      </Routes>
    )
  }
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<HomePage />} />
        <Route path="users" element={<Guard perm="users.view"><UsersPage /></Guard>} />
        <Route path="roles" element={<Guard perm="roles.view"><RolesPage /></Guard>} />
        <Route path="branches" element={<Guard perm="branches.view"><BranchesPage /></Guard>} />
        <Route path="clients" element={<Guard perm="clients.view"><ClientsPage /></Guard>} />
        <Route path="clients/:id" element={<Guard perm="clients.view"><ClientDetailPage /></Guard>} />
        <Route path="items" element={<Guard perm="items.view"><ItemsPage /></Guard>} />
        <Route path="leads" element={<Guard perm="leads.view"><LeadsPage /></Guard>} />
        <Route path="audit" element={<Guard perm="audit.view"><AuditPage /></Guard>} />
        {MENU.filter((m) => m.day).map((m) => (
          <Route key={m.key} path={m.key.slice(1)}
            element={<Guard perm={m.perm}><ComingSoon title={m.label} day={m.day!} /></Guard>} />
        ))}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
