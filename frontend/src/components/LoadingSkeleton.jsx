import React from 'react';

export default function LoadingSkeleton({ type = 'table', rows = 5 }) {
  if (type === 'table') {
    return (
      <div className="bg-white rounded-xl shadow-sm border border-[#d1d5db] overflow-hidden">
        <div className="w-full text-left border-collapse min-w-full">
          <div className="bg-[#f4f6f9] py-3 px-4 h-10 border-b border-[#d1d5db]"></div>
          <div className="divide-y divide-[#f4f6f9]">
            {Array.from({ length: rows }).map((_, idx) => (
              <div key={idx} className="flex px-4 py-4 items-center gap-4 animate-pulse">
                <div className="h-4 bg-[#EEF3F8] rounded w-1/4"></div>
                <div className="h-4 bg-[#EEF3F8] rounded w-1/4"></div>
                <div className="h-4 bg-[#EEF3F8] rounded w-1/4"></div>
                <div className="h-4 bg-[#EEF3F8] rounded w-1/4"></div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="animate-pulse space-y-4">
      {Array.from({ length: rows }).map((_, idx) => (
        <div key={idx} className="h-10 bg-[#EEF3F8] rounded w-full"></div>
      ))}
    </div>
  );
}
