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


def absolute_url(path, request=None):
    """ສ້າງ URL ເຕັມສຳລັບລິ້ງທີ່ຕ້ອງໃຊ້ນອກເວັບ (QR, ຂໍ້ຄວາມ)

    ຖ້າມີ request ຈະໃຊ້ host ຕົວຈິງທີ່ເປີດຢູ່ (ເຊັ່ນ ngrok) ເພື່ອໃຫ້ QR
    ສະແກນຈາກມືຖືໄດ້ — ຖ້າບໍ່ມີ ຈຶ່ງຖອຍໄປໃຊ້ SITE_BASE_URL"""
    if request is not None:
        return request.build_absolute_uri(path)
    return settings.SITE_BASE_URL.rstrip("/") + path
