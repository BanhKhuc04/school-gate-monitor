import { useState } from 'react';
import client, { API_BASE_URL } from '../api/client';
import { useLang } from '../i18n/LanguageContext';
import LanguageToggle from '../components/LanguageToggle';

/**
 * UT8: Trang public đăng ký xe (không cần auth).
 *
 * Flow:
 *   1. User nhập mã số SV → backend tra roster (/api/register/lookup)
 *   2. Nếu hợp lệ → hiện form (biển số + ảnh + SĐT + ngày sinh)
 *      Tên/lớp auto-fill từ roster
 *   3. Submit → POST /api/register
 *
 * Trang này nằm NGOÀI RequireRole — frontend router đăng ký riêng.
 */
export default function PublicRegisterPage() {
  const { t } = useLang();
  const [studentId, setStudentId] = useState('');
  const [lookup, setLookup] = useState(null);  // kết quả lookup từ backend
  const [lookupError, setLookupError] = useState('');
  const [lookupLoading, setLookupLoading] = useState(false);
  const [plate, setPlate] = useState('');
  const [phone, setPhone] = useState('');
  const [dob, setDob] = useState('');
  const [photoFile, setPhotoFile] = useState(null);
  const [photoPreview, setPhotoPreview] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitResult, setSubmitResult] = useState(null);
  const [submitError, setSubmitError] = useState('');

  async function handleLookup(e) {
    e.preventDefault();
    setLookupError('');
    setLookup(null);
    setLookupLoading(true);
    try {
      const res = await client.get('/api/register/lookup', {
        params: { student_id: studentId.trim() },
      });
      if (!res.data.found) {
        setLookupError(t('Mã số không có trong danh sách hợp lệ. Vui lòng liên hệ quản trị.', 'This ID is not on the approved list. Please contact an administrator.'));
      } else if (res.data.already_registered) {
        setLookupError(t(`Mã số này đã đăng ký xe biển ${res.data.existing_plate}. Vui lòng liên hệ quản trị để thay đổi.`, `This ID already registered a bike with plate ${res.data.existing_plate}. Please contact an administrator to change it.`));
      } else {
        setLookup(res.data);
      }
    } catch (err) {
      setLookupError(t('Lỗi tra cứu: ', 'Lookup error: ') + (err.response?.data?.detail || err.message));
    } finally {
      setLookupLoading(false);
    }
  }

  function handlePhotoChange(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setPhotoFile(file);
    setPhotoPreview(URL.createObjectURL(file));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setSubmitError('');
    setSubmitResult(null);
    try {
      // Upload ảnh trước (nếu có chọn) qua endpoint public riêng, không cần JWT.
      let photo_path = null;
      if (photoFile) {
        const formData = new FormData();
        formData.append('file', photoFile);
        const uploadRes = await client.post('/api/register/upload-photo', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });
        photo_path = uploadRes.data.photo_path;
      }
      const res = await client.post('/api/register', {
        student_id: studentId.trim(),
        plate_number: plate.trim(),
        photo_path,
        dob: dob || null,
        phone: phone || null,
      });
      setSubmitResult(res.data);
    } catch (err) {
      setSubmitError(err.response?.data?.detail || err.message);
    } finally {
      setSubmitting(false);
    }
  }

  if (submitResult) {
    return (
      <div className="relative min-h-screen bg-[#f4f6f9] flex items-center justify-center p-6">
        <LanguageToggle className="absolute top-4 right-4" />
        <div className="bg-white rounded-xl p-6 shadow-sm border border-[#d1d5db] max-w-md w-full text-center">
          <div className="w-14 h-14 rounded-full bg-[#123B6D]/10 flex items-center justify-center mx-auto mb-3">
            <svg className="w-7 h-7 text-[#123B6D]" viewBox="0 0 24 24" fill="none">
              <path d="M5 13l4 4L19 7" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </div>
          <h2 className="text-lg font-bold text-[#374151] mb-2">{t('Đăng ký thành công!', 'Registration successful!')}</h2>
          <p className="text-[13px] text-[#6b7280] mb-1">
            {t('Xe biển số', 'Bike plate')} <span className="font-mono font-bold text-[#374151]">{submitResult.plate_number}</span>
          </p>
          <p className="text-[13px] text-[#6b7280]">
            {t('Học sinh:', 'Student:')} <span className="font-semibold text-[#374151]">{submitResult.student_name}</span> · {t('Lớp', 'Class')} {submitResult.student_class}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="relative min-h-screen bg-[#f4f6f9] p-6">
      <LanguageToggle className="absolute top-4 right-4" />
      <div className="max-w-md mx-auto">
        <h1 className="text-xl font-bold text-[#374151] mb-1 text-center">{t('Đăng ký xe', 'Bike registration')}</h1>
        <p className="text-[12px] text-[#6b7280] text-center mb-6">
          {t('Nhập mã số học sinh để bắt đầu. Mã số phải có trong danh sách được nhà trường cung cấp.', 'Enter your student ID to start. The ID must be on the list provided by the school.')}
        </p>

        {!lookup && (
          <form onSubmit={handleLookup} className="bg-white rounded-xl p-5 shadow-sm border border-[#d1d5db]">
            <label className="block text-[12px] font-mono font-semibold text-[#374151] uppercase mb-2">
              {t('Mã số học sinh', 'Student ID')}
            </label>
            <input
              type="text"
              value={studentId}
              onChange={e => setStudentId(e.target.value.toUpperCase())}
              placeholder={t('VD: HS2025001', 'e.g. HS2025001')}
              required
              className="w-full bg-[#f4f6f9] rounded-lg px-3 py-2 text-[14px] font-mono font-bold text-[#374151] uppercase border border-[#d1d5db] outline-none focus:ring-2 focus:ring-[#123b6d] tracking-wider"
            />
            {lookupError && (
              <p className="mt-3 text-[12px] text-[#c92035] font-mono">{lookupError}</p>
            )}
            <button
              type="submit"
              disabled={lookupLoading}
              className="mt-4 w-full bg-[#123b6d] hover:bg-[#0d2a4f] disabled:opacity-50 text-white text-[13px] font-semibold py-2.5 px-4 rounded-lg transition-colors"
            >
              {lookupLoading ? t('Đang kiểm tra...', 'Checking...') : t('Tiếp tục', 'Continue')}
            </button>
          </form>
        )}

        {lookup && (
          <form onSubmit={handleSubmit} className="bg-white rounded-xl p-5 shadow-sm border border-[#d1d5db] space-y-3">
            <div className="bg-[#123B6D]/10 border border-[#123B6D]/20 rounded-lg p-3 mb-2">
              <p className="text-[11px] font-mono text-[#123B6D] uppercase">{t('Học sinh', 'Student')}</p>
              <p className="text-[14px] font-bold text-[#374151]">{lookup.student_name}</p>
              <p className="text-[11px] text-[#6b7280]">{t('Lớp', 'Class')} {lookup.student_class} · {t('Mã số', 'ID')} {lookup.student_id}</p>
            </div>

            <div>
              <label className="block text-[11px] font-mono font-semibold text-[#6b7280] uppercase mb-1">
                {t('Biển số xe', 'Plate number')}
              </label>
              <input
                type="text"
                value={plate}
                onChange={e => setPlate(e.target.value.toUpperCase())}
                placeholder="29MD-123.45"
                required
                className="w-full bg-[#f4f6f9] rounded-lg px-3 py-2 text-[13px] font-mono font-bold text-[#374151] uppercase border border-[#d1d5db] outline-none focus:ring-2 focus:ring-[#123b6d] tracking-wider"
              />
            </div>

            <div>
              <label className="block text-[11px] font-mono font-semibold text-[#6b7280] uppercase mb-1">
                {t('Ngày sinh', 'Date of birth')}
              </label>
              <input
                type="date"
                value={dob}
                onChange={e => setDob(e.target.value)}
                className="w-full bg-[#f4f6f9] rounded-lg px-3 py-2 text-[12px] font-mono text-[#374151] border border-[#d1d5db] outline-none"
              />
            </div>

            <div>
              <label className="block text-[11px] font-mono font-semibold text-[#6b7280] uppercase mb-1">
                {t('Số điện thoại', 'Phone number')}
              </label>
              <input
                type="tel"
                value={phone}
                onChange={e => setPhone(e.target.value)}
                placeholder="0912345678"
                className="w-full bg-[#f4f6f9] rounded-lg px-3 py-2 text-[12px] font-mono text-[#374151] border border-[#d1d5db] outline-none"
              />
            </div>

            <div>
              <label className="block text-[11px] font-mono font-semibold text-[#6b7280] uppercase mb-1">
                {t('Ảnh mặt (tùy chọn)', 'Face photo (optional)')}
              </label>
              <input
                type="file"
                accept="image/*"
                onChange={handlePhotoChange}
                className="w-full text-[12px] text-[#374151]"
              />
              {photoPreview && (
                <img src={photoPreview} alt="preview" className="mt-2 h-24 rounded border border-[#d1d5db]" />
              )}
            </div>

            {submitError && (
              <p className="text-[12px] text-[#c92035] font-mono bg-[#C92035]/10 border border-[#C92035]/20 rounded-lg p-2">{submitError}</p>
            )}

            <button
              type="submit"
              disabled={submitting}
              className="w-full bg-[#123B6D] hover:bg-[#123B6D] disabled:opacity-50 text-white text-[13px] font-semibold py-2.5 px-4 rounded-lg transition-colors"
            >
              {submitting ? t('Đang gửi...', 'Submitting...') : t('Gửi đăng ký', 'Submit registration')}
            </button>
            <button
              type="button"
              onClick={() => { setLookup(null); setPlate(''); setPhone(''); setDob(''); setPhotoFile(null); setPhotoPreview(null); }}
              className="w-full bg-[#f4f6f9] hover:bg-[#eceff3] text-[#6b7280] text-[12px] font-medium py-2 px-4 rounded-lg transition-colors"
            >
              ← {t('Đổi mã số khác', 'Use a different ID')}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}