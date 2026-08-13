"""ສ້າງຮູບບັດສະສົມ Stamp (PNG) ດ້ວຍ Pillow — ໄວ້ສົ່ງໃຫ້ລູກຄ້າທາງ WhatsApp

ໂທນສີຕາມແບຣນ: #1d2b53 80% + ຂາວ 20%, ໂຕໜັງສືຂາວ
ຮູບແບບດຽວກັນກັບບັດໃນ Modal ຂອງ CRM ເພື່ອໃຫ້ພະນັກງານ ແລະ ລູກຄ້າເຫັນຄືກັນ
"""

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_STATIC = Path(__file__).resolve().parents[1] / "static"
_FONT_BOLD = _STATIC / "fonts" / "NotoSansLao-Bold.ttf"
_FONT_REGULAR = _STATIC / "fonts" / "NotoSansLao-Regular.ttf"
_LOGO = _STATIC / "images" / "hug-kerb-logo.jpeg"

# ຂະໜາດບັດ — ອັດຕາສ່ວນປະມານບັດເຄຣດິດ (1.6:1)
CARD_W, CARD_H = 1000, 620
FOOTER_H = 74

NAVY = (29, 43, 83)          # #1d2b53
WHITE = (255, 255, 255)
# ສີຂາວຈາງຄຳນວນຜະສົມກັບພື້ນນ້ຳເງິນໄວ້ລ່ວງໜ້າ (ບໍ່ໃຊ້ alpha)
# Pillow ບໍ່ blend alpha ໃນ draw ຢ່າງທີ່ຄາດ — ໃຊ້ສີທຶບຈຶ່ງແນ່ນອນກວ່າ
LABEL = (131, 138, 160)      # ຂາວ 45% ເທິງນ້ຳເງິນ — ປ້າຍຈາງ
TRACK = (79, 90, 121)        # ຂາວ 22% — ຊ່ອງ Stamp ທີ່ຍັງບໍ່ໄດ້
BADGE_FILL = (63, 75, 109)   # ຂາວ 15% — ພື້ນປ້າຍລະດັບ
BADGE_LINE = (97, 107, 135)  # ຂາວ 30% — ຂອບປ້າຍລະດັບ
RING = (92, 102, 131)        # ຂາວ 28% — ວົງແຫວນອ້ອມໂລໂກ້

PAD = 56


def _font(path, size):
    """ໂຫຼດ font ຂອງໂປຣເຈັກ — fallback ຖ້າບໍ່ພົບ"""
    for candidate in (str(path), "/System/Library/Fonts/Helvetica.ttc"):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _bold(size):
    return _font(_FONT_BOLD, size)


def _regular(size):
    return _font(_FONT_REGULAR, size)


def _circle_logo(diameter):
    """ຕັດໂລໂກ້ເປັນວົງມົນເຕັມວົງ (ບໍ່ມີຂອບຂາວ)"""
    try:
        logo = Image.open(_LOGO).convert("RGB")
    except OSError:
        return None

    # cover crop ຈາກກາງ ແລ້ວຄ່ອຍຕັດເປັນວົງມົນ
    scale = max(diameter / logo.width, diameter / logo.height)
    logo = logo.resize((round(logo.width * scale), round(logo.height * scale)))
    left = (logo.width - diameter) // 2
    top = (logo.height - diameter) // 2
    logo = logo.crop((left, top, left + diameter, top + diameter))

    mask = Image.new("L", (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, diameter - 1, diameter - 1), fill=255)
    logo.putalpha(mask)
    return logo


def _field(draw, x, y, label, value, value_font, label_font):
    """ປ້າຍນ້ອຍຈາງ + ຄ່າສີຂາວ ຂ້າງລຸ່ມ"""
    draw.text((x, y), label, font=label_font, fill=LABEL)
    draw.text((x, y + 26), value, font=value_font, fill=WHITE)


def compose_member_card(card):
    """ຄືນ PNG bytes ຂອງບັດສະສົມ Stamp ຂອງລູກຄ້າຄົນນຶ່ງ"""
    customer = card.customer
    canvas = Image.new("RGB", (CARD_W, CARD_H), NAVY)
    draw = ImageDraw.Draw(canvas)

    # ── ຫົວບັດ: ໂລໂກ້ + ຊື່ຮ້ານ + ລະດັບສະມາຊິກ ──
    logo_d = 92
    logo = _circle_logo(logo_d)
    if logo is not None:
        canvas.paste(logo, (PAD, PAD), logo)
        # ວົງແຫວນຂາວຈາງອ້ອມໂລໂກ້
        draw.ellipse(
            (PAD - 3, PAD - 3, PAD + logo_d + 2, PAD + logo_d + 2),
            outline=RING,
            width=3,
        )

    text_x = PAD + logo_d + 24
    draw.text((text_x, PAD + 12), "HUG ເກີບ", font=_bold(44), fill=WHITE)
    draw.text(
        (text_x, PAD + 62), "SHOE SPA · MEMBER", font=_regular(22), fill=LABEL
    )

    tier = (card.get_tier_display() or "").upper()
    if tier:
        tf = _bold(22)
        tw = draw.textlength(tier, font=tf)
        bx1, bx2 = CARD_W - PAD - tw - 36, CARD_W - PAD
        draw.rounded_rectangle(
            (bx1, PAD + 18, bx2, PAD + 66),
            radius=24,
            fill=BADGE_FILL,
            outline=BADGE_LINE,
            width=2,
        )
        draw.text((bx1 + 18, PAD + 30), tier, font=tf, fill=WHITE)

    # ── ຊື່ສະມາຊິກ ──
    y = PAD + logo_d + 46
    _field(draw, PAD, y, "ຊື່ສະມາຊິກ", customer.name, _bold(46), _regular(20))

    # ── ເລກສະມາຊິກ / ເບີໂທ ──
    y += 108
    _field(draw, PAD, y, "ເລກສະມາຊິກ", card.card_number, _bold(30), _regular(20))
    _field(
        draw,
        CARD_W // 2 + 20,
        y,
        "ເບີໂທ",
        customer.phone or "—",
        _bold(30),
        _regular(20),
    )

    # ── ແຖບ Stamp 10 ຊ່ອງ ──
    y += 108
    current = card.current_stamps
    draw.text((PAD, y), "STAMP", font=_regular(20), fill=LABEL)
    count_text = f"{current}/10"
    cf = _bold(30)
    draw.text(
        (CARD_W - PAD - draw.textlength(count_text, font=cf), y - 6),
        count_text,
        font=cf,
        fill=WHITE,
    )

    bar_y = y + 38
    gap, slots = 10, 10
    seg_w = (CARD_W - PAD * 2 - gap * (slots - 1)) / slots
    for i in range(slots):
        x1 = PAD + i * (seg_w + gap)
        draw.rounded_rectangle(
            (x1, bar_y, x1 + seg_w, bar_y + 14),
            radius=7,
            fill=WHITE if i < current else TRACK,
        )

    # ── ຕີນບັດ: ແຖບຂາວ (ສ່ວນ 20%) ──
    draw.rectangle((0, CARD_H - FOOTER_H, CARD_W, CARD_H), fill=WHITE)
    fy = CARD_H - FOOTER_H + 22
    draw.text((PAD, fy), "WWW.HUGKERB.LA", font=_bold(24), fill=NAVY)
    issued = card.issued_at.strftime("%m/%Y") if card.issued_at else ""
    if issued:
        rf = _regular(24)
        draw.text(
            (CARD_W - PAD - draw.textlength(issued, font=rf), fy),
            issued,
            font=rf,
            fill=NAVY,
        )

    buffer = BytesIO()
    canvas.save(buffer, format="PNG")
    return buffer.getvalue()
