"""Root URL configuration. Apps registram suas próprias urls.py conforme aparecem."""

from django.contrib import admin
from django.urls import path

urlpatterns = [
    path("admin/", admin.site.urls),
]
