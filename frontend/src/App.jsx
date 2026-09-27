import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './auth/AuthContext';
import LoginPage from './pages/LoginPage';
import GuardPage from './pages/GuardPage';
import AdminVehiclesPage from './pages/AdminVehiclesPage';
import AdminViolationsPage from './pages/AdminViolationsPage';
import AdminUsersPage from './pages/AdminUsersPage';
import AdminHealthPage from './pages/AdminHealthPage';
import AdminFacesPage from './pages/AdminFacesPage';
import DashboardPage from './pages/DashboardPage';
import RequireRole from './auth/RequireRole';
import Layout from './components/Layout';

function LoginLayout({ children }) {
  return <>{children}</>;
}

function AppRoutes() {
  const { user } = useAuth();

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      {/* Authenticated routes wrapped in Layout + RequireRole */}
      <Route
        element={
          <RequireRole allow={['security', 'admin']}>
            <Layout>
              <GuardPage />
            </Layout>
          </RequireRole>
        }
      >
        <Route path="/guard" element={null} />
      </Route>

      <Route
        element={
          <RequireRole allow={['admin']}>
            <Layout>
              <AdminVehiclesPage />
            </Layout>
          </RequireRole>
        }
      >
        <Route path="/admin/vehicles" element={null} />
      </Route>

      <Route
        element={
          <RequireRole allow={['admin']}>
            <Layout>
              <AdminViolationsPage />
            </Layout>
          </RequireRole>
        }
      >
        <Route path="/admin/violations" element={null} />
      </Route>

      <Route
        element={
          <RequireRole allow={['admin']}>
            <Layout>
              <AdminUsersPage />
            </Layout>
          </RequireRole>
        }
      >
        <Route path="/admin/users" element={null} />
      </Route>

      <Route
        element={
          <RequireRole allow={['management', 'admin']}>
            <Layout>
              <DashboardPage />
            </Layout>
          </RequireRole>
        }
      >
        <Route path="/dashboard" element={null} />
      </Route>

      <Route
        element={
          <RequireRole allow={['admin']}>
            <Layout>
              <AdminHealthPage />
            </Layout>
          </RequireRole>
        }
      >
        <Route path="/admin/health" element={null} />
      </Route>

      <Route
        element={
          <RequireRole allow={['admin']}>
            <Layout>
              <AdminFacesPage />
            </Layout>
          </RequireRole>
        }
      >
        <Route path="/admin/faces" element={null} />
      </Route>

      {/* Default redirect */}
      <Route
        path="*"
        element={<Navigate to={user ? '/dashboard' : '/login'} replace />}
      />
    </Routes>
  );
}

function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}

export default App;
