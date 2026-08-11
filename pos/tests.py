from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from asset_intake.models import Asset, StorageSlot
from crm.models import Customer

from .models import Order, OrderItem, ServiceType


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
            for cabinet in zone["cabinets"]
            for slot in cabinet["slots"]
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
