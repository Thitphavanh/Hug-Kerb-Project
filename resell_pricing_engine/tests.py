from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from ai_mart_grading.models import Assessment
from asset_intake.models import Asset
from crm.models import Customer
from media_backup.models import MediaFile
from pos.models import Order, OrderItem, ServiceType

from .models import PriceValuation


class BuybackValuationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("pricing-staff")
        self.client.force_login(self.user)
        self.customer = Customer.objects.create(
            name="Buy-back customer",
            phone="02055550000",
        )
        self.asset = Asset.objects.create(
            customer=self.customer,
            brand="Jordan",
            model_name="1 Low Fragment x Travis Scott",
            size="US 8.5",
        )
        service = ServiceType.objects.create(
            name="Buy-back Evaluation",
            category=ServiceType.Category.BUYBACK,
            price=0,
        )
        order = Order.objects.create(customer=self.customer, created_by=self.user)
        OrderItem.objects.create(
            order=order,
            service_type=service,
            asset=self.asset,
            description="Buy-back evaluation",
            unit_price=0,
        )
        self.url = reverse(
            "resell_pricing_engine:run_valuation",
            args=[self.asset.pk],
        )

    def _add_required_photos(self):
        for angle in (
            MediaFile.CaptureAngle.FRONT,
            MediaFile.CaptureAngle.HEEL,
            MediaFile.CaptureAngle.SIDE,
            MediaFile.CaptureAngle.OUTSOLE,
            MediaFile.CaptureAngle.SIZE_LABEL,
        ):
            MediaFile.objects.create(
                asset=self.asset,
                stage=MediaFile.Stage.BEFORE,
                media_type=MediaFile.MediaType.IMAGE,
                capture_angle=angle,
                file=f"assets/test-{angle}.jpg",
            )

    @patch("resell_pricing_engine.views.chat_json")
    def test_valuation_is_blocked_until_ai_assessment_is_done(self, mock_chat):
        self._add_required_photos()

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertFalse(PriceValuation.objects.exists())
        mock_chat.assert_not_called()

    @patch("resell_pricing_engine.views.chat_json")
    def test_completed_buyback_creates_lak_market_and_offer_estimate(self, mock_chat):
        self._add_required_photos()
        assessment = Assessment.objects.create(
            asset=self.asset,
            status=Assessment.Status.DONE,
            overall_grade="B",
            summary="ສະພາບດີ",
        )
        result = {
            "price_min": 20_000_000,
            "price_max": 24_000_000,
            "suggested_price": 22_000_000,
            "base_price": 22_000_000,
            "condition_adjustment": -1_000_000,
            "rarity_premium": 2_000_000,
            "refurbishment_cost": 500_000,
            "risk_reserve": 1_000_000,
            "target_margin_percent": 25,
            "recommended_buy_price": 15_000_000,
            "demand_level": "High Demand",
            "confidence_score": 85,
            "reasoning": "ອີງຕາມສະພາບ ແລະຄວາມຕ້ອງການ",
        }
        mock_chat.return_value = (result, {"model": "test-vision-model"})

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 302)
        valuation = PriceValuation.objects.get()
        self.assertEqual(valuation.assessment, assessment)
        self.assertEqual(valuation.currency, "LAK")
        self.assertEqual(
            valuation.raw_response["recommended_buy_price"],
            15_000_000,
        )
        self.assertEqual(
            mock_chat.call_args.kwargs["model"],
            "google/gemini-2.5-flash-lite",
        )
