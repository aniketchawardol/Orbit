from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import ItemUnit, Product
from .serializers import ItemUnitSerializer, ProductSerializer


@api_view(["GET"])
@permission_classes([AllowAny])
def product_list(request):
    qs = Product.objects.all().order_by("-created_at")
    q = request.query_params.get("q")
    category = request.query_params.get("category")
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
    if category:
        qs = qs.filter(category=category)
    return Response(ProductSerializer(qs[:60], many=True).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def product_detail(request, pk):
    try:
        product = Product.objects.get(pk=pk)
    except Product.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)

    from marketplace.models import Listing
    from marketplace.serializers import ListingSerializer

    listings = Listing.objects.filter(
        unit__product=product, state="ACTIVE"
    ).select_related("unit")
    data = ProductSerializer(product).data
    data["listings"] = ListingSerializer(listings, many=True).data
    return Response(data)


@api_view(["GET"])
@permission_classes([AllowAny])
def unit_health_card(request, pk):
    """Public Health Card: unit lifecycle + grade + events."""
    try:
        unit = ItemUnit.objects.select_related("product").get(pk=pk)
    except ItemUnit.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)
    return Response(ItemUnitSerializer(unit).data)
