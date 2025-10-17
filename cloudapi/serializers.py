from decimal import Decimal
from rest_framework import serializers
from .models import CollaborationRequest, Commitment

class CollaborationRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = CollaborationRequest
        fields = "__all__"
        read_only_fields = ("reserved_qty", "fulfilled_qty", "status", "created_at", "updated_at")

    def validate(self, attrs):
        target = attrs.get("target_qty")
        if target is not None and target < 0:
            raise serializers.ValidationError({"target_qty": "No puede ser negativo."})
        return attrs


class CommitmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Commitment
        fields = "__all__"
        read_only_fields = ("status", "commitment_date", "updated_at")

    def validate(self, attrs):
        req = attrs.get("request") or self.instance.request  # create or update
        amt = attrs.get("amount")
        if amt is not None and amt < 0:
            raise serializers.ValidationError({"amount": "No puede ser negativo."})

        target = req.target_qty
        if self.instance is None:  # create
            if target is not None and amt is not None:
                if req.reserved_qty + amt > target:
                    raise serializers.ValidationError(
                        {"amount": "La reserva total excede el objetivo (target_qty)."}
                    )
        return attrs
