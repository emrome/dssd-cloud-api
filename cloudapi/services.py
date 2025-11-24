from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ObjectDoesNotExist
from .models import CollaborationRequest, Commitment, RequestStatus, CommitmentStatus
from .exceptions import CommitmentAlreadyExecutedError, RelatedRequestNotFoundError


@transaction.atomic
def update_request_on_new_commitment(commit: Commitment) -> None:
    """
    Servicio llamado después de crear un compromiso.
    En el modelo simple: un compromiso => el pedido pasa a COMPLETED.
    """
    try:
        req = CollaborationRequest.objects.select_for_update().get(pk=commit.request_id)
        req.status = RequestStatus.COMPLETED
        req.save(update_fields=["status"])
    except ObjectDoesNotExist:
        raise RelatedRequestNotFoundError()


@transaction.atomic
def execute_commitment_service(commit: Commitment) -> None:
    """
    En el modelo simple prácticamente no hace falta,
    pero si lo usás, simplemente marcás el compromiso como FULFILLED
    y el pedido como COMPLETED.
    """
    if commit.status == CommitmentStatus.FULFILLED:
        raise CommitmentAlreadyExecutedError()

    try:
        req = CollaborationRequest.objects.select_for_update().get(pk=commit.request_id)
        req.status = RequestStatus.COMPLETED
        req.save(update_fields=["status"])

        commit.status = CommitmentStatus.FULFILLED
        commit.save(update_fields=["status"])
    except ObjectDoesNotExist:
        raise RelatedRequestNotFoundError()
