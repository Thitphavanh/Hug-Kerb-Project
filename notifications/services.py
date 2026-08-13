"""ບໍລິການແຈ້ງເຕືອນລູກຄ້າ — Telegram Bot API ແລະ ລິ້ງ wa.me (WhatsApp)"""

import logging
import re
from urllib.parse import quote

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"
WHATSAPP_API_URL = "https://graph.facebook.com/v20.0/{phone_number_id}/messages"

# ຂໍ້ຄວາມແຈ້ງເຕືອນແຍກຕາມສະຖານະ (ສົ່ງທຸກຄັ້ງທີ່ຂັ້ນຕອນປ່ຽນ)
STATUS_TEXT = {
    "received": "ຮ້ານໄດ້ຮັບເກີບຂອງທ່ານເຂົ້າລະບົບແລ້ວ ✅ (Intake)",
    "cleaning": "ເກີບຂອງທ່ານກຳລັງທຳຄວາມສະອາດ 🧼 (Cleaning)",
    "repairing": "ເກີບຂອງທ່ານກຳລັງສ້ອມແປງ 🔧 (Repairing)",
    "ready": "ເກີບຂອງທ່ານສຳເລັດແລ້ວ ພ້ອມໃຫ້ມາຮັບຄືນທີ່ຮ້ານ 🎉 (Ready for Pickup)",
    "returned": "ສົ່ງມອບເກີບຄືນຮຽບຮ້ອຍແລ້ວ 🙏 ຂອບໃຈທີ່ໃຊ້ບໍລິການ Hug ເກີບ",
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


def send_whatsapp(to_digits, text):
    """ສົ່ງຂໍ້ຄວາມຜ່ານ WhatsApp Business Cloud API (Meta) — ຄືນຄ່າ (ok, error)"""
    token = settings.WHATSAPP_ACCESS_TOKEN
    phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
    if not token or not phone_number_id:
        return False, "WHATSAPP_ACCESS_TOKEN/WHATSAPP_PHONE_NUMBER_ID ຍັງບໍ່ໄດ້ຕັ້ງຄ່າໃນ .env"
    try:
        resp = requests.post(
            WHATSAPP_API_URL.format(phone_number_id=phone_number_id),
            headers={"Authorization": f"Bearer {token}"},
            json={
                "messaging_product": "whatsapp",
                "to": to_digits,
                "type": "text",
                "text": {"body": text},
            },
            timeout=10,
        )
        if resp.ok:
            return True, ""
        return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
    except requests.RequestException as exc:
        return False, str(exc)[:200]


def send_whatsapp_image(to_digits, image_url, caption=""):
    """ສົ່ງ *ຮູບ* ຜ່ານ WhatsApp Cloud API — ຄືນຄ່າ (ok, error)

    Meta ຈະໄປໂຫຼດຮູບຈາກ image_url ເອງ ຈຶ່ງຕ້ອງເປັນ URL ສາທາລະນະ
    (ບໍ່ແມ່ນ localhost) ແລະຕ້ອງເປີດໄດ້ໂດຍບໍ່ຕ້ອງ login
    """
    token = settings.WHATSAPP_ACCESS_TOKEN
    phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
    if not token or not phone_number_id:
        return False, "WHATSAPP_ACCESS_TOKEN/WHATSAPP_PHONE_NUMBER_ID ຍັງບໍ່ໄດ້ຕັ້ງຄ່າໃນ .env"
    try:
        resp = requests.post(
            WHATSAPP_API_URL.format(phone_number_id=phone_number_id),
            headers={"Authorization": f"Bearer {token}"},
            json={
                "messaging_product": "whatsapp",
                "to": to_digits,
                "type": "image",
                # caption ຂອງ WhatsApp ຈຳກັດ 1024 ໂຕ
                "image": {"link": image_url, "caption": caption[:1024]},
            },
            timeout=15,
        )
        if resp.ok:
            return True, ""
        return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
    except requests.RequestException as exc:
        return False, str(exc)[:200]


def notify_stamp_card(customer, card, visit_count=None):
    """ສົ່ງ *ຮູບບັດສະສົມ Stamp* ໃຫ້ລູກຄ້າຜ່ານ WhatsApp Cloud API

    ຄືນຄ່າ (ok, error). ຖ້າຍັງບໍ່ໄດ້ຕັ້ງ Cloud API ຈະຄືນ error
    ໃຫ້ໜ້າຈໍ fallback ໄປໃຊ້ລິ້ງ wa.me ໃຫ້ພະນັກງານກົດສົ່ງເອງແທນ
    """
    from .models import NotificationLog

    digits = whatsapp_phone(getattr(customer, "phone", ""))
    if not digits:
        return False, "ລູກຄ້າຍັງບໍ່ມີເບີໂທ"

    # ຮູບແນບໄປແລ້ວ — ບໍ່ຕ້ອງໃສ່ລິ້ງໃນຂໍ້ຄວາມອີກ
    caption = build_stamp_card_message(customer, card, visit_count, include_link=False)
    image_url = member_card_image_url(card)

    ok, error = send_whatsapp_image(digits, image_url, caption)
    NotificationLog.objects.create(
        customer=customer,
        channel=NotificationLog.Channel.WHATSAPP,
        recipient=digits,
        message=caption,
        is_sent=ok,
        error=error,
    )
    if not ok:
        logger.warning("Stamp card send failed for %s: %s", digits, error)
    return ok, error


def notify_status_change(asset):
    """ແຈ້ງລູກຄ້າທຸກຊ່ອງທາງທີ່ຕັ້ງຄ່າໄວ້ (Telegram + WhatsApp) ທຸກຄັ້ງທີ່ຂັ້ນຕອນປ່ຽນ
    — ບໍ່ throw exception ເພື່ອບໍ່ໃຫ້ກະທົບການບັນທຶກສະຖານະ"""
    from .models import NotificationLog

    try:
        message = build_status_message(asset)

        # Telegram (ຖ້າລູກຄ້າມີ chat_id)
        chat_id = (asset.customer.telegram_chat_id or "").strip()
        if chat_id:
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

        # WhatsApp (ຖ້າຕັ້ງຄ່າ Cloud API ແລ້ວ ແລະ ລູກຄ້າມີເບີໂທ)
        digits = whatsapp_phone(asset.customer.phone)
        if digits and settings.WHATSAPP_ACCESS_TOKEN:
            ok, error = send_whatsapp(digits, message)
            NotificationLog.objects.create(
                asset=asset,
                channel=NotificationLog.Channel.WHATSAPP,
                recipient=digits,
                message=message,
                is_sent=ok,
                error=error,
            )
            if not ok:
                logger.warning(
                    "WhatsApp notify failed for %s: %s", asset.ticket_number, error
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
    """ລິ້ງ WhatsApp ພ້ອມຂໍ້ຄວາມຕາມສະຖານະປັດຈຸບັນ ໃຫ້ພະນັກງານກົດສົ່ງຫາລູກຄ້າ

    ໃຊ້ api.whatsapp.com/send ໂດຍກົງ ບໍ່ຜ່ານ wa.me — server redirect ຂອງ wa.me
    ຈະປ່ຽນ emoji ໃນ text ເປັນ U+FFFD (�) ເຮັດໃຫ້ຂໍ້ຄວາມເພ້"""
    digits = whatsapp_phone(asset.customer.phone)
    if not digits:
        return ""
    return (
        f"https://api.whatsapp.com/send?phone={digits}"
        f"&text={quote(build_status_message(asset))}"
    )


def build_stamp_card_message(customer, card, visit_count=None, include_link=True):
    """ຂໍ້ຄວາມ "ກາດ Stamp" ສົ່ງໃຫ້ລູກຄ້າຫຼັງຊຳລະເງິນ

    ວາດ Stamp ເປັນແຖວ emoji ໃຫ້ອ່ານງ່າຍໃນ WhatsApp — ດວງທີ່ໄດ້ແລ້ວ 👟 ດວງທີ່ຍັງ ⚪

    include_link=False ໃຊ້ຕອນສົ່ງເປັນ *ຮູບ* ຜ່ານ Cloud API
    (ຮູບແນບໄປແລ້ວ ໃສ່ລິ້ງອີກຈະຊ້ຳ) — True ໃຊ້ຕອນສົ່ງເປັນຂໍ້ຄວາມຜ່ານ wa.me
    """
    current = card.current_stamps
    filled = "👟" * current
    empty = "⚪" * max(0, 10 - current)

    lines = [
        f"ສະບາຍດີ {customer.name} 🙏",
        "ຂອບໃຈທີ່ໃຊ້ບໍລິການ Hug ເກີບ Shoe Spa",
        "",
        f"ບັດສະສົມ Stamp ຂອງທ່ານ: {current}/10",
        f"{filled}{empty}",
    ]
    if visit_count:
        lines.append(f"ມາໃຊ້ບໍລິການແລ້ວ {visit_count} ຄັ້ງ")

    if card.rewards_available > 0:
        lines += ["", f"🎁 ຄົບ 10 ດວງແລ້ວ! ທ່ານໄດ້ຮັບສ່ວນຫຼຸດພິເສດ {card.rewards_available} ສິດ"]
    else:
        lines += ["", f"ອີກ {10 - current} ດວງ ຮັບສ່ວນຫຼຸດພິເສດທັນທີ 🎁"]

    if include_link:
        # ລິ້ງຮູບບັດ — WhatsApp ຈະ preview ຮູບໃຫ້ອັດຕະໂນມັດ ລູກຄ້າກົດເບິ່ງ/ບັນທຶກໄດ້
        lines += ["", "ບັດສະສົມຂອງທ່ານ:", member_card_image_url(card)]

    return "\n".join(lines)


def member_card_image_url(card):
    """URL ເຕັມຂອງຮູບບັດສະສົມ Stamp (ໃຊ້ໄດ້ຈາກນອກລະບົບ)"""
    from django.urls import reverse

    path = reverse(
        "digital_member:member_card_image", args=[card.card_number]
    )
    return settings.SITE_BASE_URL.rstrip("/") + path


def build_stamp_wa_link(customer, card, visit_count=None):
    """ລິ້ງ WhatsApp ພ້ອມກາດ Stamp — ພະນັກງານກົດສົ່ງເອງຫຼັງຮັບເງິນ"""
    digits = whatsapp_phone(getattr(customer, "phone", ""))
    if not digits:
        return ""
    message = build_stamp_card_message(customer, card, visit_count)
    return f"https://api.whatsapp.com/send?phone={digits}&text={quote(message)}"
