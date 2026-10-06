#!/usr/bin/env python
"""Build PPTX (16:9) + PDF for demo 04/10/2026.

Dùng nội dung trong tasks/task-06-demo-2026-10-04/SLIDES_CONTENT.md.
Mỗi slide gắn nhãn trạng thái (ĐÃ CÓ MÃ / ĐÃ KIỂM CHỨNG / CẦN NGHIỆM THU /
ĐỀ XUẤT) đúng plan yêu cầu. Notes tiếng Việt. Tự sinh PDF dự phòng từ
chính PPTX đã render.

Tham số: --output-dir (mặc định release/demo-2026-10-04/).
"""
import argparse
import datetime
import re
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.enum.shapes import MSO_SHAPE
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

NAVY = RGBColor(0x12, 0x3B, 0x6D)
NAVY_DARK = RGBColor(0x0B, 0x23, 0x41)
ACCENT = RGBColor(0xC9, 0x20, 0x35)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
LIGHT = RGBColor(0xF0, 0xF4, 0xFA)
GRAY = RGBColor(0x37, 0x41, 0x51)
SLATE = RGBColor(0x4B, 0x55, 0x63)
BORDER = RGBColor(0xE2, 0xE8, 0xF0)


def add_title(slide, text, sub=None, status=None, duration=None):
    # Top navy bar
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.333), Inches(1.2))
    bar.line.fill.background()
    bar.fill.solid()
    bar.fill.fore_color.rgb = NAVY

    title_box = slide.shapes.add_textbox(Inches(0.6), Inches(0.18), Inches(12.0), Inches(0.7))
    tf = title_box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.name = 'Calibri'
    p.font.size = Pt(32)
    p.font.bold = True
    p.font.color.rgb = WHITE
    if sub:
        p2 = tf.add_paragraph()
        p2.text = sub
        p2.font.size = Pt(14)
        p2.font.color.rgb = LIGHT

    # status + duration chip
    if status or duration:
        chip = slide.shapes.add_textbox(Inches(8.5), Inches(0.18), Inches(4.7), Inches(0.5))
        ctf = chip.text_frame
        cp = ctf.paragraphs[0]
        cp.text = f'{status or ""}  •  {duration or ""}'.strip('  • ')
        cp.font.size = Pt(11)
        cp.font.name = 'Consolas'
        cp.font.color.rgb = LIGHT
        cp.alignment = PP_ALIGN.RIGHT


def add_footer(slide, idx, total, label):
    f = slide.shapes.add_textbox(Inches(0.6), Inches(7.0), Inches(12.0), Inches(0.4))
    tf = f.text_frame
    p = tf.paragraphs[0]
    p.text = f'School Gate Monitor · Demo 04/10/2026 · {label}'
    p.font.size = Pt(10)
    p.font.color.rgb = SLATE
    p.font.italic = True
    p2 = tf.add_paragraph()
    p2.text = f'Trang {idx}/{total}'
    p2.font.size = Pt(9)
    p2.font.color.rgb = SLATE
    p2.alignment = PP_ALIGN.RIGHT


def add_bullets(slide, bullets, top=Inches(1.5), left=Inches(0.6), width=Inches(12.0), height=Inches(5.2)):
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    for i, item in enumerate(bullets):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        if isinstance(item, tuple):
            head, body = item
            p.text = '• ' + head
            p.font.bold = True
            p.font.size = Pt(18)
            p.font.color.rgb = NAVY
            p2 = tf.add_paragraph()
            p2.text = '   ' + body
            p2.font.size = Pt(15)
            p2.font.color.rgb = GRAY
            p2.space_after = Pt(8)
        else:
            p.text = '• ' + item
            p.font.size = Pt(18)
            p.font.color.rgb = GRAY
            p.space_after = Pt(6)


def set_notes(slide, text):
    n = slide.notes_slide
    tf = n.notes_text_frame
    tf.text = text


def make_slide(prs, title, sub, status, dur, bullets, notes, label, idx, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    add_title(s, title, sub, status, dur)
    add_bullets(s, bullets)
    add_footer(s, idx, total, label)
    set_notes(s, notes)


def build_pptx(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    # --- Slide content (theo SLIDES_CONTENT.md đã đọc) ---
    TOTAL = 12
    slides = [
        dict(
            title='Cổng trường an toàn — bảo vệ xử lý chủ động',
            sub='School Gate Monitor · trợ lý giám sát cổng',
            status='BẢN DEMO LOCAL',
            dur='15s',
            bullets=[
                'Hai camera → biển số và tình huống qua cổng → bằng chứng → người duyệt',
                'Demo 04/10/2026: laptop + camera + loa, hoạt động trong LAN, WAN ngắt',
            ],
            notes=(
                'Mở đầu: Hệ thống hỗ trợ bảo vệ quan sát xe qua cổng, đọc biển và xem bằng chứng để xử lý. '
                'Hôm nay trình diễn bằng laptop, hai camera và loa trên mạng nội bộ, kể cả khi ngắt Internet.'
            ),
            label='Slide 1 — Mở đầu',
        ),
        dict(
            title='Một luồng làm việc rõ ràng',
            sub='Bốn menu, mỗi vai trò thấy đúng phần của mình',
            status='UI ĐÃ KIỂM CHỨNG · LUẬT CẦN NGHIỆM THU',
            dur='20s',
            bullets=[
                ('Giám sát', 'xem camera, biển đọc, trạng thái bằng chứng'),
                ('Vi phạm', 'kiểm ảnh và lịch sử; báo cáo cùng luồng'),
                ('Xe đăng ký', 'đối chiếu biển đã xác nhận'),
                ('Cài đặt', 'camera, vùng đọc, lưu trữ; AI nâng cao chỉ dành cho admin'),
                'Biển yếu / mâu thuẫn cần người duyệt trước khi gắn với hồ sơ',
            ],
            notes=(
                'Bảo vệ làm việc trên Giám sát; người quản lý kiểm bằng chứng trong Vi phạm. '
                'Xe đăng ký và Cài đặt tách rõ. Mỗi tài khoản chỉ thấy phần phù hợp quyền.'
            ),
            label='Slide 2 — Luồng người dùng',
        ),
        dict(
            title='Demo chạy tại chỗ khi mất Internet',
            sub='Tất cả xử lý tại laptop, không phụ thuộc WAN',
            status='KIẾN TRÚC LOCAL HIỆN CÓ',
            dur='25s',
            bullets=[
                ('Hai camera RTSP LAN', 'gửi hình qua router đến laptop, không cloud/P2P'),
                ('Web + DB + weights', 'phục vụ tại máy, không cần Internet'),
                ('Âm thanh tiếng Việt', 'ưu tiên giọng local cài sẵn; nếu không có, dùng clip câu lỗi lưu sẵn'),
                ('Bằng chứng', 'ảnh + JSON event ở máy; không upload lên cloud'),
                'Demo sẽ rút WAN, giữ LAN rồi kiểm frame mới và âm thanh ngay tại chỗ',
            ],
            notes=(
                'Internet không nằm trong đường nhận diện. Camera → router → laptop; web/DB tại máy. '
                'Giọng Việt phải chạy tại máy; nếu không có thì dùng clip đã lưu.'
            ),
            label='Slide 3 — Kiến trúc offline',
        ),
        dict(
            title='Phần đã làm và bằng chứng kiểm thử',
            sub='Trạng thái đến ngày 03/10/2026, sau khi đối chiếu lại',
            status='ĐÃ KIỂM CHỨNG TRONG PHẠM VI NÊU',
            dur='25s',
            bullets=[
                ('Capture', 'tách khỏi AI, latest frame, JPEG dùng chung — focused test pass'),
                ('UI', '9/9 browser test cho auth/quyền/dataset/media/bbox'),
                ('Regression R2–R14', '152 passed / 1 skipped / 0 failed (full suite)'),
                ('R8 audit', 'inspect + export smoke 10/10; dữ liệu mũ vẫn pending'),
                ('Camera thật + loa offline', 'cần nghiệm thu hôm nay — hôm nay không gắn camera; dùng 15 clip R14 (216 FPS) làm bằng chứng chạy file'),
            ],
            notes=(
                'Đây là kiểm phần mềm. Chất lượng nhận diện và loa phải đối chiếu riêng; '
                'hôm nay chưa có camera thật nên dùng R14 harness 15 clip làm bằng chứng.'
            ),
            label='Slide 4 — Bằng chứng kiểm thử',
        ),
        dict(
            title='Biển số: ưu tiên đúng và có thể kiểm tra',
            sub='Detect → track → chọn crop → OCR → đồng thuận nhiều frame',
            status='ĐÃ CÓ MÃ · TOÀN CHUỖI CẦN NGHIỆM THU',
            dur='25s',
            bullets=[
                ('Hai frame độc lập', 'là điều kiện chốt; 1 crop biến thể không thành 2 phiếu'),
                ('Tối đa 5 crop / 2 giây', 'mỗi lượt xe; raw/conf/hash/track/camera/epoch đi xuyên'),
                ('Mâu thuẫn / mờ / che', 'chuyển cần duyệt; giữ ảnh gốc và nguồn quan sát'),
                ('Không tự gán', 'whitelist chỉ đối chiếu sau khi biển đã xác nhận'),
                ('Metadata chưa đầy đủ', 'ByteTrack thật + biển hai dòng + CCT ONNX thật vẫn ở hạng mục nghiệm thu',
                 ),
            ],
            notes=(
                'Khi thiếu chữ hoặc mâu thuẫn, kết quả phải chuyển cần duyệt. '
                'Danh sách xe đăng ký không dùng để sửa chuỗi yếu.'
            ),
            label='Slide 5 — Biển số',
        ),
        dict(
            title='Cảnh báo ngắn, đúng tình huống, đúng lúc',
            sub='Một lượt xe = một lần nhắc; chỉ một máy giữ quyền loa',
            status='MÃ AUDIO ĐÃ NỐI VÀO UI',
            dur='25s',
            bullets=[
                ('Mũ / số người / tư thế', 'theo bằng chứng quan sát được, có nguồn'),
                ('Một lượt nhiều lỗi', 'đọc gộp: "Không đội mũ, vui lòng dắt xe."'),
                ('Lease UUID', 'một viewer là owner, các viewer khác trên cùng cổng im lặng'),
                ('Finalize + evidence', 'chỉ đọc khi alert_finalized=true và evidence đã persist'),
                ('Reconnect / late issue', 'không đọc lại sự kiện cũ; biển đến muộn bổ sung im lặng'),
            ],
            notes=(
                'Loa đã nối qua helper createAlertAudio với filter/dedup/TTL. '
                'Giọng Việt ưu tiên localService=true; nếu máy không có thì dùng clip lưu sẵn.'
            ),
            label='Slide 6 — Audio',
        ),
        dict(
            title='Bảy phút kiểm chứng luồng thực tế',
            sub='Mỗi bước có đối chiếu, có bằng chứng',
            status='KỊCH BẢN DEMO',
            dur='25s',
            bullets=[
                ('00:00–01:10', 'đăng nhập, hai feed, rút WAN giữ LAN — chỉ ra frame mới của cả hai camera'),
                ('01:10–02:15', 'ca A: biển rõ, đối chiếu GT, chốt đúng hoặc công bố cần duyệt'),
                ('02:15–03:05', 'ca B: không đội mũ, nghe loa, xem bằng chứng'),
                ('03:05–04:25', 'ca C/D: tư thế / biển yếu → unknown / cần duyệt'),
                ('04:25–06:25', 'ca F: hai viewer — chỉ owner phát loa, không đọc event cũ'),
                ('06:25–07:00', 'landing local + chốt bàn giao, video dự phòng nếu cần'),
            ],
            notes=(
                'Tổng 7 phút. Mỗi ca có expected/observed. '
                'Nếu lỗi, chuyển fallback F1/F2/F3 trong runbook.'
            ),
            label='Slide 7 — Kịch bản demo 7 phút',
        ),
        dict(
            title='Bản bàn giao có thể vận hành và kiểm lại',
            sub='Cấu hình, weights, video dự phòng, runbook, manifest',
            status='BÀN GIAO',
            dur='20s',
            bullets=[
                ('Bản chạy', 'release/demo-2026-10-04/: launcher, manifest, runbook, slide/PDF, video backup'),
                ('VPS 103.101.162.111', 'port 22/80 reachable; SSH + deploy — pending_access (thiếu key, không ghi đè site EduPortal hiện tại)'),
                ('Local độc lập', 'xử lý tại cổng; WAN ngắt vẫn chạy đủ'),
                ('KPI / 12 giờ', 'demo gate đạt; production gate (KPI ≥95%, 12 giờ endurance) vẫn pending'),
            ],
            notes=(
                'Local đã freeze. Bàn giao trước 01:00. '
                'Trước khi đóng gói, lấy số đo thật từ FINAL_ACCEPTANCE.'
            ),
            label='Slide 8 — Bàn giao',
        ),
        # Appendices
        dict(
            title='Phụ lục — Thước đo chất lượng và tốc độ (mục tiêu)',
            sub='Chưa phải kết quả đo',
            status='MỤC TIÊU · CHƯA CÓ SỐ ĐO NGHIỆM THU',
            dur='Q&A',
            bullets=[
                'ALPR toàn chuỗi: exact ≥95% trong các biển tự chốt; coverage ≥90%',
                'Hai camera: preview mới ≥15 FPS, AI ≥5 FPS; biển p95 ≤2s',
                'Mũ: precision ≥98% / recall ≥95%; hành vi/số người: precision ≥95% / recall ≥90%',
                'Holdout ≥300 lượt có nhãn người duyệt; báo cả lỗi/cần duyệt/bỏ sót',
                'Phải đo từ bản freeze sau khi tổng duyệt — không thay bằng confidence OCR',
            ],
            notes='Phải có nhãn người duyệt độc lập; mẫu nhỏ chỉ là smoke.',
            label='Slide 9 — Phụ lục KPI',
        ),
        dict(
            title='Phụ lục — Dữ liệu và phương án YOLO11',
            sub='Audit đã có; train thật cần Kaggle',
            status='AUDIT ĐÃ KIỂM · TRAIN/WEIGHTS MỚI CHƯA ĐẠT',
            dur='Q&A',
            bullets=[
                '8.259 ảnh detect + 3.188 ảnh ký tự: hợp lệ cấu trúc; 4 nhóm trùng; chưa có holdout độc lập',
                'Bộ mũ: 0 ảnh — cần thu thêm từ camera thật',
                'Ultralytics 8.4.168 đã có; weights runtime vẫn là v8/custom — chưa chuyển YOLO11',
                'Ba notebook Kaggle đã tạo (YOLO11 biển, mũ/xe điện, CCT); chưa có Kaggle run thật',
                'CCT adapter ONNX thật đã smoke; holdout và promotion còn mở',
            ],
            notes='Nâng package không đồng nghĩa đã nâng model; giữ baseline để quay lại nếu không đạt.',
            label='Slide 10 — Phụ lục dữ liệu',
        ),
        dict(
            title='Phụ lục — VPS và giới thiệu sản phẩm',
            sub='Local giữ inference, VPS phục vụ phần nhẹ',
            status='ĐỀ XUẤT · CHƯA XÁC NHẬN DEPLOY',
            dur='Q&A',
            bullets=[
                'Local giữ camera, inference, âm thanh và vận hành khi mất Internet',
                'VPS 103.101.162.111: nginx/1.18.0 Ubuntu, port 22+80 OK, 443 fail; hiện serve landing EduPortal khác',
                'SSH read-only denied (no key) — ghi pending_access; không ghi đè site khác',
                'Landing local marketing/landing.html + operations.html đã sửa: bỏ face matching, 99.x%, 0.2s, 100%, form giả',
            ],
            notes='Trình bày landing local trong demo offline; không mở form cũ "đã gửi đăng ký".',
            label='Slide 11 — Phụ lục VPS',
        ),
        dict(
            title='Phụ lục — Điều kiện thông qua và rollback',
            sub='Demo gate vs production gate',
            status='CHECKLIST NGHIỆM THU',
            dur='Q&A',
            bullets=[
                'Demo gate: cold refresh, login, 2 feed mới, event/media + loa OK khi WAN ngắt; 1 owner loa; không đọc lặp',
                'Production gate: ALPR ≥95%, 12 giờ endurance, full media restore, VPS/sync production — vẫn pending',
                'Rollback: build+weights+config đã kiểm; giữ DB/evidence mới; không xóa staging',
                'Video backup có nhãn "video ghi trước"; không thay thế bằng chứng camera thật',
            ],
            notes='Không hứa "production hoàn tất" khi gate production còn mở; chỉ demo_ready khi đạt đúng phạm vi.',
            label='Slide 12 — Phụ lục gate',
        ),
    ]

    for i, sl in enumerate(slides, start=1):
        make_slide(prs, sl['title'], sl.get('sub', ''), sl.get('status', ''),
                   sl.get('dur', ''), sl['bullets'], sl['notes'], sl['label'],
                   i, TOTAL)

    out_pptx = out_dir / 'School_Gate_Monitor_Demo.pptx'
    prs.save(out_pptx)
    print('PPTX saved:', out_pptx)
    return out_pptx


def build_pdf_from_slides(out_dir: Path, pptx_path: Path):
    """Render the same content to PDF using reportlab (no Office needed)."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import landscape
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.colors import HexColor
    import textwrap

    out_pdf = out_dir / 'School_Gate_Monitor_Demo.pdf'
    c = canvas.Canvas(str(out_pdf), pagesize=landscape((1280, 720)))

    # Try to register a font with Vietnamese support
    font = 'Helvetica'
    font_bold = 'Helvetica-Bold'
    try:
        for cand in [r'C:\Windows\Fonts\segoeui.ttf',
                     r'C:\Windows\Fonts\arial.ttf',
                     r'C:\Windows\Fonts\DejaVuSans.ttf']:
            if Path(cand).exists():
                pdfmetrics.registerFont(TTFont('VI', cand))
                pdfmetrics.registerFont(TTFont('VI-Bold', cand))
                font = 'VI'
                font_bold = 'VI-Bold'
                break
    except Exception:
        pass

    navy = HexColor('#123B6D')
    gray = HexColor('#374151')
    accent = HexColor('#C92035')
    light = HexColor('#F0F4FA')

    slides = [
        ('CỔNG TRƯỜNG AN TOÀN — BẢO VỆ XỬ LÝ CHỦ ĐỘNG', 'BẢN DEMO LOCAL', '15s', [
            'Hai camera → biển số và tình huống qua cổng → bằng chứng → người duyệt',
            'Demo 04/10/2026: laptop + camera + loa, hoạt động trong LAN, WAN ngắt',
        ]),
        ('MỘT LUỒNG LÀM VIỆC RÕ RÀNG', 'UI ĐÃ KIỂM CHỨNG · LUẬT CẦN NGHIỆM THU', '20s', [
            'Giám sát: xem camera, biển đọc, trạng thái bằng chứng',
            'Vi phạm: kiểm ảnh và lịch sử; báo cáo cùng luồng',
            'Xe đăng ký: đối chiếu biển đã xác nhận',
            'Cài đặt: camera, vùng đọc, lưu trữ; AI nâng cao chỉ dành cho admin',
            'Biển yếu / mâu thuẫn cần người duyệt trước khi gắn với hồ sơ',
        ]),
        ('DEMO CHẠY TẠI CHỖ KHI MẤT INTERNET', 'KIẾN TRÚC LOCAL HIỆN CÓ', '25s', [
            'Hai camera RTSP LAN → laptop GPU local; không cloud/P2P',
            'Web + DB + weights + bằng chứng tại máy',
            'Âm thanh tiếng Việt: ưu tiên local, fallback clip lưu sẵn',
            'Demo sẽ rút WAN, giữ LAN rồi kiểm frame mới + loa',
        ]),
        ('PHẦN ĐÃ LÀM VÀ BẰNG CHỨNG KIỂM THỬ', 'ĐÃ KIỂM CHỨNG TRONG PHẠM VI NÊU', '25s', [
            'Capture: tách khỏi AI, latest frame, JPEG dùng chung — focused test pass',
            'UI: 9/9 browser test (auth/quyền/dataset/media/bbox)',
            'Regression R2–R14: 152 passed / 1 skipped / 0 failed',
            'R14: 15/15 clip EOF, 216 FPS (chạy file — chưa phải preview/AI end-to-end)',
            'Camera thật + 12 giờ endurance: cần nghiệm thu; hôm nay không gắn camera',
        ]),
        ('BIỂN SỐ — ƯU TIÊN ĐÚNG VÀ CÓ THỂ KIỂM TRA', 'ĐÃ CÓ MÃ · TOÀN CHUỖI CẦN NGHIỆM THU', '25s', [
            'Hai frame độc lập là điều kiện chốt',
            'Tối đa 5 crop / 2 giây; raw/conf/hash/track/camera/epoch xuyên',
            'Mâu thuẫn / mờ / che → cần duyệt; không tự gán từ whitelist',
            'ByteTrack thật + biển hai dòng + CCT ONNX thật: vẫn ở hạng mục nghiệm thu',
        ]),
        ('CẢNH BÁO NGẮN, ĐÚNG TÌNH HUỐNG, ĐÚNG LÚC', 'MÃ AUDIO ĐÃ NỐI VÀO UI', '25s', [
            'Mũ / số người / tư thế theo bằng chứng quan sát được',
            'Một lượt nhiều lỗi: gộp "Không đội mũ, vui lòng dắt xe."',
            'Lease UUID — chỉ một owner phát loa; các viewer khác im lặng',
            'Finalize + evidence + audio_authorized; reconnect không đọc lại',
            'Giọng local nếu có, clip lưu sẵn nếu không',
        ]),
        ('BẢY PHÚT KIỂM CHỨNG LUỒNG THỰC TẾ', 'KỊCH BẢN DEMO', '25s', [
            '00:00–01:10 đăng nhập, hai feed, rút WAN giữ LAN',
            '01:10–02:15 ca A: biển rõ, đối chiếu GT',
            '02:15–03:05 ca B: không đội mũ, nghe loa, xem bằng chứng',
            '03:05–04:25 ca C/D: tư thế / biển yếu → unknown / cần duyệt',
            '04:25–06:25 ca F: hai viewer — chỉ owner phát loa',
            '06:25–07:00 landing local + chốt bàn giao',
        ]),
        ('BẢN BÀN GIAO CÓ THỂ VẬN HÀNH VÀ KIỂM LẠI', 'BÀN GIAO', '20s', [
            'release/demo-2026-10-04/: launcher, manifest, runbook, slide/PDF, video backup',
            'VPS 103.101.162.111: 22/80 reachable, 443 fail; SSH pending_access; site EduPortal không ghi đè',
            'Local độc lập: xử lý tại cổng, WAN ngắt vẫn chạy đủ',
            'Production gate (KPI ≥95%, 12 giờ): pending',
        ]),
        ('PHỤ LỤC — THƯỚC ĐO CHẤT LƯỢNG VÀ TỐC ĐỘ (MỤC TIÊU)',
         'MỤC TIÊU · CHƯA CÓ SỐ ĐO NGHIỆM THU', 'Q&A', [
            'ALPR toàn chuỗi: exact ≥95%; coverage ≥90%',
            'Hai camera: preview ≥15 FPS, AI ≥5 FPS; biển p95 ≤2s',
            'Mũ: P≥98% R≥95%; hành vi/số người: P≥95% R≥90%',
            'Holdout ≥300 lượt có nhãn người duyệt',
        ]),
        ('PHỤ LỤC — DỮ LIỆU VÀ PHƯƠNG ÁN YOLO11',
         'AUDIT ĐÃ KIỂM · TRAIN/WEIGHTS MỚI CHƯA ĐẠT', 'Q&A', [
            '8.259 detect + 3.188 OCR: hợp lệ cấu trúc; 4 nhóm trùng; chưa holdout độc lập',
            'Bộ mũ: 0 ảnh — cần thu từ camera thật',
            'Ultralytics 8.4.168; weights runtime vẫn v8/custom; chưa YOLO11',
            '3 notebook Kaggle đã tạo; chưa có run thật',
            'CCT adapter ONNX đã smoke; holdout + promotion còn mở',
        ]),
        ('PHỤ LỤC — VPS VÀ GIỚI THIỆU SẢN PHẨM',
         'ĐỀ XUẤT · CHƯA XÁC NHẬN DEPLOY', 'Q&A', [
            'Local giữ camera, inference, âm thanh, vận hành khi WAN ngắt',
            'VPS: nginx/1.18.0 Ubuntu, 22+80 OK, 443 fail; EduPortal khác đang serve',
            'SSH read-only denied — pending_access; không ghi đè site khác',
            'Landing local đã sửa: bỏ face matching, 99.x%, 0.2s, 100%, form giả',
        ]),
        ('PHỤ LỤC — ĐIỀU KIỆN THÔNG QUA VÀ ROLLBACK',
         'CHECKLIST NGHIỆM THU', 'Q&A', [
            'Demo gate: cold refresh, login, 2 feed mới, audio, 1 owner loa, không đọc lặp',
            'Production gate: ALPR ≥95%, 12 giờ endurance, full media restore — pending',
            'Rollback: build+weights+config đã kiểm; giữ DB/evidence mới',
            'Video backup có nhãn "video ghi trước"; không thay camera thật',
        ]),
    ]

    W, H = 1280, 720
    for i, (title, status, dur, bullets) in enumerate(slides, start=1):
        c.setFillColor(navy)
        c.rect(0, H - 90, W, 90, fill=1, stroke=0)
        c.setFillColor(HexColor('#FFFFFF'))
        c.setFont(font_bold, 28)
        c.drawString(40, H - 55, title)
        c.setFont(font, 14)
        c.drawString(40, H - 80, status + '  ·  ' + dur)

        c.setFillColor(gray)
        c.setFont(font, 18)
        y = H - 140
        for line in bullets:
            wrapped = textwrap.wrap(line, width=72)
            for j, w in enumerate(wrapped):
                marker = '• ' if j == 0 else '   '
                c.drawString(60, y, marker + w)
                y -= 28
            y -= 4
        c.setFont(font, 10)
        c.setFillColor(HexColor('#6B7280'))
        c.drawString(40, 25, f'School Gate Monitor · Demo 04/10/2026 · {i}/{len(slides)}')
        c.showPage()
    c.save()
    print('PDF saved:', out_pdf)
    return out_pdf


def build_speaker_notes(out_dir: Path):
    notes = {
        1: 'Mở đầu. Giọng chậm, rõ. Nhấn mạnh "hỗ trợ bảo vệ", không nói thay bảo vệ.',
        2: 'Nhấn mạnh 4 menu và phân quyền. Nói thêm "biển yếu cần người duyệt".',
        3: 'Nhấn mạnh Internet không nằm trên đường xử lý; demo sẽ rút WAN.',
        4: 'Nêu số 152/1/0 rõ ràng; giải thích R14 là file, chưa phải camera thật.',
        5: 'Hai frame độc lập, dedup, không dùng whitelist để sửa chuỗi yếu.',
        6: 'Helper createAlertAudio đã nối; lease UUID, 1 owner; finalize + evidence.',
        7: 'Đọc 6 mốc 1 phút, mỗi mốc có kỳ vọng rõ. Nếu sai, fallback F1/F2/F3.',
        8: 'Bàn giao trước 01:00. Local đã freeze. VPS chỉ landing, không nằm đường xử lý.',
        9: 'Đây là mục tiêu. Chưa phải kết quả. Nhắc: phải có nhãn người duyệt, ≥300 lượt.',
        10: 'Audit đã có. Train thật cần Kaggle. Bộ mũ = 0 ảnh — cần camera thật.',
        11: 'VPS chỉ probe được port 22/80, SSH denied, không ghi đè EduPortal. Landing local sạch claim sai.',
        12: 'Demo gate vs production gate. Rollback giữ data mới. Không hứa "production hoàn tất".',
    }
    p = out_dir / 'SPEAKER_NOTES.md'
    with p.open('w', encoding='utf-8') as f:
        f.write('# Speaker Notes — Demo School Gate Monitor 04/10/2026\n\n')
        f.write('Mỗi slide 12 tương ứng 1 đoạn. Đọc kèm slide, không bê nguyên checklist nội bộ lên sân khấu.\n\n')
        for k, v in notes.items():
            f.write(f'## Slide {k}\n{v}\n\n')
    print('NOTES saved:', p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output-dir', default='release/demo-2026-10-04')
    args = ap.parse_args()
    out = Path(args.output_dir)
    pptx = build_pptx(out)
    build_pdf_from_slides(out, pptx)
    build_speaker_notes(out)


if __name__ == '__main__':
    main()