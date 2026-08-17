"""ເທັສລະບົບສະສົມຄະແນນ (Scope 2.2)"""

from decimal import Decimal

from django.test import TestCase, override_settings

from crm.models import Customer
from pos.models import Order, OrderItem, Payment, ServiceType
from pos.services import record_payment

from .models import MemberCard, PointTransaction

# ຕົວແທນ "ບໍ່ໄດ້ສົ່ງມາ" — ຈຳເປັນເພາະ customer=None ເປັນຄ່າທີ່ມີຄວາມໝາຍຈິງ (ບິນຂາຍຜ່ານ)
_UNSET = object()


@override_settings(LOYALTY_KIP_PER_POINT=10000)
class LoyaltyPointsTest(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(name="ທ້າວ ສົມພອນ", phone="02055557777")
        self.service = ServiceType.objects.create(
            name="Deep Clean", price=Decimal("150000.00")
        )

    def _order(self, price="150000.00", customer=_UNSET):
        order = Order.objects.create(
            customer=self.customer if customer is _UNSET else customer, vat_rate=0
        )
        OrderItem.objects.create(
            order=order,
            service_type=self.service,
            quantity=1,
            unit_price=Decimal(price),
        )
        return order

    def test_paying_a_bill_in_full_awards_points(self):
        """ຮູບແບບຫຼັກ — ຈ່າຍ 150,000 ກີບ ໄດ້ 15 ຄະແນນ"""
        order = self._order()
        record_payment(order=order, amount=order.total, method=Payment.Method.CASH)

        card = MemberCard.objects.get(customer=self.customer)
        self.assertEqual(card.points_balance, 15)

    def test_the_transaction_records_which_bill_earned_the_points(self):
        order = self._order()
        record_payment(order=order, amount=order.total, method=Payment.Method.CASH)

        entry = PointTransaction.objects.get(order=order)
        self.assertEqual(entry.points, 15)
        self.assertIn(order.order_number, entry.reason)

    def test_a_partly_paid_bill_earns_nothing_yet(self):
        order = self._order()
        record_payment(order=order, amount=Decimal("50000.00"), method=Payment.Method.CASH)

        self.assertFalse(PointTransaction.objects.filter(order=order).exists())

    def test_split_payment_awards_points_once_not_per_instalment(self):
        order = self._order()
        record_payment(order=order, amount=Decimal("50000.00"), method=Payment.Method.CASH)
        record_payment(order=order, amount=Decimal("100000.00"), method=Payment.Method.CASH)

        self.assertEqual(PointTransaction.objects.filter(order=order).count(), 1)
        card = MemberCard.objects.get(customer=self.customer)
        self.assertEqual(card.points_balance, 15)

    def test_points_and_stamps_are_awarded_together(self):
        """ຄະແນນບໍ່ໄດ້ມາແທນ Stamp — ລູກຄ້າໄດ້ທັງສອງຢ່າງຈາກບິນດຽວ"""
        order = self._order()
        record_payment(order=order, amount=order.total, method=Payment.Method.CASH)

        card = MemberCard.objects.get(customer=self.customer)
        self.assertEqual(card.points_balance, 15)
        self.assertEqual(card.stamps_count, 1)

    def test_a_walk_in_bill_without_a_customer_is_skipped(self):
        order = self._order(customer=None)
        record_payment(order=order, amount=order.total, method=Payment.Method.CASH)

        self.assertFalse(PointTransaction.objects.exists())

    @override_settings(LOYALTY_KIP_PER_POINT=0)
    def test_setting_the_rate_to_zero_turns_the_scheme_off(self):
        """ຮ້ານທີ່ຢາກໃຊ້ແຕ່ Stamp ຕັ້ງເປັນ 0 ແລ້ວຄະແນນຈະບໍ່ເດີນ"""
        order = self._order()
        record_payment(order=order, amount=order.total, method=Payment.Method.CASH)

        self.assertFalse(PointTransaction.objects.exists())
        card = MemberCard.objects.get(customer=self.customer)
        self.assertEqual(card.points_balance, 0)
        self.assertEqual(card.stamps_count, 1, "Stamp ຍັງຕ້ອງເດີນຕາມປົກກະຕິ")

    def test_a_bill_smaller_than_one_point_earns_nothing(self):
        order = self._order(price="5000.00")
        record_payment(order=order, amount=order.total, method=Payment.Method.CASH)

        self.assertFalse(PointTransaction.objects.exists())
