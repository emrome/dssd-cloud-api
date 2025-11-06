from django.db import transaction
from django.http import Http404 
from rest_framework import viewsets, mixins, decorators, response, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError

from .models import CollaborationRequest, Commitment, CommitmentStatus, Stage, Observation
from .serializers import CollaborationRequestSerializer, CommitmentSerializer, StageSerializer, ObservationSerializer

from .services import (
    recompute_request_status, 
    update_request_on_new_commitment, 
    execute_commitment_service
)
from .exceptions import BusinessLogicError, RelatedRequestNotFoundError

# Swagger
from drf_spectacular.utils import extend_schema, OpenApiExample


@extend_schema(
    tags=["Requests"],
    description="Permite registrar nuevos pedidos de colaboración o consultar los existentes. ",
    examples=[
        OpenApiExample(
            "Crear pedido (Materiales)",
            value={
                "project_ref": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "need_ref": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                "title": "Cemento",
                "description": "10 bolsas para la obra",
                "request_type": "MAT",
                "target_qty": "10"
            },
            request_only=True,
        ),
        OpenApiExample(
            "Crear pedido (Económica)",
            value={
                "project_ref": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "need_ref": "cccccccc-cccc-cccc-cccc-cccccccccccc",
                "title": "Recaudación para materiales",
                "description": "Fondos para compra de cemento y arena",
                "request_type": "ECON",
                "target_qty": "150000.00"
            },
            request_only=True,
        ),
    ],
)
class RequestViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet
):
    """📘 Endpoints para pedidos de colaboración"""
    queryset = CollaborationRequest.objects.all().order_by("-created_at")
    serializer_class = CollaborationRequestSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post"]

    def get_queryset(self):
        """Permite filtrar por project_ref o need_ref"""
        qs = super().get_queryset()
        project_ref = self.request.query_params.get("project_ref")
        need_ref = self.request.query_params.get("need_ref")
        if project_ref:
            qs = qs.filter(project_ref=project_ref)
        if need_ref:
            qs = qs.filter(need_ref=need_ref)
        return qs

    @transaction.atomic
    def perform_create(self, serializer):
        """
        Guarda el pedido y llama al servicio para actualizar 
        automáticamente su estado.
        """
        obj = serializer.save()
        recompute_request_status(obj) 
        obj.save(update_fields=["status"])

    @extend_schema(
        tags=["Requests"],
        operation_id="list_requests_by_project",
        description="Recupera todos los pedidos de colaboración asociados a un proyecto determinado, usando su UUID como parte de la URL.",
        request=None, 
        responses={200: CollaborationRequestSerializer(many=True)} 
    )
    @decorators.action(
        detail=False, 
        methods=["get"], 
        url_path='by-project/(?P<project_ref>[0-9a-f-]{36})'
    )
    def by_project(self, request, project_ref=None):
        """Recupera pedidos en base a un project_ref."""
        qs = self.get_queryset().filter(project_ref=project_ref)

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(qs, many=True)
        return response.Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    tags=["Commitments"],
    description="Permite registrar compromisos de colaboración sobre pedidos existentes o ver la información de compromisos ya realizados.",
    examples=[
        OpenApiExample(
            "Crear compromiso parcial",
            value={
                "request": "11111111-1111-1111-1111-111111111111",
                "actor_label": "ONG Vecinos",
                "amount": "5",
                "description": "Aporto 5 bolsas"
            },
            request_only=True,
        ),
    ],
)
class CommitmentViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet
):
    """🤝 Endpoints para compromisos (alta, ejecución y consulta de estado)"""
    queryset = Commitment.objects.select_related("request").all().order_by("-commitment_date")
    serializer_class = CommitmentSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post"]

    @transaction.atomic
    def perform_create(self, serializer):
        """
        Crea un compromiso en estado ACTIVE y llama al servicio
        para actualizar los totales del pedido.
        """
        commit = serializer.save(status=CommitmentStatus.ACTIVE)
        update_request_on_new_commitment(commit)
        serializer.instance = commit


    @extend_schema(
        tags=["Commitments"],
        operation_id="execute_commitment",
        summary="Marcar un compromiso como completado",
        description="Completa un compromiso, moviendo su monto de reservado a cumplido y recalculando el estado del pedido asociado.",
        request=None,
        responses={
            200: OpenApiExample("Ejecución OK", value={"ok": True}, response_only=True),
            400: OpenApiExample("Error de negocio", value={"ok": False, "error": "Este compromiso ya fue ejecutado previamente."}, response_only=True),
            404: OpenApiExample("No encontrado", value={"ok": False, "error": "No se encontró el compromiso."}, response_only=True),
        }
    )
    @decorators.action(detail=True, methods=["post"])
    def execute(self, request, pk=None):
        """
        Ejecuta (cumple) un compromiso, con manejo de excepciones.
        """
        try:
            commit = self.get_object() 
            execute_commitment_service(commit) 
            return response.Response({"ok": True}, status=status.HTTP_200_OK)
        except Http404:
            return response.Response(
                {"ok": False, "error": "No se encontró el compromiso con el ID proporcionado."}, 
                status=status.HTTP_404_NOT_FOUND
            )  
        except (BusinessLogicError, RelatedRequestNotFoundError) as e:
            return response.Response(
                {"ok": False, "error": e.detail}, 
                status=e.status_code
            )
        except ValidationError as e:
            return response.Response(
                {"ok": False, "error": "Datos inválidos.", "details": e.detail}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return response.Response(
                {"ok": False, "error": "Ocurrió un error interno inesperado al procesar la solicitud."}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

@extend_schema(
    tags=["Stages"],
    description="Permite registrar nuevas etapas de proyecto o consultar las existentes.",
)
class StageViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet
):
    """📋 Endpoints para Etapas del plan de trabajo"""
    queryset = Stage.objects.all().order_by("created_at")
    serializer_class = StageSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post"]

    def get_queryset(self):
        """Permite filtrar por project_ref"""
        qs = super().get_queryset()
        project_ref = self.request.query_params.get("project_ref")
        if project_ref:
            qs = qs.filter(project_ref=project_ref)
        return qs

    @extend_schema(
        tags=["Stages"],
        operation_id="list_stages_by_project",
        description="Recupera todas las etapas asociadas a un proyecto determinado, usando su UUID como parte de la URL.",
        request=None, 
        responses={200: StageSerializer(many=True)} 
    )
    @decorators.action(
        detail=False, 
        methods=["get"], 
        url_path='by-project/(?P<project_ref>[0-9a-f-]{36})'
    )
    def by_project(self, request, project_ref=None):
        """Recupera etapas en base a un project_ref."""
        qs = self.get_queryset().filter(project_ref=project_ref)

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(qs, many=True)
        return response.Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    tags=["Observations"],
    description="Permite registrar nuevas observaciones del consejo directivo o consultar las existentes.",
)
class ObservationViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet
):
    """🔎 Endpoints para Observaciones del Consejo Directivo"""
    queryset = Observation.objects.all().order_by("-created_at")
    serializer_class = ObservationSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post"]

    def get_queryset(self):
        """Permite filtrar por project_ref"""
        qs = super().get_queryset()
        project_ref = self.request.query_params.get("project_ref")
        if project_ref:
            qs = qs.filter(project_ref=project_ref)
        return qs

    @extend_schema(
        tags=["Observations"],
        operation_id="list_observations_by_project",
        description="Recupera todas las observaciones asociadas a un proyecto determinado, usando su UUID como parte de la URL.",
        request=None, 
        responses={200: ObservationSerializer(many=True)} 
    )
    @decorators.action(
        detail=False, 
        methods=["get"], 
        url_path='by-project/(?P<project_ref>[0-9a-f-]{36})'
    )
    def by_project(self, request, project_ref=None):
        """Recupera observaciones en base a un project_ref."""
        qs = self.get_queryset().filter(project_ref=project_ref)

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(qs, many=True)
        return response.Response(serializer.data, status=status.HTTP_200_OK)
