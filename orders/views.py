from django.http import JsonResponse
from .models import Order


def order_summary(request):
    orders = Order.objects.select_related("customer")

    results = []
    for order in orders:
        results.append(
            {
                "order_id": order.id,
                "customer": order.customer.name,
                "total": str(order.total),
            }
        )

    return JsonResponse({"orders": results})
