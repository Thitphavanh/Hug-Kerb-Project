import base64
import os
from io import BytesIO

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from PIL import Image, ImageOps, UnidentifiedImageError

from asset_intake.models import Asset

from .models import Assessment, AssessmentItem, ChecklistItem
from .services import OpenRouterError, chat_json

SYSTEM_PROMPT = (
    "ເຈົ້າແມ່ນຜູ້ຊ່ຽວຊານກວດສະພາບເກີບມືສອງ (sneaker condition grading expert). "
    "ໃຫ້ກວດຮູບພາບ ແລະ ໃຫ້ຄະແນນແຕ່ລະຫົວຂໍ້ຕາມ checklist, ຄະແນນເປັນ 0 ຫາ max_score ຂອງແຕ່ລະຫົວຂໍ້. "
    "ຕອບໃຫ້ຄົບທຸກ checklist ແລະເປັນ JSON ເທົ່ານັ້ນ. "
    "ໃຊ້ compact array [checklist_item_id, score, note]. "
    "note ແຕ່ລະຂໍ້ເປັນພາສາລາວສັ້ນບໍ່ເກີນ 30 ຕົວອັກສອນ; summary ໜຶ່ງປະໂຫຍກບໍ່ເກີນ 100 ຕົວອັກສອນ. "
    "ຮູບແບບ: "
    '{"items":[[<id>,<score>,"<note>"],...],"overall_grade":"A|B|C|D|F",'
    '"total_score":<number>,"summary":"<summary>","confidence_score":<number>}'
)


AI_IMAGE_LIMIT = 3
AI_IMAGE_MAX_SIZE = (1024, 1024)
DEFAULT_VISION_MODEL = "google/gemini-2.5-flash-lite"


def _assessment_entry_values(entry):
    """Accept the compact AI schema and legacy object-shaped entries."""
    if isinstance(entry, (list, tuple)) and len(entry) >= 2:
        return entry[0], entry[1], entry[2] if len(entry) >= 3 else ""
    if isinstance(entry, dict):
        return (
            entry.get("checklist_item_id"),
            entry.get("score", 0),
            entry.get("note", ""),
        )
    return None, 0, ""


def _encode_images(media_qs, limit=AI_IMAGE_LIMIT):
    """Resize intake photos before sending them to the vision model.

    Three 1024px photos are enough for the main shoe angles and keep the
    OpenRouter prompt comfortably below a typical key token limit.
    """
    content = []
    for media in media_qs[:limit]:
        if media.media_type != "image":
            continue
        try:
            with media.file.open("rb") as fh:
                with Image.open(fh) as source:
                    image = ImageOps.exif_transpose(source)
                    image.thumbnail(AI_IMAGE_MAX_SIZE, Image.Resampling.LANCZOS)
                    if image.mode != "RGB":
                        image = image.convert("RGB")
                    optimized = BytesIO()
                    image.save(optimized, format="JPEG", quality=80, optimize=True)
                    b64 = base64.b64encode(optimized.getvalue()).decode("ascii")
        except (FileNotFoundError, OSError, UnidentifiedImageError, ValueError):
            continue
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            }
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
            ],
            # Compact arrays and short notes keep all checklist results inside
            # the credit-constrained output budget.
            model=os.environ.get(
                "OPENROUTER_VISION_MODEL", DEFAULT_VISION_MODEL
            ).strip() or DEFAULT_VISION_MODEL,
            max_tokens=1800,
        )
        item_map = {c.id: c for c in checklist_items}
        for entry in result.get("items", []):
            item_id, score, note = _assessment_entry_values(entry)
            checklist_item = item_map.get(item_id)
            if checklist_item is None:
                continue
            AssessmentItem.objects.create(
                assessment=assessment,
                checklist_item=checklist_item,
                score=score,
                note=str(note)[:200],
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
