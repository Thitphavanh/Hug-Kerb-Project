import uuid
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from asset_intake.models import Asset, AssetService, StorageSlot
from crm.models import Customer

from .models import Order, OrderItem, Payment, ServiceType
from .services import hand_over_asset, record_payment, void_payment


class PosCustomerSearchTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="pos-customer-search",
            password="test-pass-123",
        )
        self.client.force_login(self.user)
        self.customer = Customer.objects.create(
            name="ນາງ ມາລີ ໄຊຍະວົງ",
            phone="02055551234",
        )
        self.service = ServiceType.objects.create(
            name="Deep Clean Service",
            price=Decimal("150000.00"),
            is_active=True,
        )

    def test_customer_search_matches_lao_name_and_partial_phone(self):
        name_response = self.client.get(
            reverse("pos:customer_search"),
            {"q": "ມາລີ"},
        )
        phone_response = self.client.get(
            reverse("pos:customer_search"),
            {"q": "551234"},
        )

        self.assertEqual(name_response.status_code, 200)
        self.assertEqual(name_response.json()["results"][0]["id"], self.customer.pk)
        self.assertEqual(phone_response.json()["results"][0]["phone"], self.customer.phone)

    def test_create_order_reuses_selected_customer(self):
        response = self.client.post(
            reverse("pos:create"),
            {
                "customer_id": str(self.customer.pk),
                "customer_name": self.customer.name,
                "customer_phone": self.customer.phone,
                "item_indices": "0",
                "brand_0": "Nike",
                "model_name_0": "Air Force 1",
                "size_0": "40",
                "service_0": str(self.service.pk),
            },
        )

        order = Order.objects.get()
        self.assertRedirects(response, reverse("pos:quotation", args=[order.pk]))
        self.assertEqual(order.customer, self.customer)
        self.assertEqual(Customer.objects.count(), 1)

    def test_create_order_assigns_selected_storage_slot(self):
        slot = StorageSlot.objects.create(zone="A", cabinet=1, position=1)

        response = self.client.post(
            reverse("pos:create"),
            {
                "customer_id": str(self.customer.pk),
                "customer_name": self.customer.name,
                "customer_phone": self.customer.phone,
                "item_indices": "0",
                "brand_0": "Nike",
                "model_name_0": "Air Force 1",
                "size_0": "40",
                "storage_slot_0": str(slot.pk),
                "service_0": str(self.service.pk),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            Asset.objects.get(model_name="Air Force 1").storage_slot,
            slot,
        )

    def test_save_and_ai_scan_opens_new_asset_photo_upload(self):
        self.client.post(
            reverse("set_language"),
            {"language": "en", "next": reverse("pos:create")},
        )
        response = self.client.post(
            reverse("pos:create"),
            {
                "next_action": "ai_scan",
                "customer_id": str(self.customer.pk),
                "customer_name": self.customer.name,
                "customer_phone": self.customer.phone,
                "item_indices": "0",
                "brand_0": "Nike",
                "model_name_0": "AI scan pair",
                "service_0": str(self.service.pk),
            },
        )

        asset = Asset.objects.get(model_name="AI scan pair")
        expected_url = (
            f"{reverse('asset_intake:detail', args=[asset.pk])}"
            "?ai=1#ai-photo-upload"
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, expected_url)

        detail = self.client.get(expected_url.split("#", 1)[0])
        self.assertContains(detail, 'id="ai-photo-upload"')
        self.assertContains(detail, "Start AI assessment")
        self.assertContains(detail, "AI assessment")

    def test_buyback_only_order_skips_quotation_and_opens_ai_grading(self):
        """ອໍເດີທີ່ມີແຕ່ບໍລິການ "ຮັບຊື້ເກີບມືສອງ" ຢ່າງດຽວ ບໍ່ມີຫຍັງໃຫ້ "ສະເໜີລາຄາ"
        — ຄວນຂ້າມໜ້າໃບສະເໜີລາຄາ/ເຊັນຢືນຢັນ ແລ້ວພາໄປໜ້າ AI Grading ຂອງເກີບເລີຍ."""
        buyback_service = ServiceType.objects.create(
            name="Buy-back Evaluation",
            category=ServiceType.Category.BUYBACK,
            price=Decimal("0.00"),
        )
        response = self.client.post(
            reverse("pos:create"),
            {
                "customer_id": str(self.customer.pk),
                "customer_name": self.customer.name,
                "customer_phone": self.customer.phone,
                "item_indices": "0",
                "brand_0": "Nike",
                "model_name_0": "Buy-back pair",
                "service_0": str(buyback_service.pk),
            },
        )

        asset = Asset.objects.get(model_name="Buy-back pair")
        expected_url = (
            f"{reverse('asset_intake:detail', args=[asset.pk])}"
            "?ai=1#ai-photo-upload"
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, expected_url)

    def test_mixed_buyback_and_paid_order_still_goes_to_quotation(self):
        """ຖ້າອໍເດີປະສົມ (ຮັບຊື້ + ບໍລິການທີ່ຄິດເງິນ) ຍັງມີຍອດທີ່ຕ້ອງອະນຸມັດແທ້ໆ
        — ຄວນໄປໜ້າໃບສະເໜີລາຄາຄືເກົ່າ, ບໍ່ຂ້າມ."""
        buyback_service = ServiceType.objects.create(
            name="Buy-back Evaluation",
            category=ServiceType.Category.BUYBACK,
            price=Decimal("0.00"),
        )
        order = Order.objects.create(customer=self.customer)
        asset1 = Asset.objects.create(customer=self.customer, brand="Nike")
        asset2 = Asset.objects.create(customer=self.customer, brand="Adidas")
        OrderItem.objects.create(
            order=order, service_type=buyback_service, asset=asset1,
            description="Buy-back", quantity=1, unit_price=0,
        )
        OrderItem.objects.create(
            order=order, service_type=self.service, asset=asset2,
            description="Deep clean", quantity=1, unit_price=self.service.price,
        )

        response = self.client.post(
            reverse("pos:create"),
            {
                "customer_id": str(self.customer.pk),
                "customer_name": self.customer.name,
                "customer_phone": self.customer.phone,
                "item_indices": "0,1",
                "brand_0": "Nike",
                "model_name_0": "Mixed pair A",
                "service_0": str(buyback_service.pk),
                "brand_1": "Nike",
                "model_name_1": "Mixed pair B",
                "service_1": str(self.service.pk),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith("/quotation/"))

    def test_storage_picker_map_marks_only_unoccupied_slot_as_free(self):
        free_slot = StorageSlot.objects.create(zone="A", cabinet=1, position=1)
        occupied_slot = StorageSlot.objects.create(zone="A", cabinet=1, position=2)
        Asset.objects.create(
            customer=self.customer,
            brand="Nike",
            model_name="Occupied pair",
            storage_slot=occupied_slot,
        )

        create_response = self.client.get(reverse("pos:create"))
        self.assertContains(create_response, reverse("pos:storage_map_data"))

        map_response = self.client.get(reverse("pos:storage_map_data"))
        slots = [
            slot
            for zone in map_response.json()["zones"]
            for row in zone["rows"]
            for slot in row["slots"]
        ]
        slots_by_id = {slot["id"]: slot for slot in slots}

        self.assertTrue(slots_by_id[free_slot.pk]["free"])
        self.assertFalse(slots_by_id[occupied_slot.pk]["free"])

    def test_duplicate_storage_selection_does_not_assign_two_pairs(self):
        slot = StorageSlot.objects.create(zone="A", cabinet=1, position=1)

        response = self.client.post(
            reverse("pos:create"),
            {
                "customer_id": str(self.customer.pk),
                "customer_name": self.customer.name,
                "customer_phone": self.customer.phone,
                "item_indices": "0,1",
                "brand_0": "Nike",
                "model_name_0": "Pair one",
                "storage_slot_0": str(slot.pk),
                "service_0": str(self.service.pk),
                "brand_1": "Adidas",
                "model_name_1": "Pair two",
                "storage_slot_1": str(slot.pk),
                "service_1": str(self.service.pk),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Asset.objects.filter(storage_slot=slot).count(), 1)
        self.assertEqual(Asset.objects.filter(storage_slot__isnull=True).count(), 1)

    def test_create_page_uses_theme_styled_color_and_size_dropdowns(self):
        self.client.post(
            reverse("set_language"),
            {"language": "en", "next": reverse("pos:create")},
        )
        response = self.client.get(reverse("pos:create"))

        self.assertContains(response, 'class="theme-select theme-select-with-swatch"')
        self.assertContains(response, 'id="color-swatch-0"')
        self.assertContains(response, 'id="size-select-0"')
        self.assertContains(response, "EU sizes")
        self.assertContains(response, "US sizes")
        self.assertContains(response, "Deep Clean Service")

        self.client.post(
            reverse("set_language"),
            {"language": "lo", "next": reverse("pos:create")},
        )
        response = self.client.get(reverse("pos:create"))
        self.assertContains(response, "ບໍລິການຊັກສະອາດເລິກ")

    def test_create_page_separates_ai_assessment_from_care_services(self):
        ServiceType.objects.create(
            name="AI Condition Report",
            category=ServiceType.Category.AI_ASSESSMENT,
            price=Decimal("45000.00"),
            is_active=True,
        )
        self.client.post(
            reverse("set_language"),
            {"language": "en", "next": reverse("pos:create")},
        )

        response = self.client.get(reverse("pos:create"))

        self.assertContains(response, "Basic Clean Service")
        self.assertNotContains(response, "AI Condition Report")

    def test_create_order_rejects_ai_report_as_shoe_care_service(self):
        ai_report = ServiceType.objects.create(
            name="AI Condition Report",
            category=ServiceType.Category.AI_ASSESSMENT,
            price=Decimal("45000.00"),
            is_active=True,
        )

        response = self.client.post(
            reverse("pos:create"),
            {
                "customer_id": str(self.customer.pk),
                "customer_name": self.customer.name,
                "customer_phone": self.customer.phone,
                "item_indices": "0",
                "brand_0": "Nike",
                "model_name_0": "Air Force 1",
                "service_0": str(ai_report.pk),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(OrderItem.objects.filter(service_type=ai_report).exists())

    def test_scan_lookup_returns_saved_color_and_size(self):
        asset = Asset.objects.create(
            customer=self.customer,
            brand="Nike",
            model_name="Air Force 1",
            color="Blue",
            size="US 9",
        )

        response = self.client.get(
            reverse("pos:scan_lookup"),
            {"code": asset.ticket_number},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["asset"]["color"], "Blue")
        self.assertEqual(response.json()["asset"]["size"], "US 9")


class QuotationLanguageTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="quotation-language",
            password="test-pass-123",
        )
        self.client.force_login(self.user)
        customer = Customer.objects.create(
            name="Quotation Customer",
            phone="02099990000",
        )
        service = ServiceType.objects.create(
            name="AI Grading",
            price=Decimal("1500000.00"),
            is_active=True,
        )
        self.order = Order.objects.create(customer=customer, created_by=self.user)
        OrderItem.objects.create(
            order=self.order,
            service_type=service,
            description=service.name,
            quantity=1,
            unit_price=service.price,
        )

    def set_language(self, language):
        self.client.post(
            reverse("set_language"),
            {"language": language, "next": reverse("pos:create")},
        )

    def test_quotation_and_signature_render_in_english_and_lao(self):
        self.set_language("en")
        quotation = self.client.get(reverse("pos:quotation", args=[self.order.pk]))
        signature = self.client.get(reverse("pos:quotation_sign", args=[self.order.pk]))

        self.assertContains(quotation, "Smart quotation")
        self.assertContains(quotation, "Promotions and discounts")
        self.assertContains(quotation, "Submit quotation")
        self.assertContains(signature, "Final step: confirm agreement")
        self.assertContains(signature, "Authorized signatory name")
        self.assertContains(signature, "Confirm and send document")
        self.assertContains(signature, 'name="language"', count=2)

        self.set_language("lo")
        quotation = self.client.get(reverse("pos:quotation", args=[self.order.pk]))
        signature = self.client.get(reverse("pos:quotation_sign", args=[self.order.pk]))

        self.assertContains(quotation, "ການສະເໜີລາຄາອັດສະລິຍະ")
        self.assertContains(quotation, "ໂປຣໂມຊັນ ແລະ ສ່ວນຫຼຸດ")
        self.assertContains(signature, "ຂັ້ນຕອນສຸດທ້າຍ")
        self.assertContains(signature, "ຊື່ຜູ້ມີອຳນາດລົງນາມ")

    def test_quotation_groups_ai_primary_and_add_on_services(self):
        ServiceType.objects.create(
            name="AI Condition Report",
            category=ServiceType.Category.AI_ASSESSMENT,
            price=Decimal("45000.00"),
        )
        ServiceType.objects.create(
            name="Color Touch-up",
            category=ServiceType.Category.ADD_ON,
            price=Decimal("180000.00"),
        )

        self.set_language("en")
        response = self.client.get(reverse("pos:quotation", args=[self.order.pk]))

        self.assertContains(response, "AI assessment")
        self.assertContains(response, "Primary services")
        self.assertContains(response, "Repair and add-on services")


class MarkOrderPaidStampTest(TestCase):
    """ປຸ່ມດ່ວນ "ຮັບເງິນສົດເຕັມຍອດ" → ປະທັບ Stamp 1 ດວງ + ລິ້ງ WhatsApp"""

    def setUp(self):
        self.user = get_user_model().objects.create_user("cashier", password="pw12345678")
        self.client.force_login(self.user)
        self.customer = Customer.objects.create(name="ທ້າວ ທົດສອບ", phone="02055551234")
        self.order = Order.objects.create(customer=self.customer, vat_rate=0)
        OrderItem.objects.create(
            order=self.order,
            description="ຊັກເກີບພຶ້ນຖານ",
            quantity=1,
            unit_price=Decimal("150000.00"),
        )

    def test_marking_paid_adds_one_stamp(self):
        from digital_member.models import MemberCard

        self.client.post(reverse("pos:mark_paid", args=[self.order.pk]))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAID)

        card = MemberCard.objects.get(customer=self.customer)
        self.assertEqual(card.stamps_count, 1)

    def test_quick_pay_writes_a_real_payment_row(self):
        """ຈຸດປະສົງຂອງ S1–S2: ຮັບເງິນຕ້ອງລົງ ledger ບໍ່ແມ່ນປ່ຽນແຕ່ status"""
        self.client.post(reverse("pos:mark_paid", args=[self.order.pk]))

        payment = Payment.objects.get(order=self.order)
        self.assertEqual(payment.amount, Decimal("150000.00"))
        self.assertEqual(payment.base_amount, Decimal("150000.00"))
        self.assertEqual(payment.method, Payment.Method.CASH)
        self.assertEqual(payment.received_by, self.user)

    def test_marking_paid_twice_does_not_double_stamp(self):
        from digital_member.models import MemberCard

        self.client.post(reverse("pos:mark_paid", args=[self.order.pk]))
        self.client.post(reverse("pos:mark_paid", args=[self.order.pk]))

        card = MemberCard.objects.get(customer=self.customer)
        self.assertEqual(card.stamps_count, 1)
        self.assertEqual(Payment.objects.filter(order=self.order).count(), 1)

    def test_paid_invoice_shows_whatsapp_stamp_link(self):
        self.client.post(reverse("pos:mark_paid", args=[self.order.pk]))
        response = self.client.get(reverse("pos:invoice", args=[self.order.pk]))
        self.assertContains(response, "ສົ່ງກາດ Stamp")
        self.assertIn("api.whatsapp.com", response.context["stamp_wa_link"])

    def test_open_invoice_shows_checkout_link_instead(self):
        response = self.client.get(reverse("pos:invoice", args=[self.order.pk]))
        self.assertContains(response, "ໄປໜ້າຄິດເງິນ")
        self.assertNotContains(response, "ສົ່ງກາດ Stamp")

    def test_get_request_does_not_change_status(self):
        self.client.get(reverse("pos:mark_paid", args=[self.order.pk]))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.OPEN)
        self.assertFalse(Payment.objects.filter(order=self.order).exists())


class OrderLedgerTest(TestCase):
    """ສະຖານະບິນຕ້ອງຄິດອອກຈາກ ledger ບໍ່ແມ່ນຕັ້ງດ້ວຍມື (ຮູບແບບທີ 12)"""

    def setUp(self):
        self.user = get_user_model().objects.create_user("ledger", password="pw12345678")
        self.customer = Customer.objects.create(name="ນາງ ລີ", phone="02055559999")
        self.order = Order.objects.create(customer=self.customer, vat_rate=0)
        OrderItem.objects.create(
            order=self.order,
            description="ຊັກເກີບ",
            quantity=2,
            unit_price=Decimal("150000.00"),
        )

    def test_partial_payment_moves_order_to_partially_paid(self):
        record_payment(
            order=self.order,
            amount=Decimal("100000"),
            method=Payment.Method.TRANSFER,
            user=self.user,
        )
        self.order.refresh_from_db()

        self.assertEqual(self.order.status, Order.Status.PARTIALLY_PAID)
        self.assertEqual(self.order.balance_due, Decimal("200000.00"))
        self.assertIsNone(self.order.total_snapshot)

    def test_split_tender_settles_and_locks_the_total(self):
        record_payment(
            order=self.order,
            amount=Decimal("100000"),
            method=Payment.Method.TRANSFER,
            user=self.user,
        )
        record_payment(
            order=self.order,
            amount=Decimal("200000"),
            method=Payment.Method.CASH,
            tendered=Decimal("500000"),
            user=self.user,
        )
        self.order.refresh_from_db()

        self.assertEqual(self.order.status, Order.Status.PAID)
        self.assertEqual(self.order.balance_due, Decimal("0.00"))
        self.assertEqual(self.order.total_snapshot, Decimal("300000.00"))
        self.assertIsNotNone(self.order.settled_at)

        cash = Payment.objects.get(method=Payment.Method.CASH)
        self.assertEqual(cash.change_amount, Decimal("300000.00"))

    def test_locked_total_survives_a_later_price_edit(self):
        """ຮູບແບບທີ 16 — ແກ້ສ່ວນຫຼຸດຫຼັງຈ່າຍແລ້ວ ຍອດບິນເກົ່າຕ້ອງບໍ່ຂະຫຍັບ"""
        record_payment(
            order=self.order,
            amount=Decimal("300000"),
            method=Payment.Method.CASH,
            user=self.user,
        )
        self.order.refresh_from_db()

        self.order.discount = Decimal("50000")
        self.order.save(update_fields=["discount"])
        self.order.refresh_from_db()

        self.assertEqual(self.order.effective_total, Decimal("300000.00"))
        self.assertEqual(self.order.balance_due, Decimal("0.00"))

    def test_overpaying_is_rejected_and_nothing_is_written(self):
        with self.assertRaises(ValidationError):
            record_payment(
                order=self.order,
                amount=Decimal("400000"),
                method=Payment.Method.CASH,
                user=self.user,
            )
        self.assertFalse(Payment.objects.exists())

    def test_same_idempotency_key_does_not_charge_twice(self):
        """ຮູບແບບທີ 13 — ກົດສອງເທື່ອ/ເນັດຊ້າ ບໍ່ໃຫ້ບັນທຶກສອງແຖວ"""
        key = uuid.uuid4()
        first, created_first = record_payment(
            order=self.order,
            amount=Decimal("100000"),
            method=Payment.Method.CASH,
            user=self.user,
            idempotency_key=key,
        )
        second, created_second = record_payment(
            order=self.order,
            amount=Decimal("100000"),
            method=Payment.Method.CASH,
            user=self.user,
            idempotency_key=key,
        )

        self.assertTrue(created_first)
        self.assertFalse(created_second)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Payment.objects.count(), 1)

    def test_voided_payment_reopens_the_balance(self):
        payment, _created = record_payment(
            order=self.order,
            amount=Decimal("300000"),
            method=Payment.Method.CASH,
            user=self.user,
        )
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAID)

        void_payment(payment=payment, user=self.user, reason="ກົດຜິດບິນ")
        self.order.refresh_from_db()

        self.assertEqual(self.order.status, Order.Status.OPEN)
        self.assertEqual(self.order.balance_due, Decimal("300000.00"))

    def test_refund_line_marks_the_order_refunded(self):
        record_payment(
            order=self.order,
            amount=Decimal("300000"),
            method=Payment.Method.CASH,
            user=self.user,
        )
        record_payment(
            order=self.order,
            amount=Decimal("300000"),
            method=Payment.Method.CASH,
            kind=Payment.Kind.REFUND,
            user=self.user,
        )
        self.order.refresh_from_db()

        self.assertEqual(self.order.status, Order.Status.REFUNDED)
        self.assertEqual(self.order.amount_paid, Decimal("0.00"))

    def test_foreign_currency_locks_the_rate_and_converts_to_base(self):
        """ຮູບແບບທີ 10 — ເກັບອັດຕາໄວ້ ບໍ່ດັ່ງນັ້ນທຽບບັນຊີຄືນບໍ່ໄດ້"""
        payment, _created = record_payment(
            order=self.order,
            amount=Decimal("500"),
            method=Payment.Method.TRANSFER,
            currency="THB",
            fx_rate=Decimal("600"),
            user=self.user,
        )
        self.order.refresh_from_db()

        self.assertEqual(payment.fx_rate, Decimal("600"))
        self.assertEqual(payment.base_amount, Decimal("300000.00"))
        self.assertEqual(self.order.status, Order.Status.PAID)

    def test_missing_exchange_rate_is_refused(self):
        with self.assertRaises(ValidationError):
            record_payment(
                order=self.order,
                amount=Decimal("500"),
                method=Payment.Method.TRANSFER,
                currency="THB",
                user=self.user,
            )


class CheckoutViewTest(TestCase):
    """ໜ້າຄິດເງິນ /pos/orders/<pk>/checkout/"""

    def setUp(self):
        self.user = get_user_model().objects.create_user("front", password="pw12345678")
        self.client.force_login(self.user)
        self.customer = Customer.objects.create(name="ທ້າວ ສີ", phone="02055551111")
        self.order = Order.objects.create(customer=self.customer, vat_rate=0)
        OrderItem.objects.create(
            order=self.order,
            description="ຟື້ນຟູພື້ນເກີບ",
            quantity=1,
            unit_price=Decimal("280000.00"),
        )

    def test_checkout_page_shows_balance_and_a_fresh_idempotency_key(self):
        response = self.client.get(reverse("pos:checkout", args=[self.order.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["balance_due"], Decimal("280000.00"))
        self.assertContains(response, 'name="idempotency_key"')

    def test_posting_a_payment_records_it_and_redirects(self):
        response = self.client.post(
            reverse("pos:take_payment", args=[self.order.pk]),
            {
                "amount": "280000",
                "tendered": "300000",
                "method": "cash",
                "currency": "LAK",
                "idempotency_key": str(uuid.uuid4()),
            },
        )

        self.assertRedirects(response, reverse("pos:invoice", args=[self.order.pk]))
        payment = Payment.objects.get()
        self.assertEqual(payment.change_amount, Decimal("20000.00"))

    def test_partial_payment_returns_to_checkout_to_collect_the_rest(self):
        response = self.client.post(
            reverse("pos:take_payment", args=[self.order.pk]),
            {
                "amount": "100000",
                "method": "qr",
                "currency": "LAK",
                "idempotency_key": str(uuid.uuid4()),
            },
        )

        self.assertRedirects(response, reverse("pos:checkout", args=[self.order.pk]))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PARTIALLY_PAID)

    def test_replaying_the_same_key_does_not_record_twice(self):
        key = str(uuid.uuid4())
        payload = {
            "amount": "100000",
            "method": "cash",
            "currency": "LAK",
            "idempotency_key": key,
        }
        self.client.post(reverse("pos:take_payment", args=[self.order.pk]), payload)
        self.client.post(reverse("pos:take_payment", args=[self.order.pk]), payload)

        self.assertEqual(Payment.objects.count(), 1)

    def test_settled_checkout_offers_handover_and_receipt(self):
        """ໜ້າຫຼັງຈ່າຍຄົບ (ຮູບແບບທີ 17) — ຢ່າໂຍນກັບໄປໜ້າຂາຍທັນທີ"""
        record_payment(
            order=self.order,
            amount=Decimal("280000"),
            method=Payment.Method.CASH,
            user=self.user,
        )

        response = self.client.get(reverse("pos:checkout", args=[self.order.pk]))

        self.assertEqual(response.context["balance_due"], Decimal("0.00"))
        self.assertContains(response, reverse("pos:handover", args=[self.order.pk]))
        self.assertContains(response, reverse("pos:invoice", args=[self.order.pk]))

    def test_void_requires_manager_role(self):
        payment, _created = record_payment(
            order=self.order,
            amount=Decimal("100000"),
            method=Payment.Method.CASH,
            user=self.user,
        )

        response = self.client.post(
            reverse("pos:void_payment", args=[self.order.pk, payment.pk])
        )

        self.assertEqual(response.status_code, 403)
        payment.refresh_from_db()
        self.assertIsNone(payment.voided_at)

    def test_manager_can_void_a_payment(self):
        manager = get_user_model().objects.create_superuser(
            "boss", "boss@example.com", "pw12345678"
        )
        payment, _created = record_payment(
            order=self.order,
            amount=Decimal("100000"),
            method=Payment.Method.CASH,
            user=self.user,
        )

        self.client.force_login(manager)
        self.client.post(
            reverse("pos:void_payment", args=[self.order.pk, payment.pk]),
            {"reason": "ກົດຜິດ"},
        )

        payment.refresh_from_db()
        self.assertIsNotNone(payment.voided_at)
        self.assertEqual(payment.voided_by, manager)


class HandoverTest(TestCase):
    """ໜ້າສົ່ງມອບເຄື່ອງ — ຖືກ gate ດ້ວຍຍອດຄ້າງ (ຮູບແບບທີ 19)"""

    def setUp(self):
        self.user = get_user_model().objects.create_user("desk", password="pw12345678")
        self.client.force_login(self.user)
        self.customer = Customer.objects.create(name="ນາງ ຄຳ", phone="02055552222")
        self.slot = StorageSlot.objects.create(zone="A", cabinet=1, position=3)
        self.asset = Asset.objects.create(
            customer=self.customer,
            brand="Nike",
            model_name="Air Force 1",
            status=Asset.Status.READY,
            storage_slot=self.slot,
        )
        self.order = Order.objects.create(customer=self.customer, vat_rate=0)
        OrderItem.objects.create(
            order=self.order,
            asset=self.asset,
            description="ຊັກເກີບ",
            quantity=1,
            unit_price=Decimal("150000.00"),
        )

    def test_handover_is_locked_while_a_balance_is_due(self):
        # ພາສາເລີ່ມຕົ້ນຂອງລະບົບຄືລາວ — assert ຄຳລາວ ເພື່ອຄຸມທັງ logic ແລະ ຄຳແປ
        response = self.client.get(reverse("pos:handover", args=[self.order.pk]))
        self.assertContains(response, "ລັອກການສົ່ງມອບໄວ້", status_code=200)

        self.client.post(
            reverse("pos:handover", args=[self.order.pk]),
            {"asset_ids": [str(self.asset.pk)], "received_to": "ນາງ ຄຳ"},
        )
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, Asset.Status.READY)

    def test_service_layer_refuses_handover_with_a_balance(self):
        with self.assertRaises(ValidationError):
            hand_over_asset(order=self.order, asset=self.asset, user=self.user)

    def test_handover_after_full_payment_records_custody(self):
        record_payment(
            order=self.order,
            amount=Decimal("150000"),
            method=Payment.Method.CASH,
            user=self.user,
        )

        self.client.post(
            reverse("pos:handover", args=[self.order.pk]),
            {"asset_ids": [str(self.asset.pk)], "received_to": "ນາງ ຄຳ"},
        )
        self.asset.refresh_from_db()

        self.assertEqual(self.asset.status, Asset.Status.RETURNED)
        self.assertEqual(self.asset.returned_to, "ນາງ ຄຳ")
        self.assertEqual(self.asset.returned_by, self.user)
        self.assertIsNotNone(self.asset.completed_at)
        # ບ່ອນເກັບຕ້ອງຖືກປ່ອຍວ່າງ ເມື່ອເກີບອອກຈາກຮ້ານແລ້ວ
        self.assertIsNone(self.asset.storage_slot)

    def test_handover_page_unlocks_once_the_bill_is_settled(self):
        record_payment(
            order=self.order,
            amount=Decimal("150000"),
            method=Payment.Method.CASH,
            user=self.user,
        )

        response = self.client.get(reverse("pos:handover", args=[self.order.pk]))

        self.assertEqual(response.context["balance_due"], Decimal("0.00"))
        self.assertNotContains(response, "Handover locked")
        self.assertContains(response, self.asset.ticket_number)

    def test_asset_from_another_order_cannot_be_handed_over(self):
        other_asset = Asset.objects.create(
            customer=self.customer, brand="Adidas", status=Asset.Status.READY
        )
        record_payment(
            order=self.order,
            amount=Decimal("150000"),
            method=Payment.Method.CASH,
            user=self.user,
        )
        self.order.refresh_from_db()

        with self.assertRaises(ValidationError):
            hand_over_asset(order=self.order, asset=other_asset, user=self.user)


class OpenOrdersTest(TestCase):
    """ໜ້າ "ບິນຄ້າງ" — ປະຕູທາງເຂົ້າຕອນລູກຄ້າມາຮັບເກີບ (ຮູບແບບທີ 15)"""

    def setUp(self):
        self.user = get_user_model().objects.create_user("parked", password="pw12345678")
        self.client.force_login(self.user)
        self.customer = Customer.objects.create(name="ທ້າວ ບຸນ", phone="02055553333")

    def _order_with_total(self, amount):
        order = Order.objects.create(customer=self.customer, vat_rate=0)
        OrderItem.objects.create(
            order=order, description="ຊັກເກີບ", quantity=1, unit_price=amount
        )
        return order

    def test_lists_open_and_partially_paid_bills_with_outstanding_total(self):
        open_order = self._order_with_total(Decimal("150000"))
        partial = self._order_with_total(Decimal("300000"))
        record_payment(
            order=partial,
            amount=Decimal("100000"),
            method=Payment.Method.CASH,
            user=self.user,
        )
        settled = self._order_with_total(Decimal("200000"))
        record_payment(
            order=settled,
            amount=Decimal("200000"),
            method=Payment.Method.CASH,
            user=self.user,
        )

        response = self.client.get(reverse("pos:open_orders"))
        listed = {row["order"].pk for row in response.context["rows"]}

        self.assertEqual(listed, {open_order.pk, partial.pk})
        self.assertEqual(response.context["total_outstanding"], Decimal("350000.00"))

    def test_scanning_a_ticket_jumps_straight_to_checkout(self):
        """ສະແກນປ້າຍເກີບ → ເຂົ້າໜ້າຄິດເງິນເລີຍ ບໍ່ຕ້ອງກົດຊ້ຳ"""
        asset = Asset.objects.create(
            customer=self.customer, brand="Vans", status=Asset.Status.READY
        )
        order = self._order_with_total(Decimal("150000"))
        OrderItem.objects.filter(order=order).update(asset=asset)

        response = self.client.get(
            reverse("pos:open_orders"), {"q": asset.ticket_number, "scan": "1"}
        )

        self.assertRedirects(response, reverse("pos:checkout", args=[order.pk]))

    def test_scanning_a_qr_portal_url_resolves_to_the_bill(self):
        asset = Asset.objects.create(
            customer=self.customer, brand="Vans", status=Asset.Status.READY
        )
        order = self._order_with_total(Decimal("150000"))
        OrderItem.objects.filter(order=order).update(asset=asset)

        response = self.client.get(
            reverse("pos:open_orders"),
            {"q": f"https://shop.example.com/t/{asset.public_token}/", "scan": "1"},
        )

        self.assertRedirects(response, reverse("pos:checkout", args=[order.pk]))

    def test_scanning_an_order_number_opens_that_bill(self):
        order = self._order_with_total(Decimal("150000"))

        response = self.client.get(
            reverse("pos:open_orders"), {"q": order.order_number, "scan": "1"}
        )

        self.assertRedirects(response, reverse("pos:checkout", args=[order.pk]))

    def test_scanning_a_collected_pair_explains_instead_of_showing_nothing(self):
        asset = Asset.objects.create(
            customer=self.customer, brand="Vans", status=Asset.Status.RETURNED
        )
        order = self._order_with_total(Decimal("150000"))
        OrderItem.objects.filter(order=order).update(asset=asset)
        record_payment(
            order=order,
            amount=Decimal("150000"),
            method=Payment.Method.CASH,
            user=self.user,
        )

        response = self.client.get(
            reverse("pos:open_orders"), {"q": asset.ticket_number, "scan": "1"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ບໍ່ມີບິນຄ້າງ")

    def test_unknown_scan_code_reports_an_error(self):
        response = self.client.get(
            reverse("pos:open_orders"), {"q": "TK-NOT-REAL-0001", "scan": "1"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ບໍ່ພົບຂໍ້ມູນທີ່ຕົງກັບລະຫັດທີ່ສະແກນ")

    def test_typed_search_does_not_jump_to_checkout(self):
        """ພິມຄົ້ນຫາເອງ (ບໍ່ມີ scan=1) ຕ້ອງຢູ່ໜ້າລາຍການຄືເກົ່າ"""
        order = self._order_with_total(Decimal("150000"))

        response = self.client.get(
            reverse("pos:open_orders"), {"q": order.order_number}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["rows"]), 1)

    def test_search_matches_ticket_number(self):
        asset = Asset.objects.create(
            customer=self.customer, brand="Vans", status=Asset.Status.READY
        )
        order = self._order_with_total(Decimal("150000"))
        OrderItem.objects.filter(order=order).update(asset=asset)

        response = self.client.get(
            reverse("pos:open_orders"), {"q": asset.ticket_number}
        )

        self.assertEqual(len(response.context["rows"]), 1)
        self.assertEqual(response.context["rows"][0]["order"].pk, order.pk)


class PosIncomeReachesAccountingTest(TestCase):
    """S6 — ເງິນທີ່ຮັບໜ້າຮ້ານຕ້ອງໄຫຼເຂົ້າຍອດນັບເງິນຂອງບັນຊີ"""

    def setUp(self):
        self.user = get_user_model().objects.create_user("acct", password="pw12345678")
        self.customer = Customer.objects.create(name="ທ້າວ ບັນຊີ", phone="02055554444")
        self.order = Order.objects.create(customer=self.customer, vat_rate=0)
        OrderItem.objects.create(
            order=self.order,
            description="ຊັກເກີບ",
            quantity=1,
            unit_price=Decimal("150000.00"),
        )

    def test_cash_payment_counts_towards_expected_cash(self):
        from accounting.models import CashBook
        from accounting.services import totals_by_currency

        record_payment(
            order=self.order,
            amount=Decimal("150000"),
            method=Payment.Method.CASH,
            user=self.user,
        )

        today = timezone.localdate()
        totals = totals_by_currency(
            today, today, payment_method=CashBook.PaymentMethod.CASH
        )
        self.assertEqual(totals["LAK"]["income"], Decimal("150000.00"))

    def test_voided_payment_drops_out_of_the_cash_count(self):
        from accounting.models import CashBook
        from accounting.services import totals_by_currency

        payment, _created = record_payment(
            order=self.order,
            amount=Decimal("150000"),
            method=Payment.Method.CASH,
            user=self.user,
        )
        void_payment(payment=payment, user=self.user, reason="ນັບຜິດ")

        today = timezone.localdate()
        totals = totals_by_currency(
            today, today, payment_method=CashBook.PaymentMethod.CASH
        )
        self.assertEqual(totals["LAK"]["income"], Decimal("0"))


class SendStampCardImageTest(TestCase):
    """ສົ່ງ *ຮູບ* ບັດ Stamp ຜ່ານ WhatsApp Cloud API"""

    def setUp(self):
        self.user = get_user_model().objects.create_user("sender", password="pw12345678")
        self.client.force_login(self.user)
        self.customer = Customer.objects.create(name="ທ້າວ ທົດສອບ", phone="02055551234")
        self.order = Order.objects.create(
            customer=self.customer, status=Order.Status.PAID
        )

    @override_settings(
        WHATSAPP_ACCESS_TOKEN="tok", WHATSAPP_PHONE_NUMBER_ID="123"
    )
    def test_sends_image_message_with_public_card_url(self):
        with patch("notifications.services.requests.post") as post:
            post.return_value.ok = True
            response = self.client.post(
                reverse("pos:send_stamp_card", args=[self.order.pk])
            )

        self.assertEqual(response.status_code, 302)
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["type"], "image")
        self.assertIn("/image.png", payload["image"]["link"])
        # ຮູບແນບໄປແລ້ວ — caption ບໍ່ຄວນມີລິ້ງຊ້ຳອີກ
        self.assertNotIn("http", payload["image"]["caption"])
        self.assertIn("Stamp", payload["image"]["caption"])

    @override_settings(
        WHATSAPP_ACCESS_TOKEN="tok", WHATSAPP_PHONE_NUMBER_ID="123"
    )
    def test_successful_send_is_logged(self):
        from notifications.models import NotificationLog

        with patch("notifications.services.requests.post") as post:
            post.return_value.ok = True
            self.client.post(reverse("pos:send_stamp_card", args=[self.order.pk]))

        log = NotificationLog.objects.get(customer=self.customer)
        self.assertTrue(log.is_sent)
        self.assertIsNone(log.asset)

    def test_without_cloud_api_it_reports_failure_instead_of_crashing(self):
        response = self.client.post(
            reverse("pos:send_stamp_card", args=[self.order.pk]), follow=True
        )
        self.assertEqual(response.status_code, 200)
        text = " ".join(str(m) for m in response.context["messages"])
        self.assertIn("WHATSAPP_ACCESS_TOKEN", text)

    def test_invoice_falls_back_to_manual_link_without_cloud_api(self):
        response = self.client.get(reverse("pos:invoice", args=[self.order.pk]))
        self.assertFalse(response.context["whatsapp_api_ready"])
        self.assertContains(response, "api.whatsapp.com")

    @override_settings(
        WHATSAPP_ACCESS_TOKEN="tok", WHATSAPP_PHONE_NUMBER_ID="123"
    )
    def test_invoice_shows_auto_send_button_with_cloud_api(self):
        response = self.client.get(reverse("pos:invoice", args=[self.order.pk]))
        self.assertTrue(response.context["whatsapp_api_ready"])
        self.assertContains(response, "ສົ່ງຮູບບັດ Stamp")

    def test_get_request_does_not_send(self):
        with patch("notifications.services.requests.post") as post:
            self.client.get(reverse("pos:send_stamp_card", args=[self.order.pk]))
        post.assert_not_called()


class QuotationKeepsAssetLinksTest(TestCase):
    """ໃບສະເໜີລາຄາຕ້ອງ *ອັບເດດ* ລາຍການ ບໍ່ແມ່ນລຶບແລ້ວສ້າງໃໝ່

    ການລຶບ-ສ້າງໃໝ່ເຮັດໃຫ້ການຜູກ "ບໍລິການ ↔ ເກີບແຕ່ລະຄູ່" ທີ່ POS ສ້າງໄວ້ຫາຍໄປ
    ແລ້ວເກີບຄູ່ທີ 2 ຈະຫຼຸດອອກຈາກບິນ ຈົນສົ່ງມອບຜ່ານໜ້າ POS ບໍ່ໄດ້
    """

    def setUp(self):
        self.user = get_user_model().objects.create_user("cash", password="pw12345678")
        self.client.force_login(self.user)
        self.wash = ServiceType.objects.create(
            name="ຊັກສະອາດທົ່ວໄປ",
            category=ServiceType.Category.PRIMARY,
            work_type=ServiceType.WorkType.WASH,
            price=Decimal("90000"),
        )
        self.repair = ServiceType.objects.create(
            name="ສ້ອມພື້ນເກີບ",
            category=ServiceType.Category.ADD_ON,
            work_type=ServiceType.WorkType.REPAIR,
            price=Decimal("180000"),
        )

    def _open_two_pair_order(self):
        self.client.post(
            reverse("pos:create"),
            {
                "next_action": "quotation",
                "customer_name": "ທ້າວ ສີ",
                "customer_phone": "02055553333",
                "item_indices": "0,1",
                "brand_0": "Nike",
                "model_name_0": "Air Force 1",
                "service_0": self.wash.pk,
                "brand_1": "Adidas",
                "model_name_1": "Samba",
                "service_1": self.repair.pk,
            },
        )
        return Order.objects.get()

    def test_both_pairs_stay_on_the_bill_after_the_quotation_step(self):
        order = self._open_two_pair_order()
        nike = Asset.objects.get(brand="Nike")
        adidas = Asset.objects.get(brand="Adidas")

        self.client.post(
            reverse("pos:quotation", args=[order.pk]),
            {"services": [str(self.wash.pk), str(self.repair.pk)], "vat_rate": "10"},
        )
        order.refresh_from_db()

        self.assertEqual(
            {a.pk for a in order.assets()}, {nike.pk, adidas.pk}
        )
        # ແຕ່ລະຄູ່ຍັງຖືວຽກຂອງຕົນ ບໍ່ຖືກລວມໃສ່ຄູ່ດຽວ
        self.assertEqual(
            [i.service_type_id for i in nike.order_items.all()], [self.wash.pk]
        )
        self.assertEqual(
            [i.service_type_id for i in adidas.order_items.all()], [self.repair.pk]
        )
        self.assertEqual(
            {(s.asset_id, s.service_type_id) for s in AssetService.objects.all()},
            {(nike.pk, self.wash.pk), (adidas.pk, self.repair.pk)},
        )

    def test_subtotal_counts_every_pair(self):
        order = self._open_two_pair_order()

        self.client.post(
            reverse("pos:quotation", args=[order.pk]),
            {"services": [str(self.wash.pk), str(self.repair.pk)], "vat_rate": "0"},
        )
        order.refresh_from_db()

        self.assertEqual(order.subtotal, Decimal("270000"))

    def test_unticking_a_service_drops_its_item_and_pending_card(self):
        order = self._open_two_pair_order()
        nike = Asset.objects.get(brand="Nike")

        self.client.post(
            reverse("pos:quotation", args=[order.pk]),
            {"services": [str(self.repair.pk)], "vat_rate": "10"},
        )

        self.assertEqual(nike.order_items.count(), 0)
        self.assertFalse(
            AssetService.objects.filter(
                asset=nike, service_type=self.wash
            ).exists()
        )

    def test_work_already_started_keeps_its_card_when_removed_from_the_bill(self):
        order = self._open_two_pair_order()
        nike = Asset.objects.get(brand="Nike")
        job = AssetService.objects.get(asset=nike, service_type=self.wash)
        job.status = AssetService.Status.IN_PROGRESS
        job.save(update_fields=["status"])

        self.client.post(
            reverse("pos:quotation", args=[order.pk]),
            {"services": [str(self.repair.pk)], "vat_rate": "10"},
        )

        # ຊ່າງລົງມືແລ້ວ — ຮັກສາໄວ້ເປັນປະຫວັດ ເຖິງແມ່ນຫຼຸດອອກຈາກບິນ
        self.assertTrue(AssetService.objects.filter(pk=job.pk).exists())

    def test_a_new_bill_does_not_adopt_an_older_pair_of_the_same_customer(self):
        customer = Customer.objects.create(name="ນາງ ດາ", phone="02055554444")
        old_asset = Asset.objects.create(
            customer=customer, brand="Vans", model_name="Old Skool"
        )
        order = Order.objects.create(customer=customer)

        self.client.post(
            reverse("pos:quotation", args=[order.pk]),
            {"services": [str(self.wash.pk)], "vat_rate": "10"},
        )

        self.assertEqual(order.assets(), [])
        self.assertEqual(old_asset.order_items.count(), 0)

    def test_a_service_added_at_the_quotation_step_lands_on_this_bill_pair(self):
        order = self._open_two_pair_order()
        nike = Asset.objects.get(brand="Nike")

        self.client.post(
            reverse("pos:quotation", args=[order.pk]),
            {
                "services": [
                    str(self.wash.pk),
                    str(self.repair.pk),
                    str(
                        ServiceType.objects.create(
                            name="ແຕ່ງສີ", price=Decimal("50000")
                        ).pk
                    ),
                ],
                "vat_rate": "10",
            },
        )
        order.refresh_from_db()

        extra = order.items.get(service_type__name="ແຕ່ງສີ")
        self.assertEqual(extra.asset_id, nike.pk)
        self.assertEqual(order.items.count(), 3)

    def test_replacing_every_service_still_lands_on_this_bill_pair(self):
        """ຖອດບໍລິການເດີມອອກໝົດ ແລ້ວເລືອກອັນໃໝ່ — ຍັງຕ້ອງຜູກກັບຄູ່ຂອງບິນນີ້"""
        order = self._open_two_pair_order()
        nike = Asset.objects.get(brand="Nike")
        spa = ServiceType.objects.create(name="ສະປາພຣີມຽມ", price=Decimal("220000"))

        self.client.post(
            reverse("pos:quotation", args=[order.pk]),
            {"services": [str(spa.pk)], "vat_rate": "0"},
        )
        order.refresh_from_db()

        self.assertEqual(order.items.count(), 1)
        self.assertEqual(order.items.get().asset_id, nike.pk)
        self.assertEqual(order.subtotal, Decimal("220000"))
