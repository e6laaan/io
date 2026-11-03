import csv
from decimal import Decimal
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.db import models
from django.db.models import Count, Sum, F
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from .models import Patient, Ticket, TicketHistory, FollowUp, OutboxEvent, Campaign, TicketStatus, RejectionReason
from .serializers import PatientSerializer, TicketSerializer, TicketHistorySerializer, FollowUpSerializer
from .services import IntegrationService


class PatientViewSet(viewsets.ModelViewSet):
    queryset = Patient.objects.all()
    serializer_class = PatientSerializer

    @action(detail=False, methods=['get'])
    def search_patient(self, request):
        q = request.query_params.get('q', '').strip()
        if not q:
            return Response([])

        patients = Patient.objects.filter(
            models.Q(iin__icontains=q) |
            models.Q(phone__icontains=q) |
            models.Q(extra_phone__icontains=q) |
            models.Q(last_name__icontains=q) |
            models.Q(first_name__icontains=q) |
            models.Q(external_id__icontains=q)
        ).distinct()[:10]

        return Response(PatientSerializer(patients, many=True).data)


class TicketViewSet(viewsets.ModelViewSet):
    queryset = Ticket.objects.select_related('patient', 'assigned_to', 'campaign', 'status', 'rejection_reason').prefetch_related('history', 'follow_ups').all()
    serializer_class = TicketSerializer

    def perform_create(self, serializer):
        st_new = TicketStatus.objects.filter(code='new').first()
        ticket = serializer.save(assigned_to=self.request.user, status=st_new)
        IntegrationService.emit_event(
            target_system="MIS",
            event_type="ticket_created",
            payload={
                "ticket_id": ticket.id,
                "patient_id": ticket.patient_id,
                "phone": ticket.patient.phone if ticket.patient else ticket.raw_contact,
                "subject": ticket.subject,
                "channel": ticket.channel,
            }
        )

    @action(detail=True, methods=['post'])
    def update_stage(self, request, pk=None):
        ticket = self.get_object()
        new_result = request.data.get('result')

        if new_result == 'rejected':
            reason_id = request.data.get('rejection_reason_id')
            reason_obj = RejectionReason.objects.filter(id=reason_id).first() if reason_id else None
            if not reason_obj:
                reason_code = request.data.get('rejection_reason')
                reason_obj = RejectionReason.objects.filter(code=reason_code).first()

            if not reason_obj:
                return Response({"error": "Обязательно укажите причину отказа из справочника"}, status=status.HTTP_400_BAD_REQUEST)

            ticket.result = "Отказ"
            ticket.rejection_reason = reason_obj
            status_closed = TicketStatus.objects.filter(code__in=['completed', 'rejected']).first()
            if status_closed:
                ticket.status = status_closed
            ticket.closed_at = timezone.now()

        elif new_result == 'booked':
            ticket.result = "Записан на прием"
            ticket.is_booked = True
            status_booked = TicketStatus.objects.filter(code='booked').first()
            if status_booked:
                ticket.status = status_booked

        elif new_result in ['followup', 'no_contact', 'thinking']:
            st_followup = TicketStatus.objects.filter(code='followup_needed').first()
            if st_followup:
                ticket.status = st_followup

            next_date_str = request.data.get('next_contact_date')
            scheduled_time = timezone.now() + timezone.timedelta(minutes=30)
            if next_date_str:
                try:
                    scheduled_time = timezone.datetime.fromisoformat(next_date_str)
                except ValueError:
                    pass

            ticket.next_contact_date = scheduled_time
            ticket.result = "Требуется повторный контакт"

            assigned_user = ticket.assigned_to or request.user
            FollowUp.objects.create(
                patient=ticket.patient,
                ticket=ticket,
                assigned_to=assigned_user,
                scheduled_at=scheduled_time,
                reason=request.data.get('reason', f"Авто-задача: контакт по обращению #{ticket.id}"),
                status=FollowUp.Status.SCHEDULED
            )

        if 'revenue' in request.data:
            ticket.revenue = request.data.get('revenue')
            ticket.is_service_rendered = True
            status_closed = TicketStatus.objects.filter(code='completed').first()
            if status_closed:
                ticket.status = status_closed
            ticket.closed_at = timezone.now()

        ticket.save()
        return Response(TicketSerializer(ticket).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def reassign(self, request, pk=None):
        ticket = self.get_object()
        user_id = request.data.get('user_id')
        new_assignee = get_object_or_404(User, id=user_id)
        old_user = ticket.assigned_to.username if ticket.assigned_to else "Не назначен"
        ticket.assigned_to = new_assignee
        ticket.save(update_fields=['assigned_to', 'updated_at'])
        ticket.follow_ups.filter(status=FollowUp.Status.SCHEDULED).update(assigned_to=new_assignee)

        TicketHistory.objects.create(
            ticket=ticket,
            author=request.user,
            comment=f"Обращение перераспределено с {old_user} на {new_assignee.username}"
        )
        return Response({"status": "reassigned", "assigned_to": new_assignee.username})

    @action(detail=True, methods=['post'])
    def send_whatsapp(self, request, pk=None):
        ticket = self.get_object()
        patient = ticket.patient
        if not patient:
            return Response({"error": "Обращение не привязано к пациенту"}, status=status.HTTP_400_BAD_REQUEST)

        message_text = request.data.get('message', '').strip()
        if not message_text:
            return Response({"error": "Текст сообщения обязателен"}, status=status.HTTP_400_BAD_REQUEST)

        if not patient.whatsapp_consent:
            return Response({"error": "Пациент не давал согласия на WhatsApp-коммуникации (п. 2.2 ТЗ)"}, status=status.HTTP_403_FORBIDDEN)

        IntegrationService.emit_event(
            target_system="WhatsApp_Gateway",
            event_type="send_chat_message",
            payload={"phone": patient.phone, "message": message_text, "ticket_id": ticket.id}
        )

        history = TicketHistory.objects.create(
            ticket=ticket,
            author=request.user if request.user.is_authenticated else None,
            comment=f"[Исходящий WhatsApp]: {message_text}"
        )

        return Response({"status": "sent", "history_record": TicketHistorySerializer(history).data}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def link_patient(self, request, pk=None):
        ticket = self.get_object()
        patient_id = request.data.get('patient_id')
        if not patient_id:
            return Response({"error": "patient_id обязателен"}, status=status.HTTP_400_BAD_REQUEST)

        patient = Patient.objects.filter(id=patient_id).first()
        if not patient:
            return Response({"error": "Пациент не найден"}, status=status.HTTP_404_NOT_FOUND)

        ticket.patient = patient
        ticket.save(update_fields=['patient', 'updated_at'])

        TicketHistory.objects.create(
            ticket=ticket,
            author=request.user if request.user.is_authenticated else None,
            comment=f"Обращение привязано к карточке: {patient}"
        )
        return Response({"status": "linked", "ticket_id": ticket.id, "patient": PatientSerializer(patient).data}, status=status.HTTP_200_OK)


class FollowUpViewSet(viewsets.ModelViewSet):
    queryset = FollowUp.objects.select_related('patient', 'assigned_to', 'ticket').all()
    serializer_class = FollowUpSerializer

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        task = self.get_object()
        result_note = request.data.get('result_note', 'Выполнено')
        task.status = FollowUp.Status.COMPLETED
        task.result_note = result_note
        task.completed_at = timezone.now()
        task.save()
        return Response(FollowUpSerializer(task).data)

    @action(detail=True, methods=['post'])
    def reassign(self, request, pk=None):
        task = self.get_object()
        user_id = request.data.get('user_id')
        new_assignee = get_object_or_404(User, id=user_id)
        task.assigned_to = new_assignee
        task.save(update_fields=['assigned_to'])
        return Response({"status": "reassigned", "assigned_to": new_assignee.username})

class AnalyticsSummaryView(APIView):
    """Сводная аналитика по обращениям и статусам (п. 4.5 ТЗ)"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        total_tickets = Ticket.objects.count()
        by_channel = Ticket.objects.values('channel').annotate(count=Count('id'))
        by_status = Ticket.objects.values('status__name').annotate(count=Count('id'))
        pending_followups = FollowUp.objects.filter(status='scheduled').count()

        return Response({
            "total_tickets": total_tickets,
            "tickets_by_channel": by_channel,
            "tickets_by_status": by_status,
            "pending_followups_count": pending_followups,
        })

class ExportAnalyticsCSVView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="marketing_analytics.csv"'
        writer = csv.writer(response)
        writer.writerow(['Кампания', 'Источник', 'Бюджет', 'Всего обращений', 'Выручка (KZT)'])
        campaigns = Campaign.objects.annotate(total_tickets=Count('tickets'), total_income=Sum('tickets__revenue'))
        for c in campaigns:
            writer.writerow([c.name, c.source, c.budget, c.total_tickets, c.total_income or 0])
        return response


@login_required
def dashboard_view(request):
    now = timezone.now()

    test_patient, _ = Patient.objects.get_or_create(
        phone="+77478961765",
        defaults={
            'first_name': 'Никита',
            'last_name': 'Барабан',
            'iin': '080814500123',
            'whatsapp_consent': True,
            'personal_data_consent': True,
            'consent_source': Patient.ConsentSource.WHATSAPP_BOT,
            'consent_updated_at': now,
            'notes': 'Тестовый профиль для проверки воронки'
        }
    )

    test_ticket = Ticket.objects.filter(patient=test_patient).first()
    if not test_ticket:
        admin_user = User.objects.filter(is_superuser=True).first()
        st_new = TicketStatus.objects.filter(code='new').first()
        test_ticket = Ticket.objects.create(
            patient=test_patient,
            assigned_to=admin_user,
            status=st_new,
            channel=Ticket.Channel.WHATSAPP,
            subject="Тестовый диалог WhatsApp",
            description="Проверка согласий и отправки сообщений."
        )

    total_tickets = Ticket.objects.count()
    total_revenue = Ticket.objects.aggregate(total=Sum('revenue'))['total'] or Decimal('0.00')
    missed_calls_count = Ticket.objects.filter(channel=Ticket.Channel.MISSED_CALL, status__code='new').count()
    booked_count = Ticket.objects.filter(is_booked=True).count()

    campaign_stats = Campaign.objects.annotate(tickets_count=Count('tickets'), total_income=Sum('tickets__revenue'))

    # Безопасный alias `name`, чтобы в шаблоне не было VariableDoesNotExist
    rejections = Ticket.objects.filter(
        rejection_reason__isnull=False
    ).values(name=F('rejection_reason__name')).annotate(count=Count('id'))

    pending_tickets = Ticket.objects.filter(
        status__is_final=False,
        patient__isnull=False
    ).select_related('patient', 'assigned_to', 'campaign', 'status').order_by('-created_at')

    unidentified_tickets = Ticket.objects.filter(
        status__is_final=False,
        patient__isnull=True
    ).select_related('assigned_to', 'status').order_by('-created_at')

    all_active_followups = FollowUp.objects.filter(
        status=FollowUp.Status.SCHEDULED
    ).select_related('patient', 'assigned_to', 'ticket').order_by('scheduled_at')

    overdue_followups_count = FollowUp.objects.filter(
        status=FollowUp.Status.SCHEDULED,
        scheduled_at__lt=now
    ).count()

    operators = User.objects.filter(is_active=True)
    integration_events = OutboxEvent.objects.all().order_by('-created_at')[:6]
    patients = Patient.objects.all().order_by('-created_at')[:8]
    rejection_reasons = RejectionReason.objects.filter(is_active=True)
    all_statuses = TicketStatus.objects.all()

    context = {
        'test_patient': test_patient,
        'test_ticket': test_ticket,
        'total_tickets': total_tickets,
        'total_revenue': total_revenue,
        'missed_calls_count': missed_calls_count,
        'booked_count': booked_count,
        'campaign_stats': campaign_stats,
        'rejections': rejections,
        'pending_tickets': pending_tickets,
        'unidentified_tickets': unidentified_tickets,
        'today_followups': all_active_followups,
        'overdue_followups_count': overdue_followups_count,
        'operators': operators,
        'integration_events': integration_events,
        'patients': patients,
        'rejection_reasons': rejection_reasons,
        'all_statuses': all_statuses,
    }
    return render(request, 'crm_core/dashboard.html', context)


@login_required
def patient_card_view(request, patient_id):
    patient = get_object_or_404(
        Patient.objects.prefetch_related('tickets__history', 'follow_ups'), 
        id=patient_id
    )
    tickets = patient.tickets.all().order_by('-created_at')
    follow_ups = patient.follow_ups.all().order_by('-scheduled_at')
    return render(request, 'crm_core/patient_card.html', {
        'patient': patient,
        'tickets': tickets,
        'follow_ups': follow_ups,
    })