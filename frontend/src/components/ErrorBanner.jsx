import React from 'react';
import { useLang } from '../i18n/LanguageContext';

export default function ErrorBanner({ message, onRetry }) {
  const { t } = useLang();
  message ??= t('Đã xảy ra lỗi khi kết nối với máy chủ.', 'Could not connect to the server.');
  return (
    <div className="bg-[#C92035]/10 border border-[#C92035]/20 rounded-xl p-4 my-4 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <div className="text-[#C92035]">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        </div>
        <div>
          <h4 className="text-[13px] font-bold text-[#C92035] uppercase tracking-wider">{t('Lỗi hệ thống', 'System error')}</h4>
          <p className="text-[12px] text-[#C92035] mt-1 font-mono">{message}</p>
        </div>
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="px-4 py-2 bg-[#C92035] text-white text-[12px] font-bold rounded-lg hover:bg-opacity-90 transition-colors"
        >
          {t('Thử lại', 'Retry')}
        </button>
      )}
    </div>
  );
}
