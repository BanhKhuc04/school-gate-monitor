import { useState, useEffect } from 'react';
import {
  BarChart, Bar, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import client from '../api/client';
import { violationLabel } from '../utils/violationLabels';
import { useLang } from '../i18n/LanguageContext';

// Short day/month label for the trend chart x-axis (e.g. "2026-09-27" → "27/9").
function shortDate(isoDate) {
  const [, m, d] = isoDate.split('-');
  return `${parseInt(d, 10)}/${parseInt(m, 10)}`;
}

export default function DashboardPage() {
  const { lang, t } = useLang();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [passages, setPassages] = useState(null);

  useEffect(() => {
    client.get('/api/stats/summary')
      .then(res => setStats(res.data))
      .catch(() => setStats(null))
      .finally(() => setLoading(false));
    // Lượt vào/ra theo người (cả 2 chiều) — lỗi thì chỉ ẩn khối này.
    client.get('/api/stats/passages')
      .then(res => setPassages(res.data))
      .catch(() => setPassages(null));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <span className="text-on-surface-variant">{t('Đang tải...', 'Loading...')}</span>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="flex items-center justify-center h-64">
        <span className="text-secondary">{t('Không tải được dữ liệu.', 'Could not load data.')}</span>
      </div>
    );
  }

  const byTypeData = Object.entries(stats.by_type || {}).map(([type, count]) => ({
    name: violationLabel(type, lang),
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
          {t('Cụm phân tích an toàn AI', 'AI safety analytics')}
        </p>
        <h1 className="text-3xl font-bold text-on-surface mb-1">{t('Báo cáo & Thống kê', 'Reports & Statistics')}</h1>
        <p className="text-sm text-on-surface-variant mb-6">
          {t('Dữ liệu tổng hợp thời gian thực từ hệ thống camera cổng trường.', 'Real-time data aggregated from the school gate cameras.')}
        </p>

        {/* KPI cards — chỉ hiện số liệu có thật trong DB, không bịa % chưa đo được */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
          <div className="bg-surface rounded-lg shadow-sm border border-outline-variant p-5">
            <p className="text-xs uppercase tracking-wide text-on-surface-variant mb-1 font-mono">{t('Vi phạm hôm nay', 'Violations today')}</p>
            <p className="text-4xl font-bold text-secondary">{stats.total_today ?? 0}</p>
            <p className="text-xs text-on-surface-variant mt-1">{t('lượt ghi nhận', 'recorded')}</p>
          </div>
          <div className="bg-surface rounded-lg shadow-sm border border-outline-variant p-5">
            <p className="text-xs uppercase tracking-wide text-on-surface-variant mb-1 font-mono">{t('Vi phạm tuần này', 'Violations this week')}</p>
            <p className="text-4xl font-bold text-primary">{stats.total_week ?? 0}</p>
            <p className="text-xs text-on-surface-variant mt-1">{t('lượt ghi nhận, 7 ngày qua', 'recorded, last 7 days')}</p>
          </div>
          <div className="bg-surface rounded-lg shadow-sm border border-outline-variant p-5">
            <p className="text-xs uppercase tracking-wide text-on-surface-variant mb-1 font-mono">{t('Lỗi phổ biến nhất', 'Most common violation')}</p>
            <p className="text-2xl font-bold text-on-surface">{mostCommonType?.count ? mostCommonType.name : '—'}</p>
            <p className="text-xs text-on-surface-variant mt-1">
              {mostCommonType?.count ? `${mostCommonType.count} ${t('lượt', 'times')}` : t('chưa có dữ liệu', 'no data yet')}
            </p>
          </div>
        </div>

        {passages && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
            {[['enter', t('Lượt vào hôm nay', 'Entries today'), 'text-primary'], ['exit', t('Lượt ra hôm nay', 'Exits today'), 'text-on-surface']].map(([dir, label, color]) => {
              const p = passages[dir] || {};
              return (
                <div key={dir} className="bg-surface rounded-lg shadow-sm border border-outline-variant p-5">
                  <p className="text-xs uppercase tracking-wide text-on-surface-variant mb-1 font-mono">{label}</p>
                  <p className={`text-4xl font-bold ${color}`}>{p.persons ?? 0}</p>
                  <p className="text-xs text-on-surface-variant mt-1">
                    {t('người', 'people')} · {p.vehicle ?? 0} {t('xe', 'bikes')} · {p.pedestrian ?? 0} {t('đi bộ', 'on foot')}
                    {p.review ? ` · ${p.review} ${t('cần xem lại', 'need review')}` : ''}
                  </p>
                </div>
              );
            })}
          </div>
        )}

        {/* Trend line — 14 ngày gần nhất */}
        <div className="bg-surface rounded-lg shadow-sm border border-outline-variant p-6 mb-6">
          <h2 className="text-base font-semibold text-on-surface mb-4">{t('Xu hướng 14 ngày gần nhất', 'Trend, last 14 days')}</h2>
          {trendData.some(d => d.count > 0) ? (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={trendData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
                <Tooltip />
                <Line type="monotone" dataKey="count" name={t('Số vi phạm', 'Violations')} stroke="#123b6d" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="text-center text-outline py-8">{t('Chưa có dữ liệu vi phạm trong 14 ngày qua.', 'No violation data in the last 14 days.')}</div>
          )}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Bar chart theo loại vi phạm */}
          <div className="bg-surface rounded-lg shadow-sm border border-outline-variant p-6">
            <h2 className="text-base font-semibold text-on-surface mb-4">{t('Phân bổ loại vi phạm', 'Violations by type')}</h2>
            {byTypeData.some(d => d.count > 0) ? (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={byTypeData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="name" tick={{ fontSize: 11 }} interval={0} angle={-20} textAnchor="end" height={60} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
                  <Tooltip />
                  <Bar dataKey="count" name={t('Số vi phạm', 'Violations')} fill="#c92035" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="text-center text-outline py-8">{t('Chưa có dữ liệu vi phạm.', 'No violation data yet.')}</div>
            )}
          </div>

          {/* Xếp hạng theo lớp */}
          <div className="bg-surface rounded-lg shadow-sm border border-outline-variant p-6">
            <h2 className="text-base font-semibold text-on-surface mb-4">{t('Vi phạm theo lớp', 'Violations by class')}</h2>
            {byClass.length > 0 ? (
              <div className="space-y-3">
                {byClass.slice(0, 8).map(({ class_name, count }) => (
                  <div key={class_name}>
                    <div className="flex justify-between text-sm mb-1">
                      <span className={class_name === 'Không xác định' ? 'text-outline italic' : 'text-on-surface'}>
                        {class_name === 'Không xác định' ? t('Không xác định', 'Unknown') : class_name}
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
              <div className="text-center text-outline py-8">{t('Chưa có dữ liệu.', 'No data yet.')}</div>
            )}
            {byClass.some(c => c.class_name === 'Không xác định') && (
              <p className="text-xs text-outline mt-4">
                {t('"Không xác định": vi phạm có biển số không khớp xe đã đăng ký.', '"Unknown": violations whose plate does not match a registered bike.')}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
