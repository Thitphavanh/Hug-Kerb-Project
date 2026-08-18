"""ເທັສການຈັດການຍີ່ຫໍ້ ແລະ ລຸ້ນເກີບ (Scope 2.3)"""

import json
import re

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Asset, Brand, ShoeModel
from .views import brand_catalogue

from crm.models import Customer


def catalogue_in_page(html):
    """ດຶງ JSON ຍີ່ຫໍ້ທີ່ຝັງໄວ້ໃນໜ້າອອກມາ"""
    match = re.search(r'id="brand-catalogue"[^>]*>(.*?)</script>', html, re.S)
    return json.loads(match.group(1)) if match else None


class BrandManagementTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="brand-manager", password="test-pass-123"
        )
        self.client.force_login(self.user)
        Brand.objects.all().delete()
        self.nike = Brand.objects.create(name="Nike", sort_order=0)
        self.adidas = Brand.objects.create(name="Adidas", sort_order=1)
        ShoeModel.objects.create(brand=self.nike, name="Air Force 1")
        ShoeModel.objects.create(brand=self.nike, name="Dunk Low")
        ShoeModel.objects.create(brand=self.adidas, name="Samba OG")

    def test_the_page_lists_brands_with_their_models(self):
        response = self.client.get(reverse("asset_intake:brands"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nike")
        self.assertContains(response, "Air Force 1")
        self.assertContains(response, "Samba OG")

    def test_staff_can_add_a_brand(self):
        self.client.post(reverse("asset_intake:brand_create"), {"name": "Puma"})

        self.assertTrue(Brand.objects.filter(name="Puma").exists())

    def test_a_duplicate_brand_is_refused_regardless_of_letter_case(self):
        """ກັນ "nike" ກັບ "Nike" ກາຍເປັນສອງຍີ່ຫໍ້ — ນີ້ຄືບັນຫາເດີມກ່ອນມີໜ້ານີ້"""
        self.client.post(reverse("asset_intake:brand_create"), {"name": "nike"})

        self.assertEqual(Brand.objects.filter(name__iexact="nike").count(), 1)

    def test_an_empty_brand_name_is_refused(self):
        before = Brand.objects.count()
        self.client.post(reverse("asset_intake:brand_create"), {"name": "   "})

        self.assertEqual(Brand.objects.count(), before)

    def test_staff_can_add_a_model_under_a_brand(self):
        self.client.post(
            reverse("asset_intake:model_create", args=[self.adidas.pk]),
            {"name": "Gazelle"},
        )

        self.assertTrue(self.adidas.shoe_models.filter(name="Gazelle").exists())

    def test_the_same_model_cannot_be_added_twice_to_one_brand(self):
        self.client.post(
            reverse("asset_intake:model_create", args=[self.nike.pk]),
            {"name": "air force 1"},
        )

        self.assertEqual(self.nike.shoe_models.filter(name__iexact="air force 1").count(), 1)

    def test_the_same_model_name_may_exist_under_two_brands(self):
        self.client.post(
            reverse("asset_intake:model_create", args=[self.adidas.pk]),
            {"name": "Air Force 1"},
        )

        self.assertTrue(self.adidas.shoe_models.filter(name="Air Force 1").exists())

    def test_deleting_a_brand_keeps_past_items_intact(self):
        """ຄູ່ເກີບເກັບຍີ່ຫໍ້ເປັນຂໍ້ຄວາມ — ລຶບຍີ່ຫໍ້ອອກຈາກລາຍການ ປະຫວັດຕ້ອງບໍ່ຫາຍ"""
        customer = Customer.objects.create(name="ນາງ ດາວ", phone="02055556666")
        asset = Asset.objects.create(customer=customer, brand="Nike", model_name="Dunk Low")

        self.client.post(reverse("asset_intake:brand_delete", args=[self.nike.pk]))

        asset.refresh_from_db()
        self.assertEqual(asset.brand, "Nike")
        self.assertFalse(Brand.objects.filter(pk=self.nike.pk).exists())

    def test_deleting_a_brand_removes_its_models(self):
        self.client.post(reverse("asset_intake:brand_delete", args=[self.nike.pk]))

        self.assertFalse(ShoeModel.objects.filter(brand_id=self.nike.pk).exists())

    def test_an_inactive_brand_disappears_from_the_pickers(self):
        self.nike.is_active = False
        self.nike.save()

        self.assertNotIn("Nike", brand_catalogue())
        self.assertIn("Adidas", brand_catalogue())


class BrandCataloguePageTest(TestCase):
    """ຫົວໃຈຂອງຄຳຂໍ: ເລືອກ Nike → ລຸ້ນເປັນຂອງ Nike, ເລືອກ Adidas → ຂອງ Adidas"""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="picker", password="test-pass-123"
        )
        self.client.force_login(self.user)
        Brand.objects.all().delete()
        nike = Brand.objects.create(name="Nike", sort_order=0)
        adidas = Brand.objects.create(name="Adidas", sort_order=1)
        ShoeModel.objects.create(brand=nike, name="Air Force 1")
        ShoeModel.objects.create(brand=adidas, name="Samba OG")

    def test_the_intake_page_carries_each_brands_own_models(self):
        html = self.client.get(reverse("asset_intake:create")).content.decode()

        catalogue = catalogue_in_page(html)
        self.assertEqual(catalogue["Nike"], ["Air Force 1"])
        self.assertEqual(catalogue["Adidas"], ["Samba OG"])

    def test_the_pos_page_carries_the_same_catalogue(self):
        html = self.client.get(reverse("pos:create")).content.decode()

        catalogue = catalogue_in_page(html)
        self.assertEqual(catalogue["Nike"], ["Air Force 1"])
        self.assertEqual(catalogue["Adidas"], ["Samba OG"])

    def test_the_pos_page_no_longer_hardcodes_its_brand_list(self):
        """ຍີ່ຫໍ້ຕ້ອງມາຈາກຖານຂໍ້ມູນ — ເພີ່ມແລ້ວຕ້ອງເຫັນທັນທີ ບໍ່ຕ້ອງແກ້ໂຄ້ດ"""
        Brand.objects.create(name="Onitsuka Tiger", sort_order=2)

        html = self.client.get(reverse("pos:create")).content.decode()

        self.assertIn("Onitsuka Tiger", catalogue_in_page(html))
        self.assertIn("Onitsuka Tiger", html)

    def test_the_intake_form_only_offers_brands_the_shop_configured(self):
        response = self.client.post(
            reverse("asset_intake:create"),
            {
                "customer_name": "ນາງ ມາລີ",
                "customer_phone": "02055557777",
                "brand": "ຍີ່ຫໍ້ທີ່ບໍ່ມີໃນລາຍການ",
                "model_name": "X",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Asset.objects.filter(model_name="X").exists())

    def test_receiving_a_pair_with_a_configured_brand_works(self):
        response = self.client.post(
            reverse("asset_intake:create"),
            {
                "customer_name": "ນາງ ມາລີ",
                "customer_phone": "02055558888",
                "brand": "Nike",
                "model_name": "Air Force 1",
                "color": "White",
                "size": "42",
            },
        )

        self.assertEqual(response.status_code, 302)
        asset = Asset.objects.get(model_name="Air Force 1")
        self.assertEqual(asset.brand, "Nike")


class BrandPageLanguageTest(TestCase):
    """ໜ້ານີ້ຕ້ອງອ່ານໄດ້ທັງລາວ ແລະ ອັງກິດ (Scope: ສອງພາສາ)"""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="lang-probe", password="test-pass-123"
        )
        self.client.force_login(self.user)
        Brand.objects.all().delete()
        Brand.objects.create(name="Nike", sort_order=0)

    def _page_in(self, language):
        self.client.post(
            reverse("set_language"),
            {"language": language, "next": reverse("asset_intake:brands")},
        )
        return self.client.get(reverse("asset_intake:brands")).content.decode()

    def test_it_renders_in_lao(self):
        html = self._page_in("lo")

        for phrase in ["ຍີ່ຫໍ້ ແລະ ລຸ້ນເກີບ", "ຍີ່ຫໍ້ໃໝ່", "ລຳດັບ", "ເພີ່ມຍີ່ຫໍ້", "ລຶບຍີ່ຫໍ້"]:
            self.assertIn(phrase, html)

    def test_it_renders_in_english(self):
        html = self._page_in("en")

        for phrase in ["Brands and models", "New brand", "Sort order", "Add brand"]:
            self.assertIn(phrase, html)

    def test_sort_order_does_not_reuse_the_bill_word(self):
        """"Order" ຖືກແປເປັນ "ອໍເດີ" ຢູ່ໜ້າ POS — ຊ່ອງລຳດັບຕ້ອງບໍ່ໄປໃຊ້ຄຳນັ້ນ"""
        html = self._page_in("lo")

        self.assertIn("ລຳດັບ", html)
