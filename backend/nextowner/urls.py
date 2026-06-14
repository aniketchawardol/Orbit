from django.urls import path

from . import views

urlpatterns = [
    # Seller / buyer
    path("resell", views.resell),
    path("alerts", views.alerts),
    path("auctions/<int:pk>", views.auction_detail),
    path("auctions/<int:pk>/buy", views.buy),
    path("auctions/<int:pk>/step", views.step),  # demo: force a price step
    # Demo "Start matching" surface
    path("demo/products", views.demo_products),
    path("demo/match", views.demo_match),
    path("demo/results", views.demo_results),
]
