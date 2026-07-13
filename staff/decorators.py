"""ຈຳກັດສິດທິການເຂົ້າ view ຕາມໜ້າທີ່ຂອງພະນັກງານ"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .models import get_role


def role_required(*roles):
    """ອະນຸຍາດສະເພາະ user ທີ່ມີໜ້າທີ່ຕາມກຳນົດ (superuser ຜ່ານໄດ້ສະເໝີ)"""

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            if get_role(request.user) in roles:
                return view_func(request, *args, **kwargs)
            raise PermissionDenied("ບໍ່ມີສິດທິເຂົ້າເຖິງໜ້ານີ້")

        return wrapper

    return decorator
