from django.urls import path
from .views import order_summary

urlpatterns = [
    path("orders/summary/", order_summary, name="order-summary"),
]
