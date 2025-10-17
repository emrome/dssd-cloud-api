from django.shortcuts import render
from decimal import Decimal
from django.db import transaction
from rest_framework import viewsets, decorators, response, status
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
            # si hay cumplidos pero sin target, consideramos COMPLETED cuando no hay más por cumplir
            # criterio simple: si no hay reservas pendientes → COMPLETED; si hay reservas → RESERVED
            req.status = RequestStatus.RESERVED if req.reserved_qty > 0 else RequestStatus.COMPLETED

@extend_schema(
    request=CollaborationRequestSerializer,
    responses=CollaborationRequestSerializer,
    examples=[
        OpenApiExample(
            "Crear pedido (Materiales sin unit)",
            value={
                "project_ref": "11111111-1111-1111-1111-111111111111",
                "need_ref": "22222222-2222-2222-2222-222222222222",
                "title": "Cemento",
                "description": "10 bolsas para la obra",
                "request_type": "MAT",
                "target_qty": "10"
            },
            request_only=True,
        ),
        OpenApiExample(
            "Crear pedido (Económica con target)",
            value={
                "project_ref": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "need_ref": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                "title": "Recaudación para materiales",
                "description": "Fondos para compra de cemento y arena",
                "request_type": "ECON",
                "target_qty": "150000.00"
            },
            request_only=True,
        ),
    ],
)
class RequestViewSet(viewsets.ModelViewSet):
    queryset = CollaborationRequest.objects.all().order_by("-created_at")
    serializer_class = CollaborationRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
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
        obj = serializer.save()
        recompute_request_status(obj)
        obj.save(update_fields=["status"])

@extend_schema(
    request=CommitmentSerializer,
    responses=CommitmentSerializer,
    examples=[
        OpenApiExample(
            "Crear compromiso parcial",
            value={
                "request": "REEMPLAZAR_POR_UUID_DEL_REQUEST",
                "actor_label": "ONG Vecinos",
                "amount": "5",
                "description": "Aporto 5 bolsas"
            },
            request_only=True,
        ),
    ],
)
class CommitmentViewSet(viewsets.ModelViewSet):
    queryset = Commitment.objects.select_related("request").all().order_by("-commitment_date")
    serializer_class = CommitmentSerializer
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def perform_create(self, serializer):
        """
        Crear compromiso en estado ACTIVE:
          - Suma amount a reserved_qty del request (si amount no es None)
          - Recalcula estado del request
        """
        commit = serializer.save(status=CommitmentStatus.ACTIVE)
        req = CollaborationRequest.objects.select_for_update().get(pk=commit.request_id)

        if commit.amount:
            req.reserved_qty = (req.reserved_qty or Decimal("0")) + commit.amount

        recompute_request_status(req)
        req.save(update_fields=["reserved_qty", "status"])

    @extend_schema(
        request=None,
        responses={200: OpenApiExample(
            "Ejecución OK",
            value={"ok": True},
            response_only=True
        )}
    )
    @decorators.action(detail=True, methods=["post"])
    @transaction.atomic
    def execute(self, request, pk=None):
        """
        Ejecuta (cumple) un compromiso:
          - Cambia status a FULFILLED
          - Mueve 'amount' de reserved_qty → fulfilled_qty
          - Recalcula estado del request
        """
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