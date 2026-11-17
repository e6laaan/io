from datetime import timedelta
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.contrib.auth.models import User

from .models import Patient, Ticket, FollowUp, OutboxEvent, Campaign, TicketStatus
from .services import IntegrationService


from django.db import models
from django.utils.dateparse import parse_datetime

class WebsiteLeadWebhookView(APIView):
    """
    Автоматический приём обращений с официального сайта Больницы (Раздел 11 ТЗ).
    Поддерживает полный набор полей (п. 11.2) и автоопределение источника/кампании по UTM (п. 13.8).
    """
    def post(self, request):
        data = request.data
        phone = data.get('phone', '').strip()
        full_name = data.get('full_name', '').strip()
        service_name = data.get('service_name', '').strip()
        description = data.get('description', '').strip()
        submitted_at_str = data.get('submitted_at', '')

        utm_source = data.get('utm_source', '').strip()
        utm_medium = data.get('utm_medium', '').strip()
        utm_campaign = data.get('utm_campaign', '').strip()
        utm_term = data.get('utm_term', '').strip()
        utm_content = data.get('utm_content', '').strip()
        explicit_source = data.get('source', '').strip()
        campaign_code = data.get('campaign_code', '').strip()

        if not phone:
            return Response({"error": "Поле phone обязательно (п. 11.2 ТЗ)"}, status=status.HTTP_400_BAD_REQUEST)

        # Разбор ФИО
        parts = full_name.split() if full_name else []
        last_name = parts[0] if len(parts) >= 1 else "Заявка с сайта"
        first_name = parts[1] if len(parts) >= 2 else ""
        patronymic = parts[2] if len(parts) >= 3 else ""

        # Поиск или создание пациента (п. 13.6: повторное обращение существующего клиента)
        patient = Patient.objects.filter(phone__icontains=phone).first()
        if not patient:
            patient = Patient.objects.create(
                first_name=first_name or last_name,
                last_name=last_name if first_name else "",
                patronymic=patronymic,
                phone=phone,
                consent_source=Patient.ConsentSource.WEBSITE,
                whatsapp_consent=bool(data.get('whatsapp_consent', True)),
                consent_updated_at=timezone.now()
            )

        # 1. Определение рекламной кампании по коду или utm_campaign (п. 13.4, 13.8)
        campaign = None
        if campaign_code:
            campaign = Campaign.objects.filter(code=campaign_code).first()
        if not campaign and utm_campaign:
            campaign = Campaign.objects.filter(
                models.Q(utm_campaign=utm_campaign) | models.Q(code=utm_campaign)
            ).first()

        # 2. Определение источника привлечения (п. 13.3, 13.8)
        lead_source = explicit_source or utm_source or (campaign.source if campaign else "Официальный сайт")

        st_new = TicketStatus.objects.filter(code='new').first()
        ticket = Ticket.objects.create(
            patient=patient,
            channel=Ticket.Channel.WEBSITE_FORM,  # Канал: сайт (п. 13.2)
            lead_source=lead_source,               # Источник привлечения (п. 13.3)
            campaign=campaign,                     # Кампания, может быть None (п. 13.5)
            status=st_new,
            subject=f"Заявка с сайта: {service_name or 'Консультация'}",
            service_name=service_name,
            description=description,
            utm_source=utm_source,
            utm_medium=utm_medium,
            utm_campaign=utm_campaign,
            utm_term=utm_term,
            utm_content=utm_content,
        )

        if submitted_at_str:
            parsed_dt = parse_datetime(submitted_at_str)
            if parsed_dt:
                Ticket.objects.filter(id=ticket.id).update(created_at=parsed_dt)

        return Response({
            "status": "created",
            "ticket_id": ticket.id,
            "patient_id": patient.id,
            "detected_source": lead_source,
            "detected_campaign": campaign.code if campaign else None
        }, status=status.HTTP_201_CREATED)


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