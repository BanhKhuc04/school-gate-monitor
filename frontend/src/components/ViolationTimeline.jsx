import { formatDate } from '../utils/format';

/**
 * Feature 2+6: Vertical timeline component for violation audit log.
 * Props:
 *   entries: Array of { id, action, actor_username, note, created_at }
 *   STATUS_LABELS: Map of action -> display label
 *   compact: boolean — render a smaller version (for table rows)
 */
export default function ViolationTimeline({ entries = [], compact = false }) {
  if (!entries.length) {
    return (
      <p className="text-[11px] font-mono text-[#9ca3af] italic py-1">
        Chưa có lịch sử xử lý
      </p>
    );
  }

  // Action color map
  const ACTION_STYLES = {
    reviewed: { dot: 'bg-[#3b82f6]', text: 'text-[#1e40af]', bg: 'bg-[#dbeafe]' },
    resolved: { dot: 'bg-[#10b981]', text: 'text-[#065f46]', bg: 'bg-[#d1fae5]' },
    reopened: { dot: 'bg-[#ef4444]', text: 'text-[#991b1b]', bg: 'bg-[#fee2e2]' },
  };

  const ACTION_LABELS = {
    reviewed: 'Đã xem',
    resolved: 'Đã xử lý',
    reopened: 'Mở lại',
  };

  if (compact) {
    // Inline compact version for violation table rows
    return (
      <div className="flex items-center gap-1.5 flex-wrap">
        {entries.map((entry) => {
          const s = ACTION_STYLES[entry.action] || ACTION_STYLES.reviewed;
          return (
            <span
              key={entry.id}
              className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold ${s.bg} ${s.text}`}
              title={`${entry.actor_username} — ${formatDate(entry.created_at)}`}
            >
              <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${s.dot}`} />
              {ACTION_LABELS[entry.action] || entry.action}
            </span>
          );
        })}
      </div>
    );
  }

  // Full vertical timeline
  return (
    <div className="relative pl-5">
      {/* Vertical line */}
      <div className="absolute left-[7px] top-2 bottom-2 w-[2px] bg-[#d1d5db]" />

      <div className="space-y-3">
        {entries.map((entry) => {
          const s = ACTION_STYLES[entry.action] || ACTION_STYLES.reviewed;
          return (
            <div key={entry.id} className="relative flex items-start gap-3">
              {/* Dot */}
              <div className={`absolute -left-[5px] top-1 w-2.5 h-2.5 rounded-full border-2 border-white ${s.dot} shrink-0 z-10`} />

              <div className="flex-1 min-w-0">
                <div className="flex items-baseline gap-1.5 flex-wrap">
                  <span className="text-[12px] font-semibold text-[#374151] font-mono">
                    {entry.actor_username}
                  </span>
                  <span className="text-[12px] text-[#6b7280]">đã</span>
                  <span className={`text-[12px] font-semibold font-mono ${s.text}`}>
                    {ACTION_LABELS[entry.action] || entry.action}
                  </span>
                  {entry.note && (
                    <span className="text-[11px] text-[#6b7280] italic">
                      — {entry.note}
                    </span>
                  )}
                </div>
                <span className="text-[10px] font-mono text-[#9ca3af]">
                  {formatDate(entry.created_at)}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
