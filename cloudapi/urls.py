from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiExample
from .views import ProjectViewSet, RequestViewSet, CommitmentViewSet, StageViewSet, ObservationViewSet, UserViewSet

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
router.register(r"projects", ProjectViewSet, basename="projects")
router.register(r"requests", RequestViewSet, basename="requests")
router.register(r"commitments", CommitmentViewSet, basename="commitments")
router.register(r"stages", StageViewSet, basename="stages")
router.register(r"observations", ObservationViewSet, basename="observations")
router.register(r"users", UserViewSet, basename="users")

urlpatterns = [
    path("auth/login", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/refresh", TokenRefreshView.as_view(), name="token_refresh"),
    path("", include(router.urls)),
]