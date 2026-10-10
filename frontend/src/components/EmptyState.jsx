import React from 'react';
import { useLang } from '../i18n/LanguageContext';

export default function EmptyState({ title, message, icon }) {
  const { t } = useLang();
  title ??= t('Không có dữ liệu', 'No data');
  message ??= t('Hiện chưa có bản ghi nào được tìm thấy.', 'No records found yet.');
  return (
    <div className="flex flex-col items-center justify-center p-12 text-center bg-white rounded-xl border border-[#d1d5db]">
      <div className="w-16 h-16 bg-[#EEF3F8] text-[#64748B] rounded-full flex items-center justify-center mb-4">
        {icon || (
          <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
          </svg>
        )}
      </div>
      <h3 className="text-lg font-bold text-[#123B6D] mb-1">{title}</h3>
      <p className="text-[13px] text-[#64748B] max-w-sm">{message}</p>
    </div>
  );
}
