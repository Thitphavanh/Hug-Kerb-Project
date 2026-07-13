from django.test import TestCase

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
