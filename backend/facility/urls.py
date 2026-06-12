from django.urls import path

from . import views

urlpatterns = [
    path("incoming", views.incoming),
    path("receive", views.receive),
    path("units/<int:pk>/relist", views.relist),
    path("units/<int:pk>/dispose", views.dispose),
    path("watchlist", views.watchlist),
    path("simulate-day", views.simulate_day),
]
