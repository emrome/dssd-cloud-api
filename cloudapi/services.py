from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ObjectDoesNotExist
from .models import CollaborationRequest, Commitment, RequestStatus, CommitmentStatus
from .exceptions import CommitmentAlreadyExecutedError, RelatedRequestNotFoundError

def recompute_request_status(req: CollaborationRequest) -> None:
    """
    Recalcula el estado de un Pedido en base a sus cantidades.
    
    Reglas:
    1. Si tiene objetivo (target) Y se cumplió (fulfilled >= target), está COMPLETED.
    2. Si no hay NADA reservado NI cumplido, está OPEN.
    3. Cualquier otro caso (hay reservas, o hay cumplidos pero sin llegar 
       al objetivo) se considera RESERVED.
    """
    
    # Caso 1: Completo (solo si hay un objetivo definido)
    if req.target_qty is not None and req.fulfilled_qty >= req.target_qty:
        req.status = RequestStatus.COMPLETED
        return

    # Caso 2: Abierto (si no hay nada de nada)
    if req.reserved_qty == 0 and req.fulfilled_qty == 0:
        req.status = RequestStatus.OPEN
        return

    # Caso 3: Reservado (todos los demás casos intermedios)
    req.status = RequestStatus.RESERVED

@transaction.atomic
def update_request_on_new_commitment(commit: Commitment) -> None:
    """
    Servicio llamado *después* de crear un Compromiso.
    Actualiza el Pedido (Request) asociado, bloqueando la fila para concurrencia.
    """
    try:
        # Bloqueo de la fila del Pedido para evitar race conditions
        req = CollaborationRequest.objects.select_for_update().get(pk=commit.request_id)
        
        if commit.amount:
            req.reserved_qty = (req.reserved_qty or Decimal("0")) + commit.amount
        
        recompute_request_status(req)
        req.save(update_fields=["reserved_qty", "status"])

    except ObjectDoesNotExist:
        raise RelatedRequestNotFoundError()

@transaction.atomic
def execute_commitment_service(commit: Commitment) -> None:
    """
    Servicio que ejecuta (cumple) un Compromiso.
    Mueve las cantidades de "reservado" a "cumplido" en el Pedido.
    """
    if commit.status == CommitmentStatus.FULFILLED:
        raise CommitmentAlreadyExecutedError()

    try:
        # Bloquear el Pedido asociado
        req = CollaborationRequest.objects.select_for_update().get(pk=commit.request_id)
        
        amt = commit.amount or Decimal("0")
        if amt > 0:
            # Asegurarse de no dejar valores negativos
            req.reserved_qty = max(Decimal("0"), (req.reserved_qty or Decimal("0")) - amt)
            req.fulfilled_qty = (req.fulfilled_qty or Decimal("0")) + amt

        commit.status = CommitmentStatus.FULFILLED
        commit.save(update_fields=["status"])
        
        recompute_request_status(req)
        req.save(update_fields=["reserved_qty", "fulfilled_qty", "status"])

    except ObjectDoesNotExist:
        raise RelatedRequestNotFoundError()