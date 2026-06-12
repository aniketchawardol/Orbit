from django.urls import path

from . import views

urlpatterns = [
    path("orders", views.my_orders),
    path("orders/place", views.place_order),
    path("orders/<int:pk>/return", views.request_return),
    path("orders/<int:pk>/advance", views.advance_order),
    path("resale", views.resale),
]
