from django.db import transaction
from django.core.exceptions import ObjectDoesNotExist

from .models import (
    CollaborationRequest,
    Commitment,
    RequestStatus,
    CommitmentStatus,
)
from .exceptions import (
    BusinessLogicError,
    CommitmentAlreadyExecutedError,
    RelatedRequestNotFoundError,
)


@transaction.atomic
def update_request_on_new_commitment(commit: Commitment) -> None:
    """
    Servicio llamado después de crear un compromiso.

    Modelo acordado:
    - Cuando se crea un compromiso ACTIVE, el pedido pasa de OPEN -> RESERVED
      para que no se siga ofreciendo a otras ONGs mientras se decide.
    """
    try:
        req = (
            CollaborationRequest.objects
            .select_for_update()
            .get(pk=commit.request_id)
        )
    except ObjectDoesNotExist:
        raise RelatedRequestNotFoundError()

    if req.status != RequestStatus.OPEN:
        raise BusinessLogicError("Solo se puede reservar un pedido en estado OPEN.")

    req.status = RequestStatus.RESERVED
    req.save(update_fields=["status"])


@transaction.atomic
def execute_commitment_service(commit: Commitment) -> None:
    """
    Ejecutar (cumplir) un compromiso.

    Modelo nuevo:
    - El compromiso ya fue aceptado por la ONG solicitante (sigue ACTIVE).
    - El pedido asociado ya está en COMPLETED (lo hizo el endpoint /commitments/{id}/accept/).
    - Acá solo marcamos el compromiso como FULFILLED.
    """
    if commit.status == CommitmentStatus.FULFILLED:
        raise CommitmentAlreadyExecutedError()

    try:
        req = (
            CollaborationRequest.objects
            .select_for_update()
            .get(pk=commit.request_id)
        )
    except ObjectDoesNotExist:
        raise RelatedRequestNotFoundError()

    if req.status != RequestStatus.COMPLETED:
        raise BusinessLogicError(
            "Solo se pueden ejecutar compromisos de pedidos en estado COMPLETED."
        )

    commit.status = CommitmentStatus.FULFILLED
    commit.save(update_fields=["status"])
