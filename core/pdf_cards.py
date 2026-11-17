"""
توليد كروت الطلاب PDF (اسم + باركود + QR)
"""
import io
from pathlib import Path

import barcode
import qrcode
from barcode.writer import ImageWriter
from django.conf import settings
from PIL import Image, ImageDraw, ImageFont


def _make_barcode(code: str) -> Image.Image:
    """باركود Code128"""
    buffer = io.BytesIO()
    code128 = barcode.get_barcode_class('code128')
    bc = code128(code, writer=ImageWriter())
    bc.write(buffer, options={
        'module_width': 0.4,
        'module_height': 12,
        'quiet_zone': 2,
        'font_size': 0,
        'text_distance': 1,
        'write_text': False,
    })
    buffer.seek(0)
    return Image.open(buffer).convert('RGB')


def _make_qr(code: str, size: int = 120) -> Image.Image:
    qr = qrcode.QRCode(version=1, box_size=4, border=1)
    qr.add_data(code)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    return img.resize((size, size), Image.Resampling.LANCZOS).convert('RGB')


def _get_font(size: int = 20):
    """خط عربي إن وجد، وإلا الخط الافتراضي"""
    candidates = [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
        '/usr/share/fonts/truetype/freefont/FreeSans.ttf',
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def generate_student_cards_pdf(students, center) -> bytes:
    """
    يولد PDF فيه كروت الطلاب (4 كروت في الصفحة A4).
    كل كارت: اسم السنتر + اسم الطالب + الصف + باركود + QR
    """
    # حجم الكارت بالبيكسل (تقريبي لـ 85x55mm @ 150dpi)
    CARD_W, CARD_H = 500, 320
    MARGIN = 20
    COLS, ROWS = 2, 3  # 6 كروت في الصفحة

    cards = []
    font_title = _get_font(18)
    font_name = _get_font(22)
    font_small = _get_font(14)

    for student in students:
        card = Image.new('RGB', (CARD_W, CARD_H), 'white')
        draw = ImageDraw.Draw(card)

        # إطار
        draw.rectangle([2, 2, CARD_W - 3, CARD_H - 3], outline='#4F46E5', width=3)

        # شريط علوي
        draw.rectangle([2, 2, CARD_W - 3, 45], fill='#4F46E5')
        center_name = center.name[:30]
        # نص في النص
        bbox = draw.textbbox((0, 0), center_name, font=font_title)
        tw = bbox[2] - bbox[0]
        draw.text(((CARD_W - tw) // 2, 12), center_name, fill='white', font=font_title)

        # اسم الطالب
        name = student.name[:40]
        bbox = draw.textbbox((0, 0), name, font=font_name)
        tw = bbox[2] - bbox[0]
        draw.text(((CARD_W - tw) // 2, 60), name, fill='#111', font=font_name)

        # الصف
        grade = student.get_grade_display()
        bbox = draw.textbbox((0, 0), grade, font=font_small)
        tw = bbox[2] - bbox[0]
        draw.text(((CARD_W - tw) // 2, 95), grade, fill='#555', font=font_small)

        # الباركود
        try:
            bc_img = _make_barcode(student.barcode)
            bc_img = bc_img.resize((340, 70), Image.Resampling.LANCZOS)
            card.paste(bc_img, ((CARD_W - 340) // 2, 130))
        except Exception:
            draw.text((CARD_W // 2 - 40, 150), student.barcode, fill='#333', font=font_small)

        # رقم الباركود
        bbox = draw.textbbox((0, 0), student.barcode, font=font_small)
        tw = bbox[2] - bbox[0]
        draw.text(((CARD_W - tw) // 2, 205), student.barcode, fill='#333', font=font_small)

        # QR في الركن
        try:
            qr_img = _make_qr(student.barcode, 80)
            card.paste(qr_img, (CARD_W - 100, CARD_H - 100))
        except Exception:
            pass

        cards.append(card)

    if not cards:
        # كارت فاضي
        cards = [Image.new('RGB', (CARD_W, CARD_H), 'white')]

    # تجميع في صفحات A4 تقريباً
    PAGE_W = CARD_W * COLS + MARGIN * (COLS + 1)
    PAGE_H = CARD_H * ROWS + MARGIN * (ROWS + 1)

    pages = []
    for i in range(0, len(cards), COLS * ROWS):
        page = Image.new('RGB', (PAGE_W, PAGE_H), '#f0f0f0')
        batch = cards[i:i + COLS * ROWS]
        for idx, card in enumerate(batch):
            row, col = divmod(idx, COLS)
            x = MARGIN + col * (CARD_W + MARGIN)
            y = MARGIN + row * (CARD_H + MARGIN)
            page.paste(card, (x, y))
        pages.append(page)

    # حفظ كـ PDF
    buffer = io.BytesIO()
    pages[0].save(
        buffer,
        format='PDF',
        save_all=True,
        append_images=pages[1:] if len(pages) > 1 else [],
        resolution=150,
    )
    buffer.seek(0)
    return buffer.getvalue()
