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
        <span className="text-gray-500">Đang tải...</span>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="flex items-center justify-center h-64">
        <span className="text-red-500">Không tải được dữ liệu.</span>
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

  return (
    <div className="min-h-screen bg-gray-100 p-6">
      <div className="max-w-5xl mx-auto">
        <h1 className="text-2xl font-bold text-gray-800 mb-6">Dashboard</h1>

        {/* KPI cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
          <div className="bg-white rounded-xl shadow-sm p-6">
            <p className="text-sm text-gray-500 mb-1">Vi phạm hôm nay</p>
            <p className="text-4xl font-bold text-blue-600">{stats.total_today ?? 0}</p>
          </div>
          <div className="bg-white rounded-xl shadow-sm p-6">
            <p className="text-sm text-gray-500 mb-1">Vi phạm tuần này</p>
            <p className="text-4xl font-bold text-orange-600">{stats.total_week ?? 0}</p>
          </div>
        </div>

        {/* Trend line — 14 ngày gần nhất */}
        <div className="bg-white rounded-xl shadow-sm p-6 mb-6">
          <h2 className="text-base font-semibold text-gray-700 mb-4">Xu hướng 14 ngày gần nhất</h2>
          {trendData.some(d => d.count > 0) ? (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={trendData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
                <Tooltip />
                <Line type="monotone" dataKey="count" stroke="#3b82f6" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="text-center text-gray-400 py-8">Chưa có dữ liệu vi phạm trong 14 ngày qua.</div>
          )}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Bar chart theo loại vi phạm */}
          <div className="bg-white rounded-xl shadow-sm p-6">
            <h2 className="text-base font-semibold text-gray-700 mb-4">Phân loại vi phạm</h2>
            {byTypeData.some(d => d.count > 0) ? (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={byTypeData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="name" tick={{ fontSize: 11 }} interval={0} angle={-20} textAnchor="end" height={60} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="text-center text-gray-400 py-8">Chưa có dữ liệu vi phạm.</div>
            )}
          </div>

          {/* Xếp hạng theo lớp */}
          <div className="bg-white rounded-xl shadow-sm p-6">
            <h2 className="text-base font-semibold text-gray-700 mb-4">Vi phạm theo lớp</h2>
            {byClass.length > 0 ? (
              <div className="space-y-3">
                {byClass.slice(0, 8).map(({ class_name, count }) => (
                  <div key={class_name}>
                    <div className="flex justify-between text-sm mb-1">
                      <span className={class_name === 'Không xác định' ? 'text-gray-400 italic' : 'text-gray-700'}>
                        {class_name}
                      </span>
                      <span className="text-gray-500 font-medium">{count}</span>
                    </div>
                    <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-orange-400 rounded-full"
                        style={{ width: `${(count / maxClassCount) * 100}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center text-gray-400 py-8">Chưa có dữ liệu.</div>
            )}
            {byClass.some(c => c.class_name === 'Không xác định') && (
              <p className="text-xs text-gray-400 mt-4">
                "Không xác định": vi phạm có biển số không khớp xe đã đăng ký.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
