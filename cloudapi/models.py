import uuid
from django.db import models
from django.core.validators import MinValueValidator
from django.db.models import Q, F


class RequestType(models.TextChoices):
    ECON = "ECON", "Económica"
    MAT = "MAT", "Materiales"
    MO = "MO", "Mano de obra"
    OTRO = "OTRO", "Otro"


class RequestStatus(models.TextChoices):
    OPEN = "OPEN", "Pendiente"
    RESERVED = "RESERVED", "Reservada"
    COMPLETED = "COMPLETED", "Completada"


class CommitmentStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Comprometido"
    FULFILLED = "FULFILLED", "Completado"
    CANCELLED = "CANCELLED", "Cancelado"


class CollaborationRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    project_ref = models.UUIDField(db_index=True)
    need_ref = models.UUIDField(db_index=True)

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    request_type = models.CharField(max_length=10, choices=RequestType.choices)

    target_qty = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)]
    )
    reserved_qty = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    fulfilled_qty = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    status = models.CharField(
        max_length=12, choices=RequestStatus.choices,
        default=RequestStatus.OPEN, db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'collaboration_request'
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["project_ref"]),
            models.Index(fields=["need_ref"]),
            models.Index(fields=["status"]),
        ]
        constraints = [
            models.CheckConstraint(check=Q(reserved_qty__gte=0), name="req_reserved_nonneg"),
            models.CheckConstraint(check=Q(fulfilled_qty__gte=0), name="req_fulfilled_nonneg"),
            models.CheckConstraint(
                check=Q(target_qty__isnull=True) | Q(fulfilled_qty__lte=F("target_qty")),
                name="req_fulfilled_lte_target_if_set",
            ),
            models.CheckConstraint(
                check=Q(target_qty__isnull=True) | Q(reserved_qty__lte=F("target_qty")),
                name="req_reserved_lte_target_if_set",
            ),
        ]

    def __str__(self):
        return f"{self.title} [{self.get_request_type_display()}] ({self.status})"


class Commitment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(
        CollaborationRequest, on_delete=models.CASCADE, related_name="commitments"
    )

    actor_label = models.CharField(max_length=140, blank=True, null=True, db_index=True)

    description = models.TextField(blank=True)
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)]
    )
    status = models.CharField(
        max_length=12, choices=CommitmentStatus.choices,
        default=CommitmentStatus.ACTIVE, db_index=True
    )
    commitment_date = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "commitment"
        ordering = ["-commitment_date"]
        indexes = [
            models.Index(fields=["request", "status"]),
        ]

    def __str__(self):
        who = self.actor_label or "Sin actor"
        return f"Compromiso de {who} → {self.request.title} ({self.status})"