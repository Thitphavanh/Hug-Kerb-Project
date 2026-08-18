import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect

from ai_mart_grading.models import Assessment
from ai_mart_grading.services import OpenRouterError, chat, chat_json, to_decimal
from asset_intake.models import Asset
from media_backup.models import MediaFile

from .models import PriceValuation, PromoContent

VALUATION_SYSTEM_PROMPT = (
    "ເຈົ້າແມ່ນຜູ້ຊ່ຽວຊານປະເມີນລາຄາຂາຍຕໍ່ ແລະລາຄາຮັບຊື້ເກີບມືສອງ "
    "ສຳລັບຮ້ານໃນລາວ (ສະກຸນເງິນ LAK). "
    "recommended_buy_price ຕ້ອງຕ່ຳກວ່າ suggested_price ໂດຍຫັກຄ່າຟື້ນຟູ, "
    "ຄວາມສ່ຽງ ແລະກຳໄລເປົ້າໝາຍຂອງຮ້ານ. "
    "ຕອບເປັນ JSON ເທົ່ານັ້ນ ຕາມຮູບແບບ: "
    '{"price_min": <number>, "price_max": <number>, "suggested_price": <number>, '
    '"base_price": <number>, "condition_adjustment": <number>, "rarity_premium": <number>, '
    '"refurbishment_cost": <number>, "risk_reserve": <number>, '
    '"target_margin_percent": <number>, "recommended_buy_price": <number>, '
    '"demand_level": "<High Demand|Normal Demand|Low Demand>", "confidence_score": <number>, '
    '"reasoning": "<ເຫດຜົນສັ້ນໆເປັນພາສາລາວ>"}'
)

PRICING_MODEL = "google/gemini-2.5-flash-lite"
REQUIRED_BUYBACK_ANGLES = {
    MediaFile.CaptureAngle.FRONT,
    MediaFile.CaptureAngle.HEEL,
    MediaFile.CaptureAngle.SIDE,
    MediaFile.CaptureAngle.OUTSOLE,
    MediaFile.CaptureAngle.SIZE_LABEL,
}

PROMO_SYSTEM_PROMPT = (
    "ເຈົ້າແມ່ນນັກການຕະຫຼາດຮ້ານຂາຍເກີບມືສອງ. ຂຽນຄຳໂປຣໂມດຂາຍເກີບເປັນພາສາລາວ ສັ້ນ ດຶງດູດ "
    "ເໝາະສົມກັບແພລດຟອມທີ່ລະບຸ, ຕອບເປັນຂໍ້ຄວາມທຳມະດາ (ບໍ່ໃຊ້ JSON), ໃສ່ hashtag ທ້າຍຂໍ້ຄວາມ."
)


@login_required
def run_valuation(request, pk):
    asset = get_object_or_404(Asset, pk=pk)
    if request.method != "POST":
        return redirect("asset_intake:detail", pk=asset.pk)

    latest_assessment = asset.assessments.filter(status=Assessment.Status.DONE).first()
    if latest_assessment is None:
        messages.error(
            request,
            "ກະລຸນາປະເມີນສະພາບດ້ວຍ AI ໃຫ້ສຳເລັດກ່ອນປະເມີນລາຄາ",
        )
        return redirect("asset_intake:detail", pk=asset.pk)

    has_buyback_service = asset.order_items.filter(
        service_type__category="buyback"
    ).exists()
    if has_buyback_service:
        captured_angles = set(
            asset.media_files.filter(
                stage=MediaFile.Stage.BEFORE,
                media_type=MediaFile.MediaType.IMAGE,
            )
            .exclude(capture_angle="")
            .values_list("capture_angle", flat=True)
        )
        if not REQUIRED_BUYBACK_ANGLES.issubset(captured_angles):
            messages.error(
                request,
                "ກະລຸນາອັບໂຫຼດຮູບ Buy-back ບັງຄັບໃຫ້ຄົບກ່ອນປະເມີນລາຄາ",
            )
            return redirect("asset_intake:detail", pk=asset.pk)

    user_text = (
        f"ເກີບ: {asset.brand} {asset.model_name}, ສີ {asset.color}, ເບີ {asset.size}\n"
        f"ສະພາບ: "
        f"{latest_assessment.overall_grade} ({latest_assessment.summary})\n"
        "ໝາຍເຫດ: ນີ້ເປັນລາຄາໂດຍປະມານ; ພະນັກງານຈະຢືນຢັນລາຄາສຸດທ້າຍ."
    )
    try:
        result, raw = chat_json(
            [
                {"role": "system", "content": VALUATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            model=os.environ.get("OPENROUTER_PRICING_MODEL", PRICING_MODEL),
            max_tokens=1200,
        )
        suggested_price = to_decimal(result.get("suggested_price"), 0)
        demand_level = str(result.get("demand_level", "")).strip()
        PriceValuation.objects.create(
            asset=asset,
            assessment=latest_assessment,
            price_min=to_decimal(result.get("price_min"), 0),
            price_max=to_decimal(result.get("price_max"), 0),
            suggested_price=suggested_price,
            currency="LAK",
            base_price=to_decimal(result.get("base_price")),
            condition_adjustment=to_decimal(result.get("condition_adjustment")),
            rarity_premium=to_decimal(result.get("rarity_premium")),
            refurbishment_cost=to_decimal(result.get("refurbishment_cost")),
            risk_reserve=to_decimal(result.get("risk_reserve")),
            target_margin_percent=to_decimal(result.get("target_margin_percent")),
            # ຖ້າ AI ບໍ່ຕອບລາຄາຮັບຊື້ ໃຫ້ວ່າງໄວ້ — ຢ່າຕົກລົງມາໃຊ້ລາຄາຂາຍຕໍ່
            # ເພາະນັ້ນຈະສະແດງລາຄາຮັບຊື້ສູງເທົ່າລາຄາຂາຍ ແລ້ວຮ້ານຊື້ແພງເກີນ
            recommended_buy_price=to_decimal(result.get("recommended_buy_price")),
            demand_level=(
                demand_level
                if demand_level in PriceValuation.DemandLevel.values
                else ""
            ),
            confidence_score=to_decimal(result.get("confidence_score")),
            reasoning=result.get("reasoning", ""),
            ai_model=raw.get("model", ""),
            raw_response={**raw, **result},
        )
        messages.success(request, "ປະເມີນລາຄາຂາຍຕໍ່ສຳເລັດ")
    except OpenRouterError as exc:
        messages.error(request, f"AI ປະເມີນລາຄາບໍ່ສຳເລັດ: {exc}")

    return redirect("asset_intake:detail", pk=asset.pk)


@login_required
def run_promo(request, pk):
    asset = get_object_or_404(Asset, pk=pk)
    if request.method != "POST":
        return redirect("asset_intake:detail", pk=asset.pk)

    platform = request.POST.get("platform", PromoContent.Platform.FACEBOOK)
    latest_valuation = asset.valuations.first()
    user_text = (
        f"ແພລດຟອມ: {platform}\n"
        f"ເກີບ: {asset.brand} {asset.model_name}, ສີ {asset.color}, ເບີ {asset.size}\n"
        f"ລາຄາຂາຍ: "
        f"{latest_valuation.suggested_price if latest_valuation else 'ຍັງບໍ່ໄດ້ປະເມີນ'} "
        f"{latest_valuation.currency if latest_valuation else ''}"
    )
    try:
        content, raw = chat(
            [
                {"role": "system", "content": PROMO_SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            max_tokens=800,
        )
        PromoContent.objects.create(
            asset=asset,
            platform=platform,
            content=content.strip(),
            ai_model=raw.get("model", ""),
        )
        messages.success(request, "ສ້າງເນື້ອຫາໂປຣໂມດສຳເລັດ")
    except OpenRouterError as exc:
        messages.error(request, f"AI ສ້າງເນື້ອຫາບໍ່ສຳເລັດ: {exc}")

    return redirect("asset_intake:detail", pk=asset.pk)
