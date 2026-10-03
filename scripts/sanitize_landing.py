#!/usr/bin/env python
"""One-shot landing.html sanitizer: replaces Material Symbols CDN icons with
emoji (so the page works without Google Fonts / Material CDN), and rewrites
the few claims that plan forbids (face matching, 99.x%, 0.2s, 100% guarantees,
fake alert() form submit). Run once; keep landing.html honest after."""
import re
from pathlib import Path

PATH = Path('marketing/landing.html')
ICON = {
    'verified': '✅', 'calendar_today': '📅', 'menu': '☰', 'shield': '🛡',
    'video_camera_front': '📷', 'directions_bike': '🚲', 'badge': '🪪',
    'visibility': '👁', 'person': '🧑', 'groups': '👥', 'analytics': '📊',
    'science': '🔬', 'description': '📄', 'admin_panel_settings': '⚙️',
    'check_circle': '✅', 'pending': '⏳', 'priority_high': '❗',
    'schedule': '🕒', 'school': '🏫', 'face': '🙂', 'play_circle': '▶',
    'refresh': '↻', 'speed': '⏱', 'gavel': '⚖', 'download': '⬇',
    'upload': '⬆', 'bolt': '⚡', 'local_police': '🛡', 'login': '➡',
    'logout': '⇤', 'edit': '✎', 'delete': '🗑', 'add': '＋',
    'close': '✕', 'search': '🔍', 'check': '✓', 'arrow_back': '←',
    'chevron_right': '›', 'expand_more': '⌄', 'warning': '⚠', 'info': 'ⓘ',
    'error': '✕', 'image': '🖼', 'videocam': '📹', 'mic': '🎤',
    'volume_up': '🔊', 'volume_off': '🔇', 'home': '⌂', 'settings': '⚙',
    'memory': '🧠', 'folder': '📁', 'build': '🛠', 'wifi': '📶',
    'wifi_off': '⛔', 'router': '📡', 'database': '🗄', 'lock': '🔒',
    'lock_open': '🔓', 'key': '🔑', 'event': '📅', 'star': '★',
    'thumb_up': '👍', 'thumb_down': '👎', 'flag': '⚑',
    'chevron_left': '‹', 'arrow_forward': '→', 'arrow_downward': '↓',
    'arrow_upward': '↑', 'hearing': '👂', 'graphic_eq': '🎚',
    'notifications_active': '🔔', 'campaign': '📣', 'support_agent': '•',
    'lightbulb': '💡', 'workspace_premium': '⭐', 'auto_awesome': '✨',
    'backpack': '🎒', 'cast_for_edu': '🎓', 'model_training': '·',
    'extension': '🧩', 'lunch_dining': '🍱', 'directions_car': '🚗',
    'sensors': '📡', 'no_encryption': '🔓', 'sync': '↻',
    'trending_up': '↗', 'trending_down': '↘', 'replay': '↺',
    'volume_down': '🔉', 'play_arrow': '▶', 'pause': '⏸',
    'stop': '⏹', 'fast_forward': '⏩', 'sos': '🆘',
    'fact_check': '✓', 'history_edu': '📜', 'folder_open': '📂',
    'live_tv': '📺', 'pan_tool': '✋', 'volume_mute': '🔇',
    'campaign': '📣', 'emergency': '🆘', 'task_alt': '❎',
}

src = PATH.read_text(encoding='utf-8')

# 1) Replace Material Symbols icon spans with emoji spans
def sub_icon(m):
    name = m.group(2)
    cls_extra = m.group(1).replace('material-symbols-outlined', '').strip()
    e = ICON.get(name, '•')
    cls = ('material-icon ' + cls_extra).strip()
    return f'<span class="{cls}">{e}</span>'

src = re.sub(r'<span class="(material-symbols-outlined[^"]*)">([a-z_]+)</span>',
             sub_icon, src)

# 2) Forbidden claim rewrites (per plan D8 — phải đúng)
REWrites = [
    # Description meta
    ('đối soát khuôn mặt học sinh và phân biệt xe đạp thường với xe điện ngay tại cổng trường',
     'đọc biển số và cảnh báo vi phạm mũ bảo hiểm ngay tại máy.'),
    # Hero claim
    ('đối soát khuôn mặt với danh sách học sinh và phân biệt chính xác xe đạp thường với xe điện ngay trong 0.2 giây',
     'hỗ trợ bảo vệ quan sát và phát loa cảnh báo bằng tiếng Việt.'),
    # Tương thích 100%
    ('Tương thích 100% với hạ tầng camera IP có sẵn của nhà trường. Không phát sinh chi phí thay thế camera.',
     'Bám sát hạ tầng camera IP RTSP phổ biến; vui lòng đối chiếu danh sách camera trước khi triển khai.'),
    # 100% Có Bằng Chứng
    ('<div class="font-heading font-bold text-3xl text-navy">100% Có Bằng Chứng</div>',
     '<div class="font-heading font-bold text-3xl text-navy">Có bằng chứng cho mỗi lượt</div>'),
    # 100% Lưu trữ có giờ
    ('<div class="font-heading font-bold text-xs sm:text-sm">100% Lưu trữ có giờ</div>',
     '<div class="font-heading font-bold text-xs sm:text-sm">Lưu trữ có giờ (mục tiêu)</div>'),
    # 99.4%
    ('<span class="font-mono text-[11px] text-emerald-400 font-bold">99.4%</span>',
     '<span class="font-mono text-[11px] text-emerald-300 font-bold">đã đo</span>'),
    # 99.2%
    ('<div class="font-heading font-bold text-xs sm:text-sm">99.2% Chuẩn kiểm định</div>',
     '<div class="font-heading font-bold text-xs sm:text-sm">Bản demo local (mục tiêu)</div>'),
    # 99.1% Confidence
    ('<span class="font-mono font-bold text-accent">99.1% Confidence</span>',
     '<span class="font-mono font-bold text-accent">đang chạy thử</span>'),
    # Loại bỏ 100% khiếu nại
    ('Loại bỏ 100% khiếu nại từ phụ huynh và học sinh về việc trừ điểm thi đua nhầm lẫn.',
     'Giảm tranh cãi nhờ ảnh bằng chứng và mã sự kiện xuyên suốt; vẫn cần người duyệt các ca mơ hồ.'),
    # Cam kết bảo mật 100%
    ('Cam kết bảo mật 100% thông tin liên hệ và hình ảnh học sinh của nhà trường.',
     'Không gửi ảnh học sinh hay biển số thật lên cloud; dữ liệu ở máy edge.'),
    # Mili-giây
    ('ở tốc giữa mili-giây, bảo vệ không cần thao tác bấm máy thủ công.',
     'trên bản build local; bảo vệ chỉ cần bật loa và quan sát banner.'),
    # 0.2s
    ('tức thời ngay khi học sinh vừa lăn bánh qua cổng', 'khi phát hiện lỗi đã xác nhận'),
    # khuôn mặt học sinh ngoài trường xâm nhập
    ('khuôn mặt học sinh ngoài trường xâm nhập và không dắt xe qua cổng theo nội quy',
     'và không dắt xe qua cổng theo nội quy'),
    # Face match feature heading
    ('3. Đối Soát Khuôn Mặt Với Danh Sách Học Sinh',
     '3. Theo dõi biển số và vi phạm'),
    # so khớp khuôn mặt
    ('so khớp khuôn mặt hồ sơ học sinh; nhận dạng tư thế dắt xe hay cưỡi xe.',
     'nhận dạng tư thế dắt xe hay cưỡi xe theo vạch cổng.'),
    # FACE_MATCH_STUDENT chip
    ('FACE_MATCH_STUDENT', 'PLATE_TRACKING'),
    # Form fake alert() submit
    ("onsubmit=\"event.preventDefault(); alert('Cảm ơn Quý Thầy/Cô! Đội ngũ kỹ thuật School Gate Monitor sẽ liên hệ trong 24 giờ làm việc để tiếp nhận video mẫu và gửi lại bản phân tích.');\"",
     'onsubmit="event.preventDefault(); window.location.href=\'mailto:demo@school-gate-monitor.local?subject=Đặt%20lịch%20demo&body=Trường:%20%0ALiên%20hệ:%20\';"'),
    # onsubmit gets a real mailto so the form actually does something.
]

for old, new in REWrites:
    src = src.replace(old, new)

# 3) Replace all onclicks that used alert(...) with text-only honest wording
# (clickable, but tell the user this is just a demo, not a real backend.)
src = re.sub(
    r"onclick=\"alert\('([^']*)'\);\"",
    lambda m: f'title="{m.group(1)} (chỉ minh họa — chưa nối backend)"',
    src)

# 4) Remove the FACE_MATCH feature card so we don't ship an unrealised claim.
src = re.sub(
    r'<div class="bg-white rounded-2xl p-6 shadow-md border border-gray-border fade-in">'
    r'\s*<div class="flex items-center justify-between mb-4">'
    r'[\s\S]*?FACE_MATCH_STUDENT[\s\S]*?</div>\s*</div>\s*</div>\s*</div>',
    '', src, count=1)

# 5) Update the live clock in the hero so the demo doesn't pretend it's 24/10/2024
src = src.replace('06:47:12 AM - 24/10/2024',
                  'Demo build local · bấm "Đặt Lịch Demo" để xem video')
# Replace the demo FPS/AI claim text too (it was 30.0 FPS / 142ms)
src = src.replace(
    '<span class="px-2 py-0.5 rounded bg-white/10">30.0 FPS</span>',
    '<span class="px-2 py-0.5 rounded bg-white/10">demo</span>')
src = src.replace(
    '<span class="hidden md:inline px-2 py-0.5 rounded bg-white/10">EDGE-AI YOLO-v8</span>',
    '<span class="hidden md:inline px-2 py-0.5 rounded bg-white/10">AI local</span>')
src = src.replace(
    '<span class="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-bold">ĐỘ TRỄ: 142ms</span>',
    '<span class="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-bold">demo (chưa đo)</span>')

PATH.write_text(src, encoding='utf-8')
print('landing.html rewritten:', PATH)