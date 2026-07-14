from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import StockMovement, Supply


class StockMovementTest(TestCase):
    def setUp(self):
        self.supply = Supply.objects.create(
            name="ນ້ຳຢາຊັກເກີບ", sku="CLN-001", unit="ຂວດ", reorder_level=2
        )

    def test_stock_in_out_adjust(self):
        StockMovement.objects.create(
            supply=self.supply, movement_type=StockMovement.MovementType.IN, quantity=10
        )
        StockMovement.objects.create(
            supply=self.supply, movement_type=StockMovement.MovementType.OUT, quantity=3
        )
        StockMovement.objects.create(
            supply=self.supply,
            movement_type=StockMovement.MovementType.ADJUST,
            quantity=-1,
        )
        self.supply.refresh_from_db()
        self.assertEqual(self.supply.quantity_on_hand, 6)
        self.assertFalse(self.supply.is_low_stock)

    def test_low_stock_flag(self):
        StockMovement.objects.create(
            supply=self.supply, movement_type=StockMovement.MovementType.IN, quantity=2
        )
        self.supply.refresh_from_db()
        self.assertTrue(self.supply.is_low_stock)


class InventoryLanguageTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="inventory-staff", password="test"
        )
        self.supply = Supply.objects.create(
            name="Shoe cleaner",
            sku="CLN-002",
            unit="bottle",
            reorder_level=2,
        )
        StockMovement.objects.create(
            supply=self.supply,
            movement_type=StockMovement.MovementType.IN,
            quantity=1,
        )
        self.client.force_login(self.user)

    def test_inventory_page_switches_between_english_and_lao(self):
        url = reverse("inventory:index")

        self.client.post(reverse("set_language"), {"language": "en", "next": url})
        english = self.client.get(url)
        self.assertContains(english, "Manage materials, stock velocity")
        self.assertContains(english, "Add New Material/Equipment")
        self.assertContains(english, "Low stock")
        self.assertContains(english, "Stock in")
        self.assertContains(english, "Movement Type")

        self.client.post(reverse("set_language"), {"language": "lo", "next": url})
        lao = self.client.get(url)
        self.assertContains(lao, "ຈັດການວັດສະດຸ")
        self.assertContains(lao, "ເພີ່ມວັດສະດຸ/ອຸປະກອນໃໝ່")
        self.assertContains(lao, "ສະຕັອກຕ່ຳ")
        self.assertContains(lao, "ຮັບເຂົ້າ")
        self.assertContains(lao, "ປະເພດການເຄື່ອນໄຫວ")
        self.assertContains(lao, "ລະບົບຈະຄຳນວນເຄື່ອງໝາຍ")

    def test_inventory_csv_uses_selected_language(self):
        index_url = reverse("inventory:index")
        export_url = reverse("inventory:export_csv")

        self.client.post(
            reverse("set_language"), {"language": "lo", "next": index_url}
        )
        response = self.client.get(export_url)
        csv_text = response.content.decode("utf-8-sig")
        self.assertIn("ຈຳນວນຄົງເຫຼືອ", csv_text)
        self.assertIn("ສະຕັອກຕ່ຳ", csv_text)
