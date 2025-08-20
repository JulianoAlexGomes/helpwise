from rest_framework import serializers
from .models import Cliente

class ClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cliente
        fields = [
            'id', 'razao_social', 'fantasia', 'cnpj', 'telefone', 'email',
            'endereco', 'numero', 'bairro', 'cep', 'complemento', 'cidade',
            'uf', 'tributacao', 'responsavel', 'observacao', 'uid', 'plano'
        ]