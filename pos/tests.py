from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from asset_intake.models import Asset
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
