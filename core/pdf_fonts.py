"""PDF ພາສາລາວ — render ດ້ວຍ WeasyPrint ເພາະມີ HarfBuzz text shaping ໃນຕົວ

ເດີມໃຊ້ xhtml2pdf/reportlab ແຕ່ມັນວາງສະຫຼະ/ວັນນະຍຸດລາວຜິດຕຳແໜ່ງ
ເຊັ່ນ "ໃບບິນ" ອອກເປັນ "ໃບບນິ" — ຕ້ອງຝັງ Noto Sans Lao ເຂົ້າ PDF ຄືເກົ່າ
ບໍ່ດັ່ງນັ້ນໂຕໜັງສືລາວຈະເປັນສີ່ຫຼ່ຽມດຳ
"""
from django.conf import settings
from django.http import HttpResponse

_FONT_DIR = settings.BASE_DIR / "static" / "fonts"
_IMAGE_DIR = settings.BASE_DIR / "static" / "images"


def pdf_font_context():
    """ຄືນ file:// URI ຂອງ font ສຳລັບ @font-face ໃນ template ທີ່ render ເປັນ PDF"""
    return {
        "pdf_font_regular": (_FONT_DIR / "NotoSansLao-Regular.ttf").as_uri(),
        "pdf_font_bold": (_FONT_DIR / "NotoSansLao-Bold.ttf").as_uri(),
        "pdf_logo": (_IMAGE_DIR / "hug-kerb-logo.jpeg").as_uri(),
    }


def pdf_response(html, filename):
    """render HTML string ເປັນ PDF response — import ຊ້າເພື່ອບໍ່ໂຫຼດ pango ຕອນ startup"""
    from weasyprint import HTML

    pdf_bytes = HTML(string=html).write_pdf()
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response
