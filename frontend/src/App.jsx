import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { useAuth } from './auth/AuthContext';
import LoginPage from './pages/LoginPage';
import SettingsLayout from './components/SettingsLayout';
import ViolationsLayout from './components/ViolationsLayout';
import RequireRole from './auth/RequireRole';
import Layout from './components/Layout';

const GuardPage = lazy(() => import('./pages/GuardPage'));
const AdminVehiclesPage = lazy(() => import('./pages/AdminVehiclesPage'));
const AdminViolationsPage = lazy(() => import('./pages/AdminViolationsPage'));
const AdminUsersPage = lazy(() => import('./pages/AdminUsersPage'));
const AdminHealthPage = lazy(() => import('./pages/AdminHealthPage'));
const AdminRoiPage = lazy(() => import('./pages/AdminRoiPage'));
const AdminCameraPage = lazy(() => import('./pages/AdminCameraPage'));
const DashboardPage = lazy(() => import('./pages/DashboardPage'));
const StudentViolationHistoryPage = lazy(() => import('./pages/StudentViolationHistoryPage'));
const DatasetManagerPage = lazy(() => import('./pages/DatasetManagerPage'));
const TrainingJobsPage = lazy(() => import('./pages/TrainingJobsPage'));
const CandidateComparePage = lazy(() => import('./pages/CandidateComparePage'));
const BBoxEditorDemoPage = lazy(() => import('./pages/BBoxEditorDemoPage'));
const AccountSettingsPage = lazy(() => import('./pages/AccountSettingsPage'));
const AdvancedAiPage = lazy(() => import('./pages/AdvancedAiPage'));
const AiReviewPage = lazy(() => import('./pages/AiReviewPage'));
const KaggleExportPage = lazy(() => import('./pages/KaggleExportPage'));

function LegacyRedirect({ to }) {
  const { search, hash } = useLocation();
  return <Navigate to={to + search + hash} replace />;
}

function AppRoutes() {
  const { user } = useAuth();
  const defaultPage = { admin: '/guard', management: '/guard', security: '/guard', teacher: '/teacher/violations' };
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireRole allow={['security', 'admin', 'management', 'teacher']}><Layout /></RequireRole>}>
        <Route path="/guard" element={<RequireRole allow={['security', 'admin', 'management']}><GuardPage /></RequireRole>} />
        <Route path="/admin/vehicles" element={<RequireRole allow={['admin', 'management']}><AdminVehiclesPage /></RequireRole>} />
        <Route element={<RequireRole allow={['admin', 'management']}><ViolationsLayout /></RequireRole>}>
          <Route path="/admin/violations" element={<AdminViolationsPage />} />
          <Route path="/admin/violations/report" element={<DashboardPage />} />
        </Route>
        <Route path="/dashboard" element={<RequireRole allow={['admin', 'management']}><LegacyRedirect to="/admin/violations/report" /></RequireRole>} />
        <Route path="/teacher/violations" element={<RequireRole allow={['teacher']}><AdminViolationsPage /></RequireRole>} />
        <Route path="/teacher/vehicles" element={<RequireRole allow={['teacher']}><AdminVehiclesPage /></RequireRole>} />
        <Route path="/admin/students/:vehicleId/violations" element={<RequireRole allow={['admin']}><StudentViolationHistoryPage /></RequireRole>} />

        <Route path="/settings" element={<SettingsLayout />}>
          <Route index element={<AccountSettingsPage />} />
          <Route path="camera" element={<RequireRole allow={['admin']}><AdminCameraPage /></RequireRole>} />
          <Route path="roi" element={<RequireRole allow={['admin']}><AdminRoiPage /></RequireRole>} />
          <Route path="storage" element={<RequireRole allow={['admin']}><AdminHealthPage /></RequireRole>} />
          <Route path="users" element={<RequireRole allow={['admin']}><AdminUsersPage /></RequireRole>} />
          <Route path="ai" element={<RequireRole allow={['admin']}><AdvancedAiPage /></RequireRole>} />
          <Route path="ai/reviews" element={<RequireRole allow={['admin']}><AiReviewPage /></RequireRole>} />
          <Route path="ai/export" element={<RequireRole allow={['admin']}><KaggleExportPage /></RequireRole>} />
          <Route path="ai/datasets" element={<RequireRole allow={['admin']}><DatasetManagerPage /></RequireRole>} />
          <Route path="ai/jobs" element={<RequireRole allow={['admin']}><TrainingJobsPage /></RequireRole>} />
          <Route path="ai/models" element={<RequireRole allow={['admin']}><CandidateComparePage /></RequireRole>} />
          <Route path="ai/bbox" element={<RequireRole allow={['admin']}><BBoxEditorDemoPage /></RequireRole>} />
        </Route>
        {[
          ['/admin/camera', '/settings/camera'], ['/admin/roi', '/settings/roi'],
          ['/admin/health', '/settings/storage'], ['/admin/users', '/settings/users'],
          ['/admin/training/datasets', '/settings/ai/datasets'], ['/admin/training/jobs', '/settings/ai/jobs'],
          ['/admin/training/candidates', '/settings/ai/models'], ['/admin/training/bbox', '/settings/ai/bbox'],
        ].map(([from, to]) => <Route key={from} path={from} element={<RequireRole allow={['admin']}><LegacyRedirect to={to} /></RequireRole>} />)}
      </Route>
      <Route path="*" element={<Navigate to={user ? defaultPage[user.role] || '/login' : '/login'} replace />} />
    </Routes>
  );
}

export default function App() {
  return <BrowserRouter><Suspense fallback={<p role="status" className="p-6 text-sm">Đang tải trang…</p>}><AppRoutes /></Suspense></BrowserRouter>;
}
