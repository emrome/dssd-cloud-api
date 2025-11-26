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
    """
    Pedido de colaboración (dinero, materiales, etc.)
    """
    project = models.PositiveIntegerField(
        db_index=True,
        help_text="ID del proyecto en el sistema ProjectPlanning (Django web)."
    )

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    request_type = models.CharField(max_length=10, choices=RequestType.choices)

    target_qty = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)]
    )

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
            models.Index(fields=["project"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.title} [{self.get_request_type_display()}] ({self.status})"


class Commitment(models.Model):
    """
    Compromiso de colaboración.
    """
    request = models.ForeignKey(
        CollaborationRequest, on_delete=models.CASCADE, related_name="commitments"
    )

    actor_label = models.CharField(max_length=140, blank=True, null=True, db_index=True)

    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=12, choices=CommitmentStatus.choices,
        default=CommitmentStatus.ACTIVE, db_index=True
    )
    commitment_date = models.DateTimeField(auto_now_add=True)
    ong_name = models.CharField(max_length=200, null=True, blank=True)
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
