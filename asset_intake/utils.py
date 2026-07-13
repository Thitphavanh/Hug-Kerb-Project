"""ເຄື່ອງມືຊ່ວຍ — ຜະລິດ QR Code ເປັນ data URI (ໃຊ້ໄດ້ທັງໜ້າເວັບ ແລະ PDF)"""

import base64
from io import BytesIO

import qrcode
from django.conf import settings


def qr_data_uri(text, box_size=8):
    """ຄືນ PNG data URI ຂອງ QR code ສຳລັບໃສ່ <img src="...">"""
    qr = qrcode.QRCode(border=2, box_size=box_size)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def absolute_url(path):
    """ຕໍ່ SITE_BASE_URL ໃສ່ໜ້າ path — ສຳລັບລິ້ງທີ່ຕ້ອງໃຊ້ນອກເວັບ (QR, ຂໍ້ຄວາມ)"""
    return settings.SITE_BASE_URL.rstrip("/") + path
