import base64
import os
from io import BytesIO

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from PIL import Image, ImageOps, UnidentifiedImageError

from asset_intake.models import Asset
from media_backup.models import MediaFile

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
BUYBACK_IMAGE_LIMIT = 8
BUYBACK_IMAGE_MAX_SIZE = (768, 768)
BUYBACK_REQUIRED_ANGLES = (
    MediaFile.CaptureAngle.FRONT,
    MediaFile.CaptureAngle.HEEL,
    MediaFile.CaptureAngle.SIDE,
    MediaFile.CaptureAngle.OUTSOLE,
    MediaFile.CaptureAngle.SIZE_LABEL,
)
BUYBACK_OPTIONAL_ANGLES = (
    MediaFile.CaptureAngle.INNER,
    MediaFile.CaptureAngle.BOX_ACCESSORIES,
    MediaFile.CaptureAngle.DEFECT,
)
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


def _encode_images(
    media_qs,
    limit=AI_IMAGE_LIMIT,
    max_size=AI_IMAGE_MAX_SIZE,
):
    """Resize intake photos before sending them to the vision model.

    Three 1024px photos are enough for the main shoe angles and keep the
    OpenRouter prompt comfortably below a typical key token limit.
    """
    content = []
    for media in list(media_qs)[:limit]:
        if media.media_type != "image":
            continue
        try:
            with media.file.open("rb") as fh:
                with Image.open(fh) as source:
                    image = ImageOps.exif_transpose(source)
                    image.thumbnail(max_size, Image.Resampling.LANCZOS)
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

    before_images = list(
        asset.media_files.filter(
            stage=MediaFile.Stage.BEFORE,
            media_type=MediaFile.MediaType.IMAGE,
        )
    )
    has_buyback_service = asset.order_items.filter(
        service_type__category="buyback"
    ).exists()
    photo_order_text = ""
    if has_buyback_service:
        captured_angles = {
            media.capture_angle for media in before_images if media.capture_angle
        }
        missing_angles = [
            angle for angle in BUYBACK_REQUIRED_ANGLES
            if angle not in captured_angles
        ]
        if missing_angles:
            missing_labels = ", ".join(
                str(MediaFile.CaptureAngle(angle).label)
                for angle in missing_angles
            )
            messages.error(
                request,
                "ກະລຸນາອັບໂຫຼດຮູບ Buy-back ໃຫ້ຄົບກ່ອນ: "
                f"{missing_labels}",
            )
            detail_url = reverse("asset_intake:detail", args=[asset.pk])
            return redirect(f"{detail_url}?ai=1#ai-photo-upload")

        media_by_angle = {}
        for media in before_images:
            if media.capture_angle:
                media_by_angle.setdefault(media.capture_angle, media)
        ordered_angles = (*BUYBACK_REQUIRED_ANGLES, *BUYBACK_OPTIONAL_ANGLES)
        ordered_media = [
            media_by_angle[angle]
            for angle in ordered_angles
            if angle in media_by_angle
        ]
        ordered_media.extend(
            media for media in before_images
            if not media.capture_angle and media not in ordered_media
        )
        images = _encode_images(
            ordered_media,
            limit=BUYBACK_IMAGE_LIMIT,
            max_size=BUYBACK_IMAGE_MAX_SIZE,
        )
        photo_order_text = (
            "\nລຳດັບຮູບ: ດ້ານໜ້າ, ດ້ານຫຼັງ, ດ້ານຂ້າງ, "
            "ພື້ນເກີບ, ປ້າຍ Size/SKU, ແລະຮູບເສີມທີ່ມີ."
        )
    else:
        images = _encode_images(before_images)
    checklist_text = "\n".join(
        f"- id={c.id}: {c.name} (ຄະແນນເຕັມ {c.max_score})" for c in checklist_items
    )
    user_text = (
        f"ເກີບ: {asset.brand} {asset.model_name}, ສີ {asset.color}, ເບີ {asset.size}\n"
        f"ໝາຍເຫດຕອນຮັບເຂົ້າ: {asset.condition_note}\n\n"
        f"Checklist ທີ່ຕ້ອງໃຫ້ຄະແນນ:\n{checklist_text}"
        f"{photo_order_text}"
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
