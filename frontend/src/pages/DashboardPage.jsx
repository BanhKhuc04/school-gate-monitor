import { useState, useEffect } from 'react';
import {
  BarChart, Bar, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import client from '../api/client';
import { VIOLATION_LABELS } from '../utils/violationLabels';

// Short day/month label for the trend chart x-axis (e.g. "2026-09-27" → "27/9").
function shortDate(isoDate) {
  const [, m, d] = isoDate.split('-');
  return `${parseInt(d, 10)}/${parseInt(m, 10)}`;
}

export default function DashboardPage() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    client.get('/api/stats/summary')
      .then(res => setStats(res.data))
      .catch(() => setStats(null))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <span className="text-on-surface-variant">Đang tải...</span>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="flex items-center justify-center h-64">
        <span className="text-secondary">Không tải được dữ liệu.</span>
      </div>
    );
  }

  const byTypeData = Object.entries(stats.by_type || {}).map(([type, count]) => ({
    name: VIOLATION_LABELS[type] || type,
    count,
  }));

  const trendData = (stats.trend || []).map(({ date, count }) => ({
    date: shortDate(date),
    count,
  }));

  const byClass = stats.by_class || [];
  const maxClassCount = Math.max(1, ...byClass.map(c => c.count));

  const mostCommonType = byTypeData.reduce(
    (best, d) => (d.count > (best?.count ?? -1) ? d : best), null
  );

  return (
    <div className="min-h-screen bg-surface-container-low p-8">
      <div className="max-w-6xl mx-auto">
        <p className="font-mono text-xs uppercase tracking-wider text-secondary mb-1">
          Cụm phân tích an toàn AI
        </p>
        <h1 className="text-3xl font-bold text-on-surface mb-1">Báo cáo &amp; Thống kê</h1>
        <p className="text-sm text-on-surface-variant mb-6">
          Dữ liệu tổng hợp thời gian thực từ hệ thống camera cổng trường.
        </p>

        {/* KPI cards — chỉ hiện số liệu có thật trong DB, không bịa % chưa đo được */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
          <div className="bg-surface rounded-lg shadow-sm border border-outline-variant p-5">
            <p className="text-xs uppercase tracking-wide text-on-surface-variant mb-1 font-mono">Vi phạm hôm nay</p>
            <p className="text-4xl font-bold text-secondary">{stats.total_today ?? 0}</p>
            <p className="text-xs text-on-surface-variant mt-1">lượt ghi nhận</p>
          </div>
          <div className="bg-surface rounded-lg shadow-sm border border-outline-variant p-5">
            <p className="text-xs uppercase tracking-wide text-on-surface-variant mb-1 font-mono">Vi phạm tuần này</p>
            <p className="text-4xl font-bold text-primary">{stats.total_week ?? 0}</p>
            <p className="text-xs text-on-surface-variant mt-1">lượt ghi nhận, 7 ngày qua</p>
          </div>
          <div className="bg-surface rounded-lg shadow-sm border border-outline-variant p-5">
            <p className="text-xs uppercase tracking-wide text-on-surface-variant mb-1 font-mono">Lỗi phổ biến nhất</p>
            <p className="text-2xl font-bold text-on-surface">{mostCommonType?.count ? mostCommonType.name : '—'}</p>
            <p className="text-xs text-on-surface-variant mt-1">
              {mostCommonType?.count ? `${mostCommonType.count} lượt` : 'chưa có dữ liệu'}
            </p>
          </div>
        </div>

        {/* Trend line — 14 ngày gần nhất */}
        <div className="bg-surface rounded-lg shadow-sm border border-outline-variant p-6 mb-6">
          <h2 className="text-base font-semibold text-on-surface mb-4">Xu hướng 14 ngày gần nhất</h2>
          {trendData.some(d => d.count > 0) ? (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={trendData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
                <Tooltip />
                <Line type="monotone" dataKey="count" stroke="#123b6d" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="text-center text-outline py-8">Chưa có dữ liệu vi phạm trong 14 ngày qua.</div>
          )}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Bar chart theo loại vi phạm */}
          <div className="bg-surface rounded-lg shadow-sm border border-outline-variant p-6">
            <h2 className="text-base font-semibold text-on-surface mb-4">Phân bổ loại vi phạm</h2>
            {byTypeData.some(d => d.count > 0) ? (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={byTypeData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="name" tick={{ fontSize: 11 }} interval={0} angle={-20} textAnchor="end" height={60} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#c92035" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="text-center text-outline py-8">Chưa có dữ liệu vi phạm.</div>
            )}
          </div>

          {/* Xếp hạng theo lớp */}
          <div className="bg-surface rounded-lg shadow-sm border border-outline-variant p-6">
            <h2 className="text-base font-semibold text-on-surface mb-4">Vi phạm theo lớp</h2>
            {byClass.length > 0 ? (
              <div className="space-y-3">
                {byClass.slice(0, 8).map(({ class_name, count }) => (
                  <div key={class_name}>
                    <div className="flex justify-between text-sm mb-1">
                      <span className={class_name === 'Không xác định' ? 'text-outline italic' : 'text-on-surface'}>
                        {class_name}
                      </span>
                      <span className="text-on-surface-variant font-medium">{count}</span>
                    </div>
                    <div className="h-2 bg-surface-container rounded-full overflow-hidden">
                      <div
                        className="h-full bg-secondary rounded-full"
                        style={{ width: `${(count / maxClassCount) * 100}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center text-outline py-8">Chưa có dữ liệu.</div>
            )}
            {byClass.some(c => c.class_name === 'Không xác định') && (
              <p className="text-xs text-outline mt-4">
                "Không xác định": vi phạm có biển số không khớp xe đã đăng ký.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
