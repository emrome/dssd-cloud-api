from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiExample
from .views import RequestViewSet, CommitmentViewSet

TokenObtainPairView = extend_schema_view(
    post=extend_schema(
        examples=[
            OpenApiExample(
                "Ejemplo de login",
                value={"username": "user_api", "password": "user123"},
                request_only=True,
            )
        ]
    )
)(TokenObtainPairView)

router = DefaultRouter()
router.register(r"requests", RequestViewSet, basename="requests")
router.register(r"commitments", CommitmentViewSet, basename="commitments")

urlpatterns = [
    path("auth/login", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/refresh", TokenRefreshView.as_view(), name="token_refresh"),
    path("", include(router.urls)),
]