from decimal import Decimal, InvalidOperation

DEFAULT_EXCHANGE_RATE = Decimal("1600.0000")
NAIRA_CURRENCIES = {"NGN", "N", "NAIRA"}


def normalized_exchange_rate(value):
    """Return a safe, positive exchange rate for pricing calculations."""
    try:
        rate = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return DEFAULT_EXCHANGE_RATE

    if not rate.is_finite() or rate <= 0:
        return DEFAULT_EXCHANGE_RATE
    return rate


def currency_amount_in_naira(amount, currency="USD", exchange_rate=None):
    try:
        value = Decimal(str(amount).replace(",", ""))
    except (InvalidOperation, TypeError, AttributeError):
        value = Decimal("0")

    if str(currency or "USD").upper() not in NAIRA_CURRENCIES:
        value *= normalized_exchange_rate(exchange_rate)
    return value


def travel_agency_for_user(user):
    """Resolve an agency directly or through a staff/admin organization."""
    if not getattr(user, "is_authenticated", False):
        return None

    from .models import Admin, Staff, TravelAgency

    direct_agency = TravelAgency.objects.filter(
        admin=user,
        approval_status=True,
    ).first()
    if direct_agency:
        return direct_agency

    staff_profile = Staff.objects.select_related(
        "organization__travel_agency"
    ).filter(staff=user).first()
    if staff_profile and staff_profile.organization:
        agency = staff_profile.organization.travel_agency
        if agency and agency.approval_status:
            return agency

    admin_profile = Admin.objects.select_related(
        "organization__travel_agency"
    ).filter(admin=user, approval_status=True).first()
    if admin_profile and admin_profile.organization:
        agency = admin_profile.organization.travel_agency
        if agency and agency.approval_status:
            return agency

    return None


def exchange_rate_for_agency(agency):
    if not agency:
        return DEFAULT_EXCHANGE_RATE
    return normalized_exchange_rate(agency.exchange_rate)


def exchange_rate_for_user(user):
    return exchange_rate_for_agency(travel_agency_for_user(user))
