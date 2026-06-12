from django.contrib.auth import authenticate, login, logout
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import Roles, User


def _user_payload(user):
    return {"id": user.id, "username": user.username, "role": user.role}


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
