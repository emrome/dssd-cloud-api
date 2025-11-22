from rest_framework import serializers
from .models import (
    CollaborationRequest, 
    Commitment
)

class CommitmentSerializer(serializers.ModelSerializer):
    """
    Serializador para Compromisos.
    """
    class Meta:
        model = Commitment
        fields = '__all__'
        read_only_fields = ('status', 'commitment_date', 'updated_at')

class CollaborationRequestSerializer(serializers.ModelSerializer):
    commitments = CommitmentSerializer(many=True, read_only=True)

    class Meta:
        model = CollaborationRequest
        fields = '__all__'
        read_only_fields = (
            'reserved_qty',
            'fulfilled_qty',
            'status',
            'created_at',
            'updated_at',
        )

class CreateCollaborationRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = CollaborationRequest
        fields = ["project", "title", "description", "request_type", "target_qty"]
