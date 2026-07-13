from .models import StaffProfile, get_role


def staff_role(request):
    """ສົ່ງໜ້າທີ່ຂອງ user ໃຫ້ທຸກ template — ໃຊ້ເຊື່ອງ/ສະແດງເມນູຕາມສິດທິ"""
    role = get_role(request.user) if hasattr(request, "user") else None
    return {
        "staff_role": role,
        "is_manager": role == StaffProfile.Role.MANAGER,
        "is_technician": role == StaffProfile.Role.TECHNICIAN,
    }
