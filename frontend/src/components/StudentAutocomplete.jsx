import { useState, useRef, useEffect } from 'react';

/**
 * Feature 5: Student/vehicle autocomplete search.
 * Props:
 *   vehicles: array from GET /api/vehicles (pre-fetched by parent)
 *   onSelect(vehicle): callback when user picks a result
 *   placeholder: input placeholder text
 *   className: optional outer wrapper class
 */
export default function StudentAutocomplete({
  vehicles = [],
  onSelect,
  placeholder = 'Tìm biển số, tên học sinh, lớp...',
  className = '',
}) {
  const [query, setQuery] = useState('');
  const [show, setShow] = useState(false);
  const ref = useRef(null);

  const q = query.trim().toLowerCase();

  const results = q.length < 1 ? [] : vehicles.filter((v) => (
    v.plate_number?.toLowerCase().includes(q) ||
    v.student_name?.toLowerCase().includes(q) ||
    v.student_class?.toLowerCase().includes(q)
  )).slice(0, 8);

  useEffect(() => {
    function handleClick(e) {
      if (ref.current && !ref.current.contains(e.target)) {
        setShow(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  function handleSelect(v) {
    setQuery('');
    setShow(false);
    onSelect?.(v);
  }

  return (
    <div ref={ref} className={`relative ${className}`}>
      <div className="flex items-center bg-[#f4f6f9] rounded-lg px-3 py-2 gap-2">
        <svg className="w-4 h-4 text-[#6b7280] shrink-0" viewBox="0 0 24 24" fill="none">
          <path d="M15 15l6 6m-11-4a7 7 0 110-14 7 7 0 010 14z"
            stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
        </svg>
        <input
          type="text"
          placeholder={placeholder}
          className="bg-transparent border-0 outline-none w-full font-mono text-[12px] text-[#374151] placeholder:text-[#9ca3af]"
          value={query}
          onChange={e => { setQuery(e.target.value); setShow(true); }}
          onFocus={() => setShow(true)}
        />
        {query && (
          <button
            type="button"
            onClick={() => { setQuery(''); setShow(false); }}
            className="text-[#9ca3af] hover:text-[#6b7280] text-[16px] leading-none"
          >
            ×
          </button>
        )}
      </div>

      {show && results.length > 0 && (
        <ul className="absolute top-full left-0 right-0 mt-1 bg-white border border-[#d1d5db] rounded-lg shadow-lg z-50 overflow-hidden">
          {results.map(v => (
            <li key={v.id}>
              <button
                type="button"
                className="w-full text-left px-3 py-2.5 hover:bg-[#f4f6f9] transition-colors"
                onClick={() => handleSelect(v)}
              >
                <span className="font-mono font-bold text-[12px] text-[#374151] mr-2">
                  {v.plate_number}
                </span>
                <span className="text-[11px] text-[#6b7280]">
                  {v.student_name} · {v.student_class}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {show && q.length >= 1 && results.length === 0 && (
        <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-[#d1d5db] rounded-lg shadow-lg z-50 px-3 py-2 text-[12px] text-[#9ca3af]">
          Không tìm thấy
        </div>
      )}
    </div>
  );
}
