from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("core.urls")),
    path("api/", include("catalog.urls")),
    path("api/", include("marketplace.urls")),
    path("api/seller/", include("sellerportal.urls")),
    path("api/facility/", include("facility.urls")),
    path("api/rerouting/", include("rerouting.urls")),
    path("api/nextowner/", include("nextowner.urls")),
    path("", include("greencredits.urls")),
]

if not settings.USE_S3:
    # Local file storage → Django serves /media/ (any DEBUG value; nginx proxies it).
    # With USE_S3=1, media URLs point straight at S3/CloudFront — nothing to serve here.
    from django.views.static import serve as media_serve

    urlpatterns += [
        path(
            "media/<path:path>",
            media_serve,
            {"document_root": settings.MEDIA_ROOT},
        ),
    ]
