from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from pos.models import ServiceType

from .models import ServiceSupply, StockMovement, Supply


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


class ServiceRecipeViewTest(TestCase):
    """ສູດອຸປະກອນຕ້ອງຕັ້ງໄດ້ຈາກໜ້າສາງ — ພະນັກງານຮ້ານເຂົ້າ admin ບໍ່ໄດ້"""

    def setUp(self):
        user = get_user_model().objects.create_user("inventory-staff")
        self.client.force_login(user)
        self.supply = Supply.objects.create(
            name="ນ້ຳຢາຊັກເກີບ", sku="CLN-900", unit="ຂວດ", quantity_on_hand=10
        )
        self.service = ServiceType.objects.create(
            name="Deep Clean", price=Decimal("150000.00")
        )

    def test_staff_can_attach_a_material_to_a_service(self):
        response = self.client.post(
            reverse("inventory:add_recipe"),
            {
                "service_type": self.service.pk,
                "supply": self.supply.pk,
                "quantity_per_unit": "3",
            },
        )

        self.assertEqual(response.status_code, 302)
        recipe = ServiceSupply.objects.get()
        self.assertEqual(recipe.service_type, self.service)
        self.assertEqual(recipe.quantity_per_unit, 3)

    def test_adding_the_same_material_twice_updates_it_instead_of_duplicating(self):
        """ແຖວຊ້ຳຈະເຮັດໃຫ້ຫັກສະຕັອກສອງເທື່ອຈາກບໍລິການດຽວ"""
        for quantity in ("2", "5"):
            self.client.post(
                reverse("inventory:add_recipe"),
                {
                    "service_type": self.service.pk,
                    "supply": self.supply.pk,
                    "quantity_per_unit": quantity,
                },
            )

        self.assertEqual(ServiceSupply.objects.count(), 1)
        self.assertEqual(ServiceSupply.objects.get().quantity_per_unit, 5)

    def test_a_zero_quantity_is_refused(self):
        response = self.client.post(
            reverse("inventory:add_recipe"),
            {
                "service_type": self.service.pk,
                "supply": self.supply.pk,
                "quantity_per_unit": "0",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ServiceSupply.objects.exists())

    def test_staff_can_remove_a_material_from_a_recipe(self):
        recipe = ServiceSupply.objects.create(
            service_type=self.service, supply=self.supply, quantity_per_unit=1
        )

        self.client.post(reverse("inventory:delete_recipe", args=[recipe.pk]))

        self.assertFalse(ServiceSupply.objects.exists())

    def test_the_page_flags_services_that_still_have_no_recipe(self):
        """ນີ້ຄືສັນຍານທີ່ບອກຮ້ານວ່າເປັນຫຍັງບິນທີ່ຊຳລະແລ້ວຈຶ່ງບໍ່ຫັກສະຕັອກ"""
        active_services = ServiceType.objects.filter(is_active=True).count()

        before = self.client.get(reverse("inventory:index"))
        self.assertEqual(
            before.context["services_without_recipe"], active_services
        )

        ServiceSupply.objects.create(
            service_type=self.service, supply=self.supply, quantity_per_unit=1
        )

        after = self.client.get(reverse("inventory:index"))
        self.assertEqual(
            after.context["services_without_recipe"], active_services - 1
        )

    def test_a_mistyped_stock_figure_does_not_crash_the_page(self):
        """ຟອມສົ່ງຂໍ້ຄວາມມາ — ຄ່າຫວ່າງເຄີຍເປັນໜ້າ 500"""
        response = self.client.post(
            reverse("inventory:add_supply"),
            {
                "name": "ຜ້າເຊັດ",
                "sku": "CLT-900",
                "unit": "ຜືນ",
                "quantity_on_hand": "",
                "reorder_level": "abc",
                "cost_price": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        supply = Supply.objects.get(sku="CLT-900")
        self.assertEqual(supply.quantity_on_hand, 0)
        self.assertEqual(supply.reorder_level, 0)
