"""ເທັສການຕັດສະຕັອກອັດຕະໂນມັດ (Scope 2.1)"""

from decimal import Decimal

from django.test import TestCase

from crm.models import Customer
from pos.models import Order, OrderItem, Payment, ServiceType
from pos.services import record_payment

from .models import ServiceSupply, StockMovement, Supply


class AutoStockDeductionTest(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(name="ນາງ ສົມໃຈ", phone="02055559999")
        self.soap = Supply.objects.create(
            name="ນ້ຳຢາຊັກເກີບ", sku="CLN-100", unit="ຂວດ", quantity_on_hand=50
        )
        self.brush = Supply.objects.create(
            name="ແປງຂັດ", sku="BRS-100", unit="ອັນ", quantity_on_hand=20
        )
        self.deep_clean = ServiceType.objects.create(
            name="Deep Clean", price=Decimal("150000.00")
        )
        ServiceSupply.objects.create(
            service_type=self.deep_clean, supply=self.soap, quantity_per_unit=2
        )
        ServiceSupply.objects.create(
            service_type=self.deep_clean, supply=self.brush, quantity_per_unit=1
        )

    def _paid_order(self, quantity=1):
        order = Order.objects.create(customer=self.customer, vat_rate=0)
        OrderItem.objects.create(
            order=order,
            service_type=self.deep_clean,
            quantity=quantity,
            unit_price=Decimal("150000.00"),
        )
        record_payment(
            order=order,
            amount=order.total,
            method=Payment.Method.CASH,
        )
        return order

    def test_paying_a_bill_deducts_the_supplies_the_service_uses(self):
        """ຮູບແບບຫຼັກ — ຮ້ານບໍ່ຕ້ອງໄປຕັດນ້ຳຢາເອງດ້ວຍມືອີກ"""
        self._paid_order()

        self.soap.refresh_from_db()
        self.brush.refresh_from_db()
        self.assertEqual(self.soap.quantity_on_hand, 48)
        self.assertEqual(self.brush.quantity_on_hand, 19)

    def test_quantity_on_the_bill_multiplies_the_recipe(self):
        """ຊັກ 3 ຄູ່ໃນບິນດຽວ ຕ້ອງຫັກນ້ຳຢາ 3 ເທົ່າ"""
        self._paid_order(quantity=3)

        self.soap.refresh_from_db()
        self.assertEqual(self.soap.quantity_on_hand, 44)

    def test_movements_are_linked_to_the_bill_that_caused_them(self):
        order = self._paid_order()

        movements = StockMovement.objects.filter(order=order)
        self.assertEqual(movements.count(), 2)
        for movement in movements:
            self.assertEqual(movement.movement_type, StockMovement.MovementType.OUT)
            self.assertIn(order.order_number, movement.note)

    def test_paying_the_rest_of_a_split_bill_does_not_deduct_twice(self):
        """ຈ່າຍແບ່ງງວດ — ຫັກສະຕັອກເທື່ອດຽວຕອນຊຳລະຄົບ ບໍ່ແມ່ນທຸກງວດ"""
        order = Order.objects.create(customer=self.customer, vat_rate=0)
        OrderItem.objects.create(
            order=order,
            service_type=self.deep_clean,
            quantity=1,
            unit_price=Decimal("150000.00"),
        )

        record_payment(order=order, amount=Decimal("50000.00"), method=Payment.Method.CASH)
        self.soap.refresh_from_db()
        self.assertEqual(self.soap.quantity_on_hand, 50, "ຈ່າຍບໍ່ຄົບ ຍັງບໍ່ຄວນຫັກ")

        record_payment(order=order, amount=Decimal("100000.00"), method=Payment.Method.CASH)
        self.soap.refresh_from_db()
        self.assertEqual(self.soap.quantity_on_hand, 48)
        self.assertEqual(StockMovement.objects.filter(order=order).count(), 2)

    def test_a_service_without_a_recipe_deducts_nothing(self):
        plain = ServiceType.objects.create(name="Basic Clean", price=Decimal("90000.00"))
        order = Order.objects.create(customer=self.customer, vat_rate=0)
        OrderItem.objects.create(
            order=order, service_type=plain, quantity=1, unit_price=Decimal("90000.00")
        )
        record_payment(order=order, amount=order.total, method=Payment.Method.CASH)

        self.assertFalse(StockMovement.objects.filter(order=order).exists())
        self.soap.refresh_from_db()
        self.assertEqual(self.soap.quantity_on_hand, 50)

    def test_two_services_sharing_a_supply_produce_one_combined_row(self):
        """ອຸປະກອນຕົວດຽວກັນຖືກໃຊ້ 2 ບໍລິການ — ຄວນອອກແຖວດຽວ ອ່ານປະຫວັດງ່າຍ"""
        repair = ServiceType.objects.create(name="Repair", price=Decimal("180000.00"))
        ServiceSupply.objects.create(
            service_type=repair, supply=self.soap, quantity_per_unit=1
        )

        order = Order.objects.create(customer=self.customer, vat_rate=0)
        OrderItem.objects.create(
            order=order,
            service_type=self.deep_clean,
            quantity=1,
            unit_price=Decimal("150000.00"),
        )
        OrderItem.objects.create(
            order=order, service_type=repair, quantity=1, unit_price=Decimal("180000.00")
        )
        record_payment(order=order, amount=order.total, method=Payment.Method.CASH)

        soap_movements = StockMovement.objects.filter(order=order, supply=self.soap)
        self.assertEqual(soap_movements.count(), 1)
        self.assertEqual(soap_movements.first().quantity, 3)
