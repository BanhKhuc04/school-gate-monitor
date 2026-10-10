# PATCH: Tích hợp 3 trang training vào frontend routing

> Trạng thái: PENDING_INTEGRATION (Task 1/2 đang giữ `frontend/src/App.jsx`,
> `frontend/src/components/Sidebar.jsx`).
> Khi Task 1/2 bàn giao hoặc cho phép, áp dụng hunk sau đây.

## File: frontend/src/App.jsx

### Thêm import (gần các AdminXxxPage imports):

```jsx
import DatasetManagerPage from './pages/DatasetManagerPage';
import TrainingJobsPage from './pages/TrainingJobsPage';
import CandidateComparePage from './pages/CandidateComparePage';
import BBoxEditorDemoPage from './pages/BBoxEditorDemoPage';
```

### Thêm route (sau admin/roster route, trước teacher route):

```jsx
      {/* Task 3 — training data & jobs & candidates (admin only) */}
      <Route
        element={
          <RequireRole allow={['admin']}>
            <Layout>
              <DatasetManagerPage />
            </Layout>
          </RequireRole>
        }
      >
        <Route path="/admin/training/datasets" element={null} />
      </Route>

      <Route
        element={
          <RequireRole allow={['admin']}>
            <Layout>
              <TrainingJobsPage />
            </Layout>
          </RequireRole>
        }
      >
        <Route path="/admin/training/jobs" element={null} />
      </Route>

      <Route
        element={
          <RequireRole allow={['admin']}>
            <Layout>
              <CandidateComparePage />
            </Layout>
          </RequireRole>
        }
      >
        <Route path="/admin/training/candidates" element={null} />
      </Route>

      <Route
        element={
          <RequireRole allow={['admin']}>
            <Layout>
              <BBoxEditorDemoPage />
            </Layout>
          </RequireRole>
        }
      >
        <Route path="/admin/training/bbox" element={null} />
      </Route>
```

## File: frontend/src/components/Sidebar.jsx

### Thêm vào admin links (sau roster link):

```jsx
  if (user.role === 'admin') {
    links.push({ to: '/admin/training/datasets', label: 'Dữ liệu huấn luyện', icon: 'shield' });
    links.push({ to: '/admin/training/jobs', label: 'Training jobs', icon: 'shield' });
    links.push({ to: '/admin/training/candidates', label: 'So sánh model', icon: 'shield' });
    links.push({ to: '/admin/training/bbox', label: 'Sửa bbox', icon: 'shield' });
  }
```

### Thêm icon nếu cần (trong object ICONS):

```jsx
  shield: 'M12 3l7 3v6c0 5-3.4 8.4-7 9-3.6-.6-7-4-7-9V6l7-3Z',
  // Dùng 'shield' đã có, hoặc thêm 'database':
  database: 'M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zm0 6c0 1.7 3.6 3 8 3s8-1.3 8-3V6c0 1.7-3.6 3-8 3s-8-1.3-8-3v6zm0 6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6c0 1.7-3.6 3-8 3s-8-1.3-8-3v6z',
```

## Kiểm tra sau khi áp dụng

1. `cd frontend && npm install` (đã có sẵn dependencies).
2. `npm run lint` — không có lỗi.
3. `npm run build` — thành công.
4. Login admin → Sidebar thấy 3 menu mới → click vào trang tương ứng.
5. Login teacher/security → KHÔNG thấy menu training (chỉ admin).

## Lưu ý

- 3 trang này gọi API mới (/api/training/*), chỉ tích hợp khi patch main.py đã apply.
- Nếu API chưa có → Sidebar menu có thể thêm trước (trang sẽ trả 401/403).