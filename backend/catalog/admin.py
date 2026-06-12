from django.contrib import admin

from .models import ItemUnit, Product, UnitEvent

admin.site.register(Product)
admin.site.register(ItemUnit)
admin.site.register(UnitEvent)
