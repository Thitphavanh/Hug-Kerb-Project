from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Max, Prefetch
from django.shortcuts import render, get_object_or_404, redirect
from django.utils.translation import gettext as _

from asset_intake.models import Asset
from ai_mart_grading.models import Assessment
from digital_member.models import MemberCard, PointTransaction

from .models import Customer


@login_required
def index(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        phone = request.POST.get("phone", "").strip()
        email = request.POST.get("email", "").strip()
        tier_val = request.POST.get("tier", "basic").strip()

        if name and phone:
            if Customer.objects.filter(phone=phone).exists():
                messages.error(
                    request,
                    _("This phone number is already used by another customer."),
                )
                return redirect("crm:index")

            customer = Customer.objects.create(name=name, phone=phone, email=email)
            import random
            card_number = f"KV-{random.randint(1000, 9999)}-{random.randint(100, 999)}"
            MemberCard.objects.create(
                customer=customer,
                card_number=card_number,
                tier=tier_val,
                points_balance=0,
                is_active=True
            )
            return redirect(f"/crm/?customer={customer.pk}")

    search = request.GET.get("q", "").strip()
    tier = request.GET.get("tier", "").strip()
    
    customers_qs = Customer.objects.select_related("member_card").annotate(
        last_service_date=Max("assets__intake_date")
    ).order_by("-created_at")
    
    if search:
        customers_qs = customers_qs.filter(
            Q(name__icontains=search)
            | Q(phone__icontains=search)
            | Q(email__icontains=search)
            | Q(member_card__card_number__icontains=search)
        )
    if tier:
        customers_qs = customers_qs.filter(member_card__tier=tier)

    customers = list(customers_qs[:25])
    
    selected_customer_id = request.GET.get("customer")
    selected_customer = None
    if selected_customer_id:
        try:
            selected_customer = Customer.objects.select_related("member_card").get(pk=selected_customer_id)
        except Customer.DoesNotExist:
            pass
            
    if not selected_customer and customers:
        selected_customer = customers[0]

    selected_member = (
        getattr(selected_customer, "member_card", None) if selected_customer else None
    )
    
    selected_history = (
        Asset.objects.select_related("customer")
        .prefetch_related(
            Prefetch(
                "assessments",
                queryset=Assessment.objects.filter(status=Assessment.Status.DONE),
                to_attr="completed_assessments"
            )
        )
        .filter(customer=selected_customer)[:6]
        if selected_customer
        else Asset.objects.none()
    )
    
    point_transactions = (
        PointTransaction.objects.select_related("order", "card").filter(card=selected_member)[:6]
        if selected_member
        else PointTransaction.objects.none()
    )

    context = {
        "active_nav": "crm",
        "customers": customers,
        "selected_customer": selected_customer,
        "selected_member": selected_member,
        "selected_history": selected_history,
        "point_transactions": point_transactions,
        "customer_count": Customer.objects.count(),
        "member_count": MemberCard.objects.filter(is_active=True).count(),
        "recent_assets": Asset.objects.select_related("customer")[:6],
        "tier_choices": MemberCard.Tier.choices,
        "search_query": search,
        "selected_tier": tier,
    }
    return render(request, "crm/index.html", context)


@login_required
def edit_customer(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    if request.method == "POST":
        phone = request.POST.get("phone", "").strip()
        if Customer.objects.exclude(pk=customer.pk).filter(phone=phone).exists():
            messages.error(
                request,
                _("This phone number is already used by another customer."),
            )
            return redirect(f"/crm/?customer={customer.pk}")

        customer.name = request.POST.get("name", "").strip()
        customer.phone = phone
        customer.email = request.POST.get("email", "").strip()
        customer.save()

        tier_val = request.POST.get("tier", "").strip()
        if tier_val:
            member_card, _card_created = MemberCard.objects.get_or_create(customer=customer)
            member_card.tier = tier_val
            member_card.save()

        return redirect(f"/crm/?customer={customer.pk}")
    return redirect("crm:index")


@login_required
def delete_customer(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    if request.method == "POST":
        customer.delete()
    return redirect("crm:index")
