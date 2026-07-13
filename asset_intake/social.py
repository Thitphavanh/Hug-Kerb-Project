"""ສ້າງຮູບ Before/After ສຳລັບໂພສ social media ດ້ວຍ Pillow"""

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# font ລາວຂອງໂປຣເຈັກ (core/static/fonts/) — ຊື່ຮ້ານ "Hug ເກີບ" ມີໂຕລາວ
_PROJECT_FONT = Path(__file__).resolve().parents[1] / "static" / "fonts" / "NotoSansLao-Bold.ttf"

CANVAS = 1080
HEADER_H = 120
FOOTER_H = 90
BRAND_COLOR = (11, 28, 48)
ACCENT_COLOR = (56, 189, 248)
WHITE = (255, 255, 255)


def _font(size):
    """ໂຫຼດ font ທີ່ມີໃນເຄື່ອງ — fallback ເປັນ font default ຂອງ Pillow"""
    for path in (
        str(_PROJECT_FONT),  # Noto Sans Lao — ຮອງຮັບທັງລາວ ແລະ ອັງກິດ
        "/System/Library/Fonts/Helvetica.ttc",  # macOS
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _fit_half(path, half_w, half_h):
    """ຕັດ/ຂະຫຍາຍຮູບໃຫ້ເຕັມເຄິ່ງກອບ (cover crop ຈາກກາງ)"""
    img = Image.open(path).convert("RGB")
    scale = max(half_w / img.width, half_h / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)))
    left = (img.width - half_w) // 2
    top = (img.height - half_h) // 2
    return img.crop((left, top, left + half_w, top + half_h))


def _label(draw, text, x, y, font):
    """ປ້າຍຂໍ້ຄວາມພື້ນເຂັ້ມມົນໆ ທັບເທິງຮູບ"""
    pad = 14
    box = draw.textbbox((x, y), text, font=font)
    draw.rounded_rectangle(
        (box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad),
        radius=10,
        fill=BRAND_COLOR,
    )
    draw.text((x, y), text, font=font, fill=WHITE)


def compose_before_after(before_path, after_path, caption=""):
    """ຄືນ PNG bytes: ຮູບກ່ອນ-ຫຼັງຄຽງກັນ ພ້ອມ header/footer ຂອງຮ້ານ"""
    canvas = Image.new("RGB", (CANVAS, CANVAS), BRAND_COLOR)
    half_w = CANVAS // 2
    photo_h = CANVAS - HEADER_H - FOOTER_H

    canvas.paste(_fit_half(before_path, half_w, photo_h), (0, HEADER_H))
    canvas.paste(_fit_half(after_path, half_w, photo_h), (half_w, HEADER_H))

    draw = ImageDraw.Draw(canvas)

    # ເສັ້ນແບ່ງກາງ
    draw.rectangle(
        (half_w - 3, HEADER_H, half_w + 3, HEADER_H + photo_h), fill=WHITE
    )

    # Header: ຊື່ຮ້ານ + caption
    draw.text((40, 30), "Hug ເກີບ", font=_font(56), fill=ACCENT_COLOR)
    if caption:
        title_font = _font(34)
        w = draw.textlength(caption, font=title_font)
        draw.text((CANVAS - 40 - w, 44), caption[:40], font=title_font, fill=WHITE)

    # ປ້າຍ BEFORE / AFTER
    label_font = _font(40)
    _label(draw, "BEFORE", 40, HEADER_H + 36, label_font)
    after_w = draw.textlength("AFTER", font=label_font)
    _label(draw, "AFTER", CANVAS - 40 - after_w, HEADER_H + 36, label_font)

    # Footer
    footer_font = _font(30)
    footer = "Shoe Cleaning & Care"
    w = draw.textlength(footer, font=footer_font)
    draw.text(
        ((CANVAS - w) / 2, CANVAS - FOOTER_H + 26),
        footer,
        font=footer_font,
        fill=WHITE,
    )

    buf = BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()
