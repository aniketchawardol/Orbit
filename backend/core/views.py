from django.contrib.auth import authenticate, login, logout
from django.core.exceptions import ObjectDoesNotExist
import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import Roles, User

log = logging.getLogger(__name__)


def _precompute_return_prevention(user):
    """Best-effort: warm accessory-compatibility verdicts in parallel on login."""
    try:
        from returnprevention.tasks import precompute_for_user

        precompute_for_user.delay(user.id)
    except Exception:  # noqa: BLE001 — a broker hiccup must never block auth
        log.exception("could not enqueue return-prevention precompute for %s", user.id)


def _user_payload(user):
    payload = {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "email": user.email or "",
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
        "city": user.city or "",
        "lat": user.lat,
        "lng": user.lng,
        "profile": user.profile or {},
        "date_joined": user.date_joined.isoformat() if user.date_joined else None,
    }
    try:
        # green_credits is a OneToOne relation created by greencredits app; include balance if present
        payload["green_credits"] = {"balance": user.green_credits.balance}
    except Exception:
        payload["green_credits"] = {"balance": 0}
    return payload


@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    username = (request.data.get("username") or "").strip()
    password = request.data.get("password") or ""
    role = request.data.get("role", Roles.BUYER)
    if role not in (Roles.BUYER, Roles.SELLER):  # facility accounts: admin-only
        return Response({"detail": "Invalid role."}, status=status.HTTP_400_BAD_REQUEST)
    if not username or not password:
        return Response(
            {"detail": "username and password required."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if User.objects.filter(username=username).exists():
        return Response(
            {"detail": "Username taken."}, status=status.HTTP_409_CONFLICT
        )
    user = User.objects.create_user(username=username, password=password, role=role)
    login(request, user)
    _precompute_return_prevention(user)
    return Response(_user_payload(user), status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    user = authenticate(
        request,
        username=request.data.get("username"),
        password=request.data.get("password"),
    )
    if user is None:
        return Response(
            {"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED
        )
    login(request, user)
    _precompute_return_prevention(user)
    return Response(_user_payload(user))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_view(request):
    logout(request)
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@permission_classes([AllowAny])
def me(request):
    if not request.user.is_authenticated:
        return Response({"user": None})
    return Response({"user": _user_payload(request.user)})
