from .cart import cart_count
from .models import Staff


def booking_cart(request):
    can_checkout = (
        request.user.is_authenticated
        and Staff.objects.filter(staff=request.user).exists()
    )
    return {
        "cart_count": cart_count(request),
        "cart_checkout_allowed": can_checkout,
    }
