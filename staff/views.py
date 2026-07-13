"""ໜ້າລາຍງານພະນັກງານ ແລະ ຄອມມິດຊັນ (ຜູ້ຈັດການເທົ່ານັ້ນ)"""

from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext as _
from django.contrib.auth.models import User
from django.views.decorators.http import require_POST
from django.contrib import messages

from asset_intake.models import Asset

from .decorators import role_required
from .models import StaffProfile


def _role_label(role):
    return {
        StaffProfile.Role.MANAGER: _("Manager"),
        StaffProfile.Role.FRONT_DESK: _("Front desk"),
        StaffProfile.Role.TECHNICIAN: _("Technician"),
    }.get(role, role)


def _parse_month(request):
    """ອ່ານ ?month=YYYY-MM — ຄ່າຜິດຮູບແບບໃຫ້ໃຊ້ເດືອນປັດຈຸບັນ"""
    today = timezone.localdate()
    month_str = request.GET.get("month", "")
    try:
        year, month = map(int, month_str.split("-"))
        if not 1 <= month <= 12:
            raise ValueError
        return year, month
    except (ValueError, AttributeError):
        return today.year, today.month


@role_required(StaffProfile.Role.MANAGER)
def commission_report(request):
    year, month = _parse_month(request)

    # ວຽກທີ່ສົ່ງມອບແລ້ວໃນເດືອນນີ້ ແລະ ມີຊ່າງຮັບຜິດຊອບ
    assets = (
        Asset.objects.filter(
            status=Asset.Status.RETURNED,
            completed_at__year=year,
            completed_at__month=month,
            assigned_to__isnull=False,
        )
        .select_related("assigned_to", "customer")
        .prefetch_related("order_items")
    )

    by_tech = {}
    for asset in assets:
        job_value = sum(
            (item.subtotal for item in asset.order_items.all()), start=Decimal("0")
        )
        row = by_tech.setdefault(
            asset.assigned_to_id,
            {"user": asset.assigned_to, "jobs": [], "base_total": Decimal("0")},
        )
        row["jobs"].append({"asset": asset, "value": job_value})
        row["base_total"] += job_value

    profiles = {
        p.user_id: p for p in StaffProfile.objects.filter(user_id__in=by_tech.keys())
    }
    rows = []
    grand_commission = Decimal("0")
    for user_id, row in by_tech.items():
        profile = profiles.get(user_id)
        rate = profile.commission_rate if profile else Decimal("0")
        commission = (row["base_total"] * rate / 100).quantize(Decimal("0.01"))
        grand_commission += commission
        rows.append(
            {
                "user": row["user"],
                "profile": profile,
                "role_label": _role_label(profile.role) if profile else "",
                "job_count": len(row["jobs"]),
                "jobs": row["jobs"],
                "base_total": row["base_total"],
                "rate": rate,
                "commission": commission,
            }
        )
    rows.sort(key=lambda r: r["commission"], reverse=True)

    staff_members = list(StaffProfile.objects.select_related("user"))
    for profile in staff_members:
        profile.localized_role = _role_label(profile.role)

    context = {
        "active_nav": "staff",
        "rows": rows,
        "grand_commission": grand_commission,
        "month_value": f"{year:04d}-{month:02d}",
        "staff_members": staff_members,
    }
    return render(request, "staff/commission_report.html", context)


@role_required(StaffProfile.Role.MANAGER)
@require_POST
def add_staff(request):
    first_name = request.POST.get("first_name", "").strip()
    last_name = request.POST.get("last_name", "").strip()
    username = request.POST.get("username", "").strip()
    password = request.POST.get("password", "")
    role = request.POST.get("role", StaffProfile.Role.TECHNICIAN)
    phone = request.POST.get("phone", "").strip()
    commission_rate = request.POST.get("commission_rate", "0")
    is_active = request.POST.get("is_active") == "on"

    if not username or not password:
        messages.error(request, "ກະລຸນາກອກຊື່ຜູ້ໃຊ້ ແລະ ລະຫັດຜ່ານ")
        return redirect("staff:commissions")

    if User.objects.filter(username=username).exists():
        messages.error(request, "ຊື່ຜູ້ໃຊ້ນີ້ມີຢູ່ໃນລະບົບແລ້ວ")
        return redirect("staff:commissions")

    try:
        user = User.objects.create_user(
            username=username,
            password=password,
            first_name=first_name,
            last_name=last_name
        )
        StaffProfile.objects.create(
            user=user,
            role=role,
            phone=phone,
            commission_rate=Decimal(commission_rate) if commission_rate else Decimal("0"),
            is_active=is_active
        )
        messages.success(request, "ເພີ່ມພະນັກງານສຳເລັດແລ້ວ")
    except Exception as e:
        messages.error(request, f"ເກີດຂໍ້ຜິດພາດ: {str(e)}")

    return redirect("staff:commissions")


@role_required(StaffProfile.Role.MANAGER)
@require_POST
def edit_staff(request, pk):
    profile = get_object_or_404(StaffProfile, pk=pk)
    user = profile.user

    first_name = request.POST.get("first_name", "").strip()
    last_name = request.POST.get("last_name", "").strip()
    role = request.POST.get("role", StaffProfile.Role.TECHNICIAN)
    phone = request.POST.get("phone", "").strip()
    commission_rate = request.POST.get("commission_rate", "0")
    is_active = request.POST.get("is_active") == "on"
    password = request.POST.get("password", "")

    try:
        user.first_name = first_name
        user.last_name = last_name
        if password:
            user.set_password(password)
        user.save()

        profile.role = role
        profile.phone = phone
        profile.commission_rate = Decimal(commission_rate) if commission_rate else Decimal("0")
        profile.is_active = is_active
        profile.save()
        
        messages.success(request, "ແກ້ໄຂຂໍ້ມູນພະນັກງານສຳເລັດແລ້ວ")
    except Exception as e:
        messages.error(request, f"ເກີດຂໍ້ຜິດພາດ: {str(e)}")

    return redirect("staff:commissions")


@role_required(StaffProfile.Role.MANAGER)
@require_POST
def delete_staff(request, pk):
    profile = get_object_or_404(StaffProfile, pk=pk)
    user = profile.user
    try:
        user.delete() # Cascade delete will automatically delete StaffProfile
        messages.success(request, "ລົບພະນັກງານສຳເລັດແລ້ວ")
    except Exception as e:
        messages.error(request, f"ເກີດຂໍ້ຜິດພາດ: {str(e)}")
        
    return redirect("staff:commissions")
