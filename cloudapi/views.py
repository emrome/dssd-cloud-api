from decimal import Decimal
from django.db import transaction
from rest_framework import viewsets, mixins, decorators, response, status
from rest_framework.permissions import IsAuthenticated
from .models import CollaborationRequest, Commitment, RequestStatus, CommitmentStatus
from .serializers import CollaborationRequestSerializer, CommitmentSerializer
from drf_spectacular.utils import extend_schema, OpenApiExample

def recompute_request_status(req: CollaborationRequest) -> None:
    """
    Regla:
      - COMPLETED si fulfilled_qty >= target_qty (cuando existe target)
      - RESERVED si reserved_qty > 0 o (fulfilled < target)
      - OPEN si no hay reservas ni cumplidos
    """
    if req.target_qty is not None and req.fulfilled_qty >= req.target_qty:
        req.status = RequestStatus.COMPLETED
    elif (req.reserved_qty > 0) or (req.target_qty is not None and req.fulfilled_qty < req.target_qty):
        req.status = RequestStatus.RESERVED
    else:
        if req.reserved_qty == 0 and req.fulfilled_qty == 0:
            req.status = RequestStatus.OPEN
        else:
            req.status = RequestStatus.RESERVED if req.reserved_qty > 0 else RequestStatus.COMPLETED

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
    mixins.ListModelMixin,     # GET /api/requests/
    mixins.CreateModelMixin,   # POST /api/requests/
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
        """Guarda el pedido y actualiza automáticamente su estado"""
        obj = serializer.save()
        recompute_request_status(obj)
        obj.save(update_fields=["status"])

@extend_schema(
    tags=["Commitments"],
    description="Permite registrar compromisos de colaboración sobre pedidos existentes. ",
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
    mixins.CreateModelMixin,      # POST /api/commitments/
    mixins.RetrieveModelMixin,    # GET /api/commitments/{id}/
    viewsets.GenericViewSet
):
    """🤝 Endpoints para compromisos (alta, ejecución y consulta de estado)"""
    queryset = Commitment.objects.select_related("request").all().order_by("-commitment_date")
    serializer_class = CommitmentSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post"]

    @transaction.atomic
    def perform_create(self, serializer):
        """Crea un compromiso en estado ACTIVE y actualiza los totales del pedido"""
        commit = serializer.save(status=CommitmentStatus.ACTIVE)
        req = CollaborationRequest.objects.select_for_update().get(pk=commit.request_id)

        if commit.amount:
            req.reserved_qty = (req.reserved_qty or Decimal("0")) + commit.amount

        recompute_request_status(req)
        req.save(update_fields=["reserved_qty", "status"])

    @extend_schema(
        tags=["Commitments"],
        operation_id="execute_commitment",
        summary="Marcar un compromiso como completado",
        description="Completa un compromiso, moviendo su monto de reservado a cumplido y recalculando el estado del pedido asociado.",
        responses={
            200: OpenApiExample(
                "Ejecución OK",
                value={"ok": True},
                response_only=True
            )
        }
    )
    @decorators.action(detail=True, methods=["post"])
    @transaction.atomic
    def execute(self, request, pk=None):
        """Ejecuta (cumple) un compromiso"""
        commit = self.get_object()
        if commit.status == CommitmentStatus.FULFILLED:
            return response.Response({"detail": "Ya estaba completado."}, status=status.HTTP_200_OK)

        req = CollaborationRequest.objects.select_for_update().get(pk=commit.request_id)

        amt = commit.amount or Decimal("0")
        if amt > 0:
            req.reserved_qty = max(Decimal("0"), (req.reserved_qty or Decimal("0")) - amt)
            req.fulfilled_qty = (req.fulfilled_qty or Decimal("0")) + amt

        commit.status = CommitmentStatus.FULFILLED
        commit.save(update_fields=["status"])

        recompute_request_status(req)
        req.save(update_fields=["reserved_qty", "fulfilled_qty", "status"])

        return response.Response({"ok": True}, status=status.HTTP_200_OK)