"""ບໍລິການແຈ້ງເຕືອນລູກຄ້າ — Telegram Bot API ແລະ ລິ້ງ wa.me (WhatsApp)"""

import logging
import re
from urllib.parse import quote

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"

# ຂໍ້ຄວາມແຈ້ງເຕືອນແຍກຕາມສະຖານະ (ສົ່ງທຸກຄັ້ງທີ່ຂັ້ນຕອນປ່ຽນ)
STATUS_TEXT = {
    "received": "ຮ້ານໄດ້ຮັບເກີບຂອງທ່ານເຂົ້າລະບົບແລ້ວ ✅ (Intake)",
    "cleaning": "ເກີບຂອງທ່ານກຳລັງທຳຄວາມສະອາດ 🧼 (Cleaning)",
    "repairing": "ເກີບຂອງທ່ານກຳລັງສ້ອມແປງ 🔧 (Repairing)",
    "ready": "ເກີບຂອງທ່ານສຳເລັດແລ້ວ ພ້ອມໃຫ້ມາຮັບຄືນທີ່ຮ້ານ 🎉 (Ready for Pickup)",
    "returned": "ສົ່ງມອບເກີບຄືນຮຽບຮ້ອຍແລ້ວ 🙏 ຂອບໃຈທີ່ໃຊ້ບໍລິການ Hug Kerb",
}


def build_status_message(asset):
    """ຂໍ້ຄວາມແຈ້ງເຕືອນຕາມສະຖານະປັດຈຸບັນ ພ້ອມລິ້ງຕິດຕາມ (portal)"""
    portal_url = settings.SITE_BASE_URL.rstrip("/") + asset.get_portal_url()
    item = f"{asset.brand} {asset.model_name}".strip()
    lines = [
        f"ສະບາຍດີ {asset.customer.name} 👟",
        STATUS_TEXT.get(asset.status, asset.get_status_display()),
        f"ເກີບ: {item} · ເລກໃບຮັບເຄື່ອງ: {asset.ticket_number}",
    ]
    if asset.status == "ready" and asset.pickup_date:
        lines.append(f"ວັນນັດຮັບເຄື່ອງ: {asset.pickup_date:%d/%m/%Y}")
    lines += [
        f"ກົດລິ້ງນີ້ເພື່ອຕິດຕາມສະຖານະ ແລະ ເບິ່ງຮູບກ່ອນ-ຫຼັງຊັກ: {portal_url}",
        "(ເຂົ້າເບິ່ງໂດຍຢືນຢັນເບີໂທທີ່ລົງທະບຽນກັບຮ້ານ)",
    ]
    return "\n".join(lines)


def send_telegram(chat_id, text):
    """ສົ່ງຂໍ້ຄວາມຜ່ານ Telegram Bot API — ຄືນຄ່າ (ok, error)"""
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        return False, "TELEGRAM_BOT_TOKEN ຍັງບໍ່ໄດ້ຕັ້ງຄ່າໃນ .env"
    try:
        resp = requests.post(
            TELEGRAM_API_URL.format(token=token),
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
        if resp.ok and resp.json().get("ok"):
            return True, ""
        return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
    except requests.RequestException as exc:
        return False, str(exc)[:200]


def notify_status_change(asset):
    """ແຈ້ງລູກຄ້າຜ່ານ Telegram ທຸກຄັ້ງທີ່ຂັ້ນຕອນປ່ຽນ — ບໍ່ throw exception"""
    from .models import NotificationLog

    try:
        chat_id = (asset.customer.telegram_chat_id or "").strip()
        if not chat_id:
            return
        message = build_status_message(asset)
        ok, error = send_telegram(chat_id, message)
        NotificationLog.objects.create(
            asset=asset,
            channel=NotificationLog.Channel.TELEGRAM,
            recipient=chat_id,
            message=message,
            is_sent=ok,
            error=error,
        )
        if not ok:
            logger.warning(
                "Telegram notify failed for %s: %s", asset.ticket_number, error
            )
    except Exception:
        logger.exception("notify_status_change failed for asset %s", asset.pk)


def whatsapp_phone(phone):
    """ແປງເບີໂທເປັນຮູບແບບສາກົນສຳລັບ wa.me (ເບີຂຶ້ນຕົ້ນ 0 ຖືວ່າເປັນເບີລາວ +856)"""
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("00"):
        digits = digits[2:]
    elif digits.startswith("0"):
        digits = "856" + digits[1:]
    return digits


def build_wa_link(asset):
    """ລິ້ງ wa.me ພ້ອມຂໍ້ຄວາມຕາມສະຖານະປັດຈຸບັນ ໃຫ້ພະນັກງານກົດສົ່ງຫາລູກຄ້າ"""
    digits = whatsapp_phone(asset.customer.phone)
    if not digits:
        return ""
    return f"https://wa.me/{digits}?text={quote(build_status_message(asset))}"
