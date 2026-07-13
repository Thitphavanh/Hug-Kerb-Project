from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from ai_mart_grading.models import Assessment, AssessmentItem, ChecklistItem
from asset_intake.models import Asset
from crm.models import Customer
from digital_member.models import MemberCard, PointTransaction
from inventory.models import StockMovement, Supply
from pos.models import Expense, Order, OrderItem, Payment, ServiceType
from resell_pricing_engine.models import PriceValuation, PromoContent


class Command(BaseCommand):
    help = "Seed realistic demo data for POS, CRM, Inventory, AI Grading, Pricing, and Reports."

    def handle(self, *args, **options):
        today = timezone.localdate()
        now = timezone.now()

        services = self.seed_services()
        customers = self.seed_customers()
        members = self.seed_members(customers)
        supplies = self.seed_inventory()
        assets = self.seed_assets(customers, today, now)
        assessments = self.seed_assessments(assets)
        self.seed_pricing_and_content(assets, assessments)
        orders = self.seed_orders(customers, assets, services, today, now)
        self.seed_payments_and_expenses(orders, today, now)
        self.seed_points(members, orders)
        self.seed_stock_movements(supplies, orders)

        self.stdout.write(
            self.style.SUCCESS(
                "Seeded demo data: "
                f"{len(customers)} customers, {len(services)} services, "
                f"{len(supplies)} supplies, {len(assets)} assets, {len(orders)} orders."
            )
        )

    def seed_services(self):
        rows = [
            ("Deep Clean Service", "150000"),
            ("Premium Spa + Deodorize", "220000"),
            ("Sole Restoration", "300000"),
            ("AI Condition Report", "45000"),
            ("Color Touch-up", "180000"),
        ]
        services = {}
        for name, price in rows:
            service, _ = ServiceType.objects.update_or_create(
                name=name,
                defaults={"price": Decimal(price), "is_active": True},
            )
            services[name] = service
        return services

    def seed_customers(self):
        rows = [
            {
                "phone": "020 5555 0001",
                "name": "ທ້າວ ສົມຊາຍ ສີຫາລາດ",
                "email": "somxay@example.com",
                "line_id": "somxay.hk",
            },
            {
                "phone": "020 9999 0002",
                "name": "ນາງ ມະນີ ຈັນທະວົງ",
                "email": "manee@example.com",
                "line_id": "manee.hk",
            },
            {
                "phone": "020 7777 0003",
                "name": "ທ້າວ ສຸລິຍາ ພົມມະຈັນ",
                "email": "suliya@example.com",
                "line_id": "suliya.hk",
            },
            {
                "phone": "020 2222 0004",
                "name": "ນາງ ອານຸສອນ ແກ້ວມະນີ",
                "email": "anusone@example.com",
                "line_id": "anusone.hk",
            },
        ]
        customers = {}
        for row in rows:
            phone = row.pop("phone")
            customer, _ = Customer.objects.update_or_create(phone=phone, defaults=row)
            customers[phone] = customer
        return customers

    def seed_members(self, customers):
        rows = [
            ("020 5555 0001", "HK-DEMO-001", MemberCard.Tier.GOLD, 2450),
            ("020 9999 0002", "HK-DEMO-002", MemberCard.Tier.SILVER, 1200),
            ("020 7777 0003", "HK-DEMO-003", MemberCard.Tier.BASIC, 450),
        ]
        members = {}
        for phone, card_number, tier, points in rows:
            member, _ = MemberCard.objects.update_or_create(
                customer=customers[phone],
                defaults={
                    "card_number": card_number,
                    "tier": tier,
                    "points_balance": points,
                    "is_active": True,
                },
            )
            members[phone] = member
        return members

    def seed_inventory(self):
        rows = [
            ("MAT-001", "Premium Leather Cleaner", "bottle", 8, 10, "75000"),
            ("MAT-002", "Microfiber Towel", "pcs", 120, 30, "12000"),
            ("MAT-003", "Sole Whitening Gel", "tube", 14, 12, "55000"),
            ("MAT-004", "Waxed Laces Black", "pairs", 80, 25, "18000"),
            ("MAT-005", "Suede Brush Kit", "set", 6, 8, "95000"),
        ]
        supplies = {}
        for sku, name, unit, quantity, reorder, cost in rows:
            supply, _ = Supply.objects.update_or_create(
                sku=sku,
                defaults={
                    "name": name,
                    "unit": unit,
                    "quantity_on_hand": quantity,
                    "reorder_level": reorder,
                    "cost_price": Decimal(cost),
                    "is_active": True,
                },
            )
            supplies[sku] = supply
        return supplies

    def seed_assets(self, customers, today, now):
        rows = [
            (
                "TK-DEMO-001",
                customers["020 5555 0001"],
                "Nike",
                "Air Jordan 1 Retro High",
                "Chicago",
                "42",
                Asset.Status.IN_SERVICE,
                today + timedelta(days=2),
                now - timedelta(days=2, hours=4),
            ),
            (
                "TK-DEMO-002",
                customers["020 9999 0002"],
                "Adidas",
                "Yeezy Boost 350 V2",
                "Zebra",
                "41",
                Asset.Status.RECEIVED,
                today + timedelta(days=3),
                now - timedelta(days=1, hours=2),
            ),
            (
                "TK-DEMO-003",
                customers["020 7777 0003"],
                "Nike",
                "Dunk Low Panda",
                "Black/White",
                "43",
                Asset.Status.READY,
                today + timedelta(days=1),
                now - timedelta(hours=8),
            ),
            (
                "TK-DEMO-004",
                customers["020 2222 0004"],
                "New Balance",
                "990v5",
                "Grey",
                "40",
                Asset.Status.RECEIVED,
                today + timedelta(days=4),
                now - timedelta(hours=3),
            ),
        ]
        assets = {}
        for ticket, customer, brand, model_name, color, size, status, pickup, created_at in rows:
            asset, _ = Asset.objects.update_or_create(
                ticket_number=ticket,
                defaults={
                    "customer": customer,
                    "brand": brand,
                    "model_name": model_name,
                    "color": color,
                    "size": size,
                    "status": status,
                    "pickup_date": pickup,
                    "condition_note": "Demo intake record with visible wear notes.",
                },
            )
            Asset.objects.filter(pk=asset.pk).update(intake_date=created_at, updated_at=created_at)
            assets[ticket] = Asset.objects.get(pk=asset.pk)
        return assets

    def seed_assessments(self, assets):
        checklist_rows = [
            ("Laces condition", ChecklistItem.Category.LACES, 10, 1),
            ("Upper / body condition", ChecklistItem.Category.UPPER, 10, 2),
            ("Sole condition", ChecklistItem.Category.SOLE, 10, 3),
            ("Insole condition", ChecklistItem.Category.INSOLE, 10, 4),
            ("Color condition", ChecklistItem.Category.OTHER, 10, 5),
        ]
        checklist = []
        for name, category, max_score, order in checklist_rows:
            item, _ = ChecklistItem.objects.update_or_create(
                name=name,
                defaults={
                    "category": category,
                    "max_score": max_score,
                    "display_order": order,
                    "is_active": True,
                },
            )
            checklist.append(item)

        assessment_data = {
            "TK-DEMO-001": (Assessment.Grade.A, Decimal("91.00"), [9, 9, 8, 9, 10]),
            "TK-DEMO-002": (Assessment.Grade.C, Decimal("68.00"), [8, 6, 5, 6, 7]),
            "TK-DEMO-003": (Assessment.Grade.B, Decimal("84.00"), [9, 8, 8, 8, 9]),
        }
        assessments = {}
        for ticket, (grade, total, scores) in assessment_data.items():
            asset = assets[ticket]
            assessment, _ = Assessment.objects.update_or_create(
                asset=asset,
                ai_model="demo-vision-grader",
                defaults={
                    "status": Assessment.Status.DONE,
                    "overall_grade": grade,
                    "total_score": total,
                    "summary": "Demo AI assessment generated from checklist scoring.",
                    "raw_response": {"source": "seed_demo_data"},
                },
            )
            assessment.items.all().delete()
            for checklist_item, score in zip(checklist, scores):
                AssessmentItem.objects.create(
                    assessment=assessment,
                    checklist_item=checklist_item,
                    score=Decimal(score),
                    note="Seeded checklist score.",
                )
            assessments[ticket] = assessment
        return assessments

    def seed_pricing_and_content(self, assets, assessments):
        rows = [
            ("TK-DEMO-001", "5200000", "6500000", "6200000", "High demand Jordan model."),
            ("TK-DEMO-002", "2400000", "3600000", "3100000", "Moderate value; condition affects resale."),
            ("TK-DEMO-003", "1800000", "2600000", "2300000", "Steady demand for Panda colorway."),
        ]
        for ticket, price_min, price_max, suggested, reasoning in rows:
            valuation, _ = PriceValuation.objects.update_or_create(
                asset=assets[ticket],
                ai_model="demo-pricing-engine",
                defaults={
                    "assessment": assessments.get(ticket),
                    "price_min": Decimal(price_min),
                    "price_max": Decimal(price_max),
                    "suggested_price": Decimal(suggested),
                    "currency": "LAK",
                    "reasoning": reasoning,
                    "raw_response": {"source": "seed_demo_data"},
                },
            )
            PromoContent.objects.update_or_create(
                asset=assets[ticket],
                platform=PromoContent.Platform.FACEBOOK,
                defaults={
                    "content": f"{assets[ticket].brand} {assets[ticket].model_name} ພ້ອມລາຍງານ AI Grade ແລະລາຄາແນະນຳ {valuation.suggested_price:,.0f} LAK.",
                    "ai_model": "demo-promo-writer",
                },
            )

    def seed_orders(self, customers, assets, services, today, now):
        rows = [
            (
                "ORD-DEMO-001",
                customers["020 5555 0001"],
                assets["TK-DEMO-001"],
                Order.Status.PAID,
                Decimal("0"),
                now - timedelta(days=2),
                [
                    (services["Deep Clean Service"], "Deep clean for Jordan 1", 1, "150000"),
                    (services["AI Condition Report"], "AI grading report", 1, "45000"),
                ],
            ),
            (
                "ORD-DEMO-002",
                customers["020 9999 0002"],
                assets["TK-DEMO-002"],
                Order.Status.PAID,
                Decimal("20000"),
                now - timedelta(days=1),
                [
                    (services["Sole Restoration"], "Sole restoration", 1, "300000"),
                    (services["Premium Spa + Deodorize"], "Premium spa treatment", 1, "220000"),
                ],
            ),
            (
                "ORD-DEMO-003",
                customers["020 7777 0003"],
                assets["TK-DEMO-003"],
                Order.Status.OPEN,
                Decimal("0"),
                now - timedelta(hours=8),
                [
                    (services["Color Touch-up"], "Color touch-up", 1, "180000"),
                ],
            ),
            (
                "ORD-DEMO-004",
                customers["020 5555 0001"],
                assets["TK-DEMO-001"],
                Order.Status.PAID,
                Decimal("0"),
                now - timedelta(days=8),
                [
                    (services["Premium Spa + Deodorize"], "Premium spa treatment", 1, "220000"),
                ],
            ),
            (
                "ORD-DEMO-005",
                customers["020 5555 0001"],
                assets["TK-DEMO-001"],
                Order.Status.PAID,
                Decimal("0"),
                now - timedelta(days=15),
                [
                    (services["Deep Clean Service"], "Deep clean repeat service", 1, "150000"),
                ],
            ),
        ]
        orders = {}
        for order_number, customer, asset, status, discount, created_at, items in rows:
            order, _ = Order.objects.update_or_create(
                order_number=order_number,
                defaults={
                    "customer": customer,
                    "status": status,
                    "discount": discount,
                    "note": "Demo order generated by seed_demo_data.",
                },
            )
            Order.objects.filter(pk=order.pk).update(created_at=created_at, updated_at=created_at)
            order.items.all().delete()
            for service, description, quantity, unit_price in items:
                OrderItem.objects.create(
                    order=order,
                    service_type=service,
                    asset=asset,
                    description=description,
                    quantity=quantity,
                    unit_price=Decimal(unit_price),
                )
            orders[order_number] = Order.objects.get(pk=order.pk)
        return orders

    def seed_payments_and_expenses(self, orders, today, now):
        for order_number, order in orders.items():
            order.payments.all().delete()
            if order.status == Order.Status.PAID:
                payment = Payment.objects.create(
                    order=order,
                    amount=order.total,
                    currency="LAK",
                    method=Payment.Method.QR,
                    note="Demo BCEL One payment.",
                )
                paid_at = order.created_at + timedelta(minutes=20)
                Payment.objects.filter(pk=payment.pk).update(paid_at=paid_at)

        expense_rows = [
            (today, Expense.Category.SUPPLIES, "Demo: Cleaning chemical restock", "180000"),
            (today - timedelta(days=1), Expense.Category.MARKETING, "Demo: Facebook boost", "90000"),
            (today - timedelta(days=3), Expense.Category.UTILITY, "Demo: Water and power", "120000"),
            (today - timedelta(days=10), Expense.Category.RENT, "Demo: Shop rent", "850000"),
        ]
        for date, category, description, amount in expense_rows:
            Expense.objects.update_or_create(
                date=date,
                description=description,
                defaults={
                    "category": category,
                    "amount": Decimal(amount),
                    "currency": "LAK",
                },
            )

    def seed_points(self, members, orders):
        rows = [
            ("020 5555 0001", 1500, "Demo: Deep clean reward", orders["ORD-DEMO-001"]),
            ("020 5555 0001", 950, "Demo: Premium spa reward", orders["ORD-DEMO-004"]),
            ("020 9999 0002", 1200, "Demo: Restoration reward", orders["ORD-DEMO-002"]),
            ("020 7777 0003", 450, "Demo: Color touch-up pending reward", orders["ORD-DEMO-003"]),
        ]
        for phone, points, reason, order in rows:
            transaction = PointTransaction.objects.filter(
                card=members[phone], reason=reason, order=order
            ).first()
            if not transaction:
                PointTransaction.objects.create(
                    card=members[phone],
                    points=points,
                    reason=reason,
                    order=order,
                )

        final_balances = {
            "020 5555 0001": 2450,
            "020 9999 0002": 1200,
            "020 7777 0003": 450,
        }
        for phone, balance in final_balances.items():
            MemberCard.objects.filter(pk=members[phone].pk).update(points_balance=balance)

    def seed_stock_movements(self, supplies, orders):
        rows = [
            (supplies["MAT-001"], StockMovement.MovementType.OUT, 4, "Demo: used for ORD-DEMO-001", orders["ORD-DEMO-001"]),
            (supplies["MAT-003"], StockMovement.MovementType.OUT, 3, "Demo: used for ORD-DEMO-002", orders["ORD-DEMO-002"]),
            (supplies["MAT-002"], StockMovement.MovementType.IN, 60, "Demo: supplier restock", None),
            (supplies["MAT-005"], StockMovement.MovementType.OUT, 2, "Demo: used for suede care", orders["ORD-DEMO-002"]),
        ]
        for supply, movement_type, quantity, note, order in rows:
            if not StockMovement.objects.filter(supply=supply, note=note).exists():
                StockMovement.objects.create(
                    supply=supply,
                    movement_type=movement_type,
                    quantity=quantity,
                    note=note,
                    order=order,
                )

        final_quantities = {
            "MAT-001": 8,
            "MAT-002": 120,
            "MAT-003": 14,
            "MAT-004": 80,
            "MAT-005": 6,
        }
        for sku, quantity in final_quantities.items():
            Supply.objects.filter(pk=supplies[sku].pk).update(quantity_on_hand=quantity)
