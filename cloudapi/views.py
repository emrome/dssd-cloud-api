from django.db import transaction
from django.http import Http404 
from rest_framework import viewsets, mixins, decorators, response, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError

from .models import (
    CollaborationRequest, Commitment, CommitmentStatus
)
from .serializers import (
    CollaborationRequestSerializer, CommitmentSerializer, CreateCollaborationRequestSerializer
)

from .services import (
    recompute_request_status, 
    update_request_on_new_commitment, 
    execute_commitment_service
)
from .exceptions import BusinessLogicError, RelatedRequestNotFoundError
from drf_spectacular.utils import extend_schema, OpenApiExample


@extend_schema(
    tags=["Requests"],
    description="Permite registrar nuevos pedidos de colaboración o consultar los existentes. ",
    examples=[
        OpenApiExample(
            "Crear pedido (Materiales)",
            value={
                # CAMBIO: De UUID a un ID numérico
                "project": 1, 
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
                # CAMBIO: De UUID a un ID numérico
                "project": 1,
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
        """Permite filtrar por project_id"""
        qs = super().get_queryset()
        project_id = self.request.query_params.get("project_id")
        if project_id:
            qs = qs.filter(project=project_id)
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
        description="Recupera todos los pedidos de colaboración asociados a un proyecto determinado, usando su ID como parte de la URL.",
        request=None, 
        responses={200: CollaborationRequestSerializer(many=True)} 
    )
    @decorators.action(
        detail=False, 
        methods=["get"],
        url_path='by-project/(?P<project_id>[0-9]+)'
    )
    def by_project(self, request, project_id=None):
        """Recupera pedidos en base a un project_id."""
        qs = self.get_queryset().filter(project=project_id)

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(qs, many=True)
        return response.Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Requests"],
        operation_id="import_project_requests",
        description="Importa una lista de pedidos provenientes de Bonita para un proyecto determinado.",
        request=CreateCollaborationRequestSerializer(many=True),
        responses={201: CollaborationRequestSerializer(many=True)},
    )
    @decorators.action(
        detail=True,
        methods=["post"],
        url_path='needs/import'
    )
    @transaction.atomic
    def import_needs(self, request, pk=None):
        """
        Recibe una lista JSON de CollaborationRequest y los crea en lote
        para el proyecto indicado.
        """
        if not isinstance(request.data, list):
            return response.Response(
                {"detail": "Se esperaba una lista JSON de pedidos."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        enriched = []
        for item in request.data:
            item["project"] = pk
            enriched.append(item)

        serializer = CreateCollaborationRequestSerializer(data=enriched, many=True)
        serializer.is_valid(raise_exception=True)
        objs = serializer.save()

        for obj in objs:
            recompute_request_status(obj)
            obj.save(update_fields=["status"])

        return response.Response(
            self.get_serializer(objs, many=True).data,
            status=status.HTTP_201_CREATED
        )

@extend_schema(
    tags=["Commitments"],
    description="Permite registrar compromisos de colaboración sobre pedidos existentes o ver la información de compromisos ya realizados.",
    examples=[
        OpenApiExample(
            "Crear compromiso parcial",
            value={
                # CAMBIO: De UUID a un ID numérico
                "request": 1,
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