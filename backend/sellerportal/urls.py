from django.urls import path

from . import views

urlpatterns = [
    path("products", views.products),
    path("returns", views.returns_inbox),
    path("returns/apply", views.apply_action),
    path("returns/bulk", views.bulk_apply),
    path("rules", views.rules),
    path("rules/<int:pk>", views.rule_detail),
]
