from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect

from ai_mart_grading.models import Assessment
from ai_mart_grading.services import OpenRouterError, chat, chat_json
from asset_intake.models import Asset

from .models import PriceValuation, PromoContent

VALUATION_SYSTEM_PROMPT = (
    "ເຈົ້າແມ່ນຜູ້ຊ່ຽວຊານປະເມີນລາຄາຂາຍຕໍ່ເກີບມືສອງໃນຕະຫຼາດ (ສະກຸນເງິນ THB). "
    "ຕອບເປັນ JSON ເທົ່ານັ້ນ ຕາມຮູບແບບ: "
    '{"price_min": <number>, "price_max": <number>, "suggested_price": <number>, '
    '"base_price": <number>, "condition_adjustment": <number>, "rarity_premium": <number>, '
    '"demand_level": "<High Demand|Normal Demand|Low Demand>", "confidence_score": <number>, '
    '"reasoning": "<ເຫດຜົນສັ້ນໆເປັນພາສາລາວ>"}'
)

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
    user_text = (
        f"ເກີບ: {asset.brand} {asset.model_name}, ສີ {asset.color}, ເບີ {asset.size}\n"
        f"ສະພາບ: "
        f"{latest_assessment.overall_grade if latest_assessment else 'ຍັງບໍ່ໄດ້ປະເມີນ'} "
        f"({latest_assessment.summary if latest_assessment else asset.condition_note})"
    )
    try:
        result, raw = chat_json(
            [
                {"role": "system", "content": VALUATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ]
        )
        PriceValuation.objects.create(
            asset=asset,
            assessment=latest_assessment,
            price_min=result.get("price_min", 0),
            price_max=result.get("price_max", 0),
            suggested_price=result.get("suggested_price", 0),
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
            ]
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
