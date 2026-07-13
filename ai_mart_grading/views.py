import base64

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect

from asset_intake.models import Asset

from .models import Assessment, AssessmentItem, ChecklistItem
from .services import OpenRouterError, chat_json

SYSTEM_PROMPT = (
    "ເຈົ້າແມ່ນຜູ້ຊ່ຽວຊານກວດສະພາບເກີບມືສອງ (sneaker condition grading expert). "
    "ໃຫ້ກວດຮູບພາບ ແລະ ໃຫ້ຄະແນນແຕ່ລະຫົວຂໍ້ຕາມ checklist, ຄະແນນເປັນ 0 ຫາ max_score ຂອງແຕ່ລະຫົວຂໍ້. "
    "ຕອບເປັນ JSON ເທົ່ານັ້ນ ຕາມຮູບແບບ: "
    '{"items": [{"checklist_item_id": <int>, "score": <number>, "note": "<ໝາຍເຫດພາສາລາວ>"}], '
    '"overall_grade": "A|B|C|D|F", "total_score": <number>, "summary": "<ສະຫຼູບພາສາລາວ 2-3 ປະໂຫຍກ>", '
    '"confidence_score": <number>}'
)


def _encode_images(media_qs, limit=6):
    """ອ່ານໄຟລ໌ຮູບຈາກ MEDIA_ROOT ແລ້ວແປງເປັນ base64 data URL ສົ່ງໃຫ້ OpenRouter (ຕ້ອງໃຊ້ model ທີ່ຮອງຮັບ vision)"""
    content = []
    for media in media_qs[:limit]:
        if media.media_type != "image":
            continue
        try:
            with media.file.open("rb") as fh:
                b64 = base64.b64encode(fh.read()).decode("ascii")
        except (FileNotFoundError, ValueError):
            continue
        content.append(
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
        )
    return content


@login_required
def run_assessment(request, pk):
    asset = get_object_or_404(Asset, pk=pk)
    if request.method != "POST":
        return redirect("asset_intake:detail", pk=asset.pk)

    checklist_items = list(ChecklistItem.objects.filter(is_active=True))
    if not checklist_items:
        messages.error(request, "ຍັງບໍ່ມີຫົວຂໍ້ Checklist — ກະລຸນາເພີ່ມກ່ອນໃນໜ້າ Admin")
        return redirect("asset_intake:detail", pk=asset.pk)

    images = _encode_images(asset.media_files.filter(stage="before"))
    checklist_text = "\n".join(
        f"- id={c.id}: {c.name} (ຄະແນນເຕັມ {c.max_score})" for c in checklist_items
    )
    user_text = (
        f"ເກີບ: {asset.brand} {asset.model_name}, ສີ {asset.color}, ເບີ {asset.size}\n"
        f"ໝາຍເຫດຕອນຮັບເຂົ້າ: {asset.condition_note}\n\n"
        f"Checklist ທີ່ຕ້ອງໃຫ້ຄະແນນ:\n{checklist_text}"
    )

    assessment = Assessment.objects.create(asset=asset, status=Assessment.Status.PENDING)
    try:
        result, raw = chat_json(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [{"type": "text", "text": user_text}, *images],
                },
            ]
        )
        item_map = {c.id: c for c in checklist_items}
        for entry in result.get("items", []):
            checklist_item = item_map.get(entry.get("checklist_item_id"))
            if checklist_item is None:
                continue
            AssessmentItem.objects.create(
                assessment=assessment,
                checklist_item=checklist_item,
                score=entry.get("score", 0),
                note=entry.get("note", ""),
            )
        assessment.overall_grade = result.get("overall_grade", "")
        assessment.total_score = result.get("total_score")
        assessment.summary = result.get("summary", "")
        assessment.ai_model = raw.get("model", "")
        assessment.raw_response = {**raw, **result}
        assessment.status = Assessment.Status.DONE
        assessment.save()
        messages.success(request, "ປະເມີນສະພາບດ້ວຍ AI ສຳເລັດ")
    except OpenRouterError as exc:
        assessment.status = Assessment.Status.FAILED
        assessment.summary = str(exc)
        assessment.save(update_fields=["status", "summary"])
        messages.error(request, f"AI ປະເມີນບໍ່ສຳເລັດ: {exc}")

    return redirect("asset_intake:detail", pk=asset.pk)
