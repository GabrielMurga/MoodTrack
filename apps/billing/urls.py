from django.urls import path

from . import views

app_name = "billing"

urlpatterns = [
    path("billing/", views.billing_dashboard, name="dashboard"),
    path("billing/checkout/", views.create_checkout, name="create_checkout"),
    path("billing/checkout/success/", views.checkout_success, name="checkout_success"),
    path("billing/portal/", views.open_portal, name="open_portal"),
    path("billing/webhook/stripe/", views.stripe_webhook, name="stripe_webhook"),
]
