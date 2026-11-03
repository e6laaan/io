from rest_framework import serializers
from .models import Patient, Ticket, TicketHistory, FollowUp


class PatientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Patient
        fields = '__all__'


class TicketHistorySerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source='author.username', read_only=True)

    class Meta:
        model = TicketHistory
        fields = ['id', 'ticket', 'author', 'author_name', 'comment', 'created_at']
        read_only_fields = ['author', 'created_at']


class FollowUpSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source='patient.__str__', read_only=True)
    assigned_name = serializers.CharField(source='assigned_to.username', read_only=True)

    class Meta:
        model = FollowUp
        fields = '__all__'


class TicketSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source='patient.__str__', read_only=True)
    assigned_name = serializers.CharField(source='assigned_to.username', read_only=True)
    history = TicketHistorySerializer(many=True, read_only=True)
    follow_ups = FollowUpSerializer(many=True, read_only=True)

    class Meta:
        model = Ticket
        fields = '__all__'