from datetime import timedelta
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.contrib.auth.models import User

from .models import Patient, Ticket, FollowUp, OutboxEvent, Campaign, TicketStatus
from .services import IntegrationService


class WebsiteLeadWebhookView(APIView):
    """Прием заявок с сайта или лендингов"""
    def post(self, request):
        data = request.data
        phone = data.get('phone', '').strip()
        first_name = data.get('first_name', 'Заявка с сайта')
        service_name = data.get('service_name', '')
        utm_campaign = data.get('utm_campaign', '')

        if not phone:
            return Response({"error": "Поле phone обязательно"}, status=status.HTTP_400_BAD_REQUEST)

        patient, _ = Patient.objects.get_or_create(
            phone=phone,
            defaults={
                'first_name': first_name,
                'last_name': '',
                'consent_source': Patient.ConsentSource.WEBSITE,
                'whatsapp_consent': True,
                'consent_updated_at': timezone.now()
            }
        )

        campaign = Campaign.objects.filter(utm_campaign=utm_campaign).first()
        st_new = TicketStatus.objects.filter(code='new').first()

        ticket = Ticket.objects.create(
            patient=patient,
            channel=Ticket.Channel.WEBSITE_FORM,
            status=st_new,
            subject=f"Заявка с сайта: {service_name or 'Консультация'}",
            service_name=service_name,
            campaign=campaign,
            utm_source=data.get('utm_source', 'website'),
            utm_campaign=utm_campaign
        )

        return Response({"status": "created", "ticket_id": ticket.id}, status=status.HTTP_201_CREATED)


class MissedCallWebhookView(APIView):
    """Вебхук от виртуальной АТС: фиксация пропущенного звонка (п. 2.2 ТЗ)"""
    def post(self, request):
        phone = request.data.get('caller_phone', '').strip()
        if not phone:
            return Response({"error": "caller_phone обязателен"}, status=status.HTTP_400_BAD_REQUEST)

        patient = Patient.objects.filter(phone=phone).first()
        raw_contact = "" if patient else phone
        admin_user = User.objects.filter(is_superuser=True).first()
        st_new = TicketStatus.objects.filter(code='new').first()
        st_followup = TicketStatus.objects.filter(code='followup_needed').first() or st_new

        ticket = Ticket.objects.create(
            patient=patient,
            raw_contact=raw_contact,
            assigned_to=admin_user,
            channel=Ticket.Channel.MISSED_CALL,
            status=st_followup,
            result="Недозвон",
            subject="Пропущенный звонок с АТС",
            description=f"Входящий вызов с номера {phone} не отвечен оператором.",
            next_contact_date=timezone.now() + timedelta(minutes=15)
        )

        FollowUp.objects.create(
            patient=patient,
            ticket=ticket,
            assigned_to=admin_user,
            scheduled_at=timezone.now() + timedelta(minutes=15),
            reason="Срочный перезвон по пропущенному вызову (п. 2.2 ТЗ)",
            status=FollowUp.Status.SCHEDULED
        )

        return Response({"status": "recorded", "ticket_id": ticket.id}, status=status.HTTP_201_CREATED)


class ProcessOutboxQueueView(APIView):
    """
    Фоновый воркер / эндпоинт отправки событий из буфера Outbox (п. 1.4 ТЗ).
    Гарантирует изоляцию CRM при сбоях внешних шлюзов.
    """
    def post(self, request):
        pending_events = OutboxEvent.objects.filter(status='pending')[:20]
        processed = 0

        for event in pending_events:
            try:
                # Симуляция отправки во внешнюю систему
                event.status = 'sent'
                event.save(update_fields=['status', 'updated_at'])
                processed += 1
            except Exception as e:
                event.status = 'failed'
                event.retry_count += 1
                event.last_error = str(e)
                event.save(update_fields=['status', 'retry_count', 'last_error', 'updated_at'])

        return Response({"processed_events": processed}, status=status.HTTP_200_OK)