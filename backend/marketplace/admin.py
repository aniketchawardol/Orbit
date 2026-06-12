from django.contrib import admin

from .models import Listing, Order

admin.site.register(Listing)
admin.site.register(Order)
