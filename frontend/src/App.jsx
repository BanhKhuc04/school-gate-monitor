import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './auth/AuthContext';
import LoginPage from './pages/LoginPage';
import GuardPage from './pages/GuardPage';
import AdminVehiclesPage from './pages/AdminVehiclesPage';
import AdminViolationsPage from './pages/AdminViolationsPage';
import AdminUsersPage from './pages/AdminUsersPage';
import AdminHealthPage from './pages/AdminHealthPage';
import AdminRoiPage from './pages/AdminRoiPage';
import AdminCameraPage from './pages/AdminCameraPage';
import DashboardPage from './pages/DashboardPage';
import StudentViolationHistoryPage from './pages/StudentViolationHistoryPage';
import RequireRole from './auth/RequireRole';
import Layout from './components/Layout';

function AppRoutes() {
  const { user } = useAuth();

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      {/* Guard — security + admin + management (principal can view live camera too) */}
      <Route
        element={
          <RequireRole allow={['security', 'admin', 'management']}>
            <Layout>
              <GuardPage />
            </Layout>
          </RequireRole>
        }
      >
        <Route path="/guard" element={null} />
      </Route>

      {/* Admin + management (read-only view for management — enforced by page-level isAdmin checks + server 403s) */}
      <Route
        element={
          <RequireRole allow={['admin', 'management']}>
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
          <RequireRole allow={['admin', 'management']}>
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
              <AdminRoiPage />
            </Layout>
          </RequireRole>
        }
      >
        <Route path="/admin/roi" element={null} />
      </Route>

      <Route
        element={
          <RequireRole allow={['admin']}>
            <Layout>
              <AdminCameraPage />
            </Layout>
          </RequireRole>
        }
      >
        <Route path="/admin/camera" element={null} />
      </Route>

      {/* Feature 9: Teacher routes — reuse admin pages with server-side scope filtering */}
      <Route
        element={
          <RequireRole allow={['teacher']}>
            <Layout>
              <AdminViolationsPage />
            </Layout>
          </RequireRole>
        }
      >
        <Route path="/teacher/violations" element={null} />
      </Route>

      <Route
        element={
          <RequireRole allow={['teacher']}>
            <Layout>
              <AdminVehiclesPage />
            </Layout>
          </RequireRole>
        }
      >
        <Route path="/teacher/vehicles" element={null} />
      </Route>

      {/* Feature 2+6: Student violation history */}
      <Route
        element={
          <RequireRole allow={['admin']}>
            <Layout>
              <StudentViolationHistoryPage />
            </Layout>
          </RequireRole>
        }
      >
        <Route path="/admin/students/:vehicleId/violations" element={null} />
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
