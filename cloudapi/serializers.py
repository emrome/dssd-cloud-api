from rest_framework import serializers
from .models import (
    Project, 
    CollaborationRequest, 
    Commitment, 
    Stage, 
    Observation, 
    User
)

class UserSerializer(serializers.ModelSerializer):
    """
    Serializador para el modelo de User.
    Maneja el hasheo de la contraseña en la creación.
    """
    class Meta:
        model = User
        fields = ['id', 'name', 'email', 'password', 'created_at']
        extra_kwargs = {
            'password': {'write_only': True} # Ocultar password en respuestas GET
        }

    def create(self, validated_data):
        # Hashear la contraseña al crear el usuario
        user = User(
            email=validated_data['email'],
            name=validated_data['name']
        )
        user.set_password(validated_data['password'])
        user.save()
        return user

class CommitmentSerializer(serializers.ModelSerializer):
    """
    Serializador para Compromisos.
    """
    class Meta:
        model = Commitment
        fields = '__all__'
        read_only_fields = ('status', 'commitment_date', 'updated_at')

class CollaborationRequestSerializer(serializers.ModelSerializer):
    """
    Serializador para Pedidos de Colaboración.
    Incluye los compromisos anidados (solo lectura).
    """
    commitments = CommitmentSerializer(many=True, read_only=True)
    
    class Meta:
        model = CollaborationRequest
        fields = '__all__'
        read_only_fields = ('reserved_qty', 'fulfilled_qty', 'status', 'created_at', 'updated_at')

class StageSerializer(serializers.ModelSerializer):
    """
    Serializador para Etapas.
    """
    class Meta:
        model = Stage
        fields = '__all__'
        read_only_fields = ('created_at',)

class ObservationSerializer(serializers.ModelSerializer):
    """
    Serializador para Observaciones.
    """
    class Meta:
        model = Observation
        fields = '__all__'
        read_only_fields = ('created_at',)

class ProjectSerializer(serializers.ModelSerializer):
    """
    Serializador para Proyectos.
    Incluye todas las relaciones anidadas (solo lectura)
    para tener una vista completa del proyecto.
    """
    requests = CollaborationRequestSerializer(many=True, read_only=True)
    stages = StageSerializer(many=True, read_only=True)
    observations = ObservationSerializer(many=True, read_only=True)

    class Meta:
        model = Project
        fields = [
            'id', 'name', 'description', 'start_date', 'end_date', 
            'created_by_ong', 'bonita_case_id', 'created_at', 'updated_at',
            'requests', 'stages', 'observations'
        ]
        read_only_fields = ('created_at', 'updated_at', 'requests', 'stages', 'observations')