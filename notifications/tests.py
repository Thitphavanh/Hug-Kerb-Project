from unittest.mock import patch

from django.test import TestCase, override_settings

from asset_intake.models import Asset
from crm.models import Customer

from .models import NotificationLog
from .services import build_wa_link, whatsapp_phone


@override_settings(TELEGRAM_BOT_TOKEN="test-token", SITE_BASE_URL="http://testserver")
class TelegramNotifyTest(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            name="ທົດສອບ", phone="02011112222", telegram_chat_id="12345"
        )

    def _make_asset(self, mock_post):
        mock_post.return_value.ok = True
        mock_post.return_value.json.return_value = {"ok": True}
        return Asset.objects.create(customer=self.customer, brand="Nike")

    @patch("notifications.services.requests.post")
    def test_notify_on_intake_creation(self, mock_post):
        asset = self._make_asset(mock_post)
        mock_post.assert_called_once()
        log = NotificationLog.objects.get()
        self.assertTrue(log.is_sent)
        self.assertEqual(log.recipient, "12345")
        self.assertIn(asset.public_token, log.message)
        self.assertIn("Intake", log.message)

    @patch("notifications.services.requests.post")
    def test_notify_on_every_status_change(self, mock_post):
        asset = self._make_asset(mock_post)
        mock_post.reset_mock()
        NotificationLog.objects.all().delete()

        for status in [
            Asset.Status.CLEANING,
            Asset.Status.REPAIRING,
            Asset.Status.READY,
            Asset.Status.RETURNED,
        ]:
            asset.status = status
            asset.save(update_fields=["status", "updated_at"])

        self.assertEqual(mock_post.call_count, 4)
        self.assertEqual(NotificationLog.objects.count(), 4)
        ready_log = NotificationLog.objects.filter(message__contains="Ready").first()
        self.assertIsNotNone(ready_log)
        self.assertIn(asset.public_token, ready_log.message)

    @patch("notifications.services.requests.post")
    def test_no_duplicate_notify_when_saving_same_status(self, mock_post):
        asset = self._make_asset(mock_post)
        mock_post.reset_mock()
        # ບັນທຶກຄືນໂດຍສະຖານະບໍ່ປ່ຽນ — ບໍ່ຄວນສົ່ງຊ້ຳ
        asset.save(update_fields=["status", "updated_at"])
        mock_post.assert_not_called()

    @patch("notifications.services.requests.post")
    def test_no_notify_without_chat_id(self, mock_post):
        self.customer.telegram_chat_id = ""
        self.customer.save()
        asset = Asset.objects.create(customer=self.customer, brand="Nike")
        asset.status = Asset.Status.READY
        asset.save(update_fields=["status", "updated_at"])
        mock_post.assert_not_called()
        self.assertEqual(NotificationLog.objects.count(), 0)

    @patch("notifications.services.requests.post", side_effect=Exception("boom"))
    def test_notify_failure_does_not_break_save(self, mock_post):
        asset = Asset.objects.create(customer=self.customer, brand="Nike")
        asset.status = Asset.Status.READY
        asset.save(update_fields=["status", "updated_at"])
        asset.refresh_from_db()
        self.assertEqual(asset.status, Asset.Status.READY)


class WhatsAppLinkTest(TestCase):
    def test_lao_phone_converted(self):
        self.assertEqual(whatsapp_phone("020 1111 2222"), "8562011112222")

    def test_international_phone_kept(self):
        self.assertEqual(whatsapp_phone("+66 81 234 5678"), "66812345678")

    def test_wa_link_contains_phone_and_ticket(self):
        customer = Customer.objects.create(name="ທົດສອບ", phone="02011112222")
        asset = Asset.objects.create(customer=customer, brand="Nike")
        link = build_wa_link(asset)
        # ໃຊ້ api.whatsapp.com ໂດຍກົງ — redirect ຂອງ wa.me ທຳລາຍ emoji ໃນ text
        self.assertIn("api.whatsapp.com/send?phone=8562011112222", link)
        self.assertIn(asset.ticket_number, link)

    def test_wa_link_keeps_emoji_encoding(self):
        customer = Customer.objects.create(name="ທົດສອບ", phone="02011112222")
        asset = Asset.objects.create(customer=customer, brand="Nike")
        link = build_wa_link(asset)
        # 👟 ໃນຂໍ້ຄວາມທັກທາຍຕ້ອງ encode ເປັນ UTF-8 ຄົບ 4 byte ບໍ່ແມ່ນ U+FFFD
        self.assertIn("%F0%9F%91%9F", link)
        self.assertNotIn("%EF%BF%BD", link)
