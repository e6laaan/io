from datetime import timedelta, date
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone

from crm_core.models import (
    Patient, Ticket, TicketHistory, FollowUp, OutboxEvent, 
    Campaign, TicketStatus, RejectionReason, CallLog, WhatsAppMessage,
    MessageTemplate, BroadcastLog
)


class Command(BaseCommand):
    help = "Наполняет базу полным набором справочников и тестовых сценариев (ТЗ 1.1–14.5)"

    def handle(self, *args, **options):
        self.stdout.write("Очистка старых данных...")
        BroadcastLog.objects.all().delete()
        MessageTemplate.objects.all().delete()
        WhatsAppMessage.objects.all().delete()
        CallLog.objects.all().delete()
        OutboxEvent.objects.all().delete()
        FollowUp.objects.all().delete()
        TicketHistory.objects.all().delete()
        Ticket.objects.all().delete()
        Patient.objects.all().delete()
        Campaign.objects.all().delete()
        TicketStatus.objects.all().delete()
        RejectionReason.objects.all().delete()

        admin_user = User.objects.filter(is_superuser=True).first()
        if not admin_user:
            admin_user = User.objects.create_superuser('admin', 'admin@medcrm.local', 'admin123')
            self.stdout.write("Создан администратор: admin / admin123")

        operator2, _ = User.objects.get_or_create(
            username='operator_sasha',
            defaults={'first_name': 'Александра', 'last_name': 'Смирнова', 'is_staff': True}
        )
        if not operator2.has_usable_password():
            operator2.set_password('admin123')
            operator2.save()

        now = timezone.now()

        self.stdout.write("1. Создание динамических статусов (п. 6.3, 6.4 ТЗ)...")
        statuses_data = [
            ("Новое", "new", False, 1),
            ("В работе", "in_progress", False, 2),
            ("Ожидает решения пациента", "pending_patient", False, 3),
            ("Требуется повторный контакт", "followup_needed", False, 4),
            ("Записан", "booked", False, 5),
            ("Не удалось связаться", "no_contact", False, 6),
            ("Отказался", "rejected", True, 7),
            ("Обращение завершено", "completed", True, 8),
            ("Другое", "other", False, 9),
        ]
        status_map = {}
        for name, code, is_final, order in statuses_data:
            st, _ = TicketStatus.objects.get_or_create(
                code=code, 
                defaults={'name': name, 'is_final': is_final, 'order': order}
            )
            status_map[code] = st

        self.stdout.write("2. Создание причин отказа (п. 6.5, 6.6 ТЗ)...")
        reasons_data = [
            ("Высокая стоимость", "expensive"),
            ("Отсутствует подходящее время", "no_time"),
            ("Отсутствует необходимая услуга", "no_service"),
            ("Пациент думает", "patient_thinking"),
            ("Обратится позднее", "call_later"),
            ("Не удалось связаться", "unreachable"),
            ("Выбрал другой вариант", "competitor"),
            ("Другое", "other"),
        ]
        reason_map = {}
        for name, code in reasons_data:
            rr, _ = RejectionReason.objects.get_or_create(
                code=code, 
                defaults={'name': name, 'is_active': True}
            )
            reason_map[code] = rr

        self.stdout.write("3. Создание справочника рекламных кампаний (Раздел 14 ТЗ)...")
        c_mrt = Campaign.objects.create(
            code="CMP-GOOGLE-MRT",
            name="Контекст УЗИ и МРТ",
            source="Google Ads", 
            utm_campaign="google_uzi_2026", 
            promoted_service="МРТ и УЗИ диагностика",
            start_date=date(2026, 10, 1),
            end_date=date(2026, 12, 31),
            budget=Decimal("150000.00"),
            actual_spend=Decimal("64000.00"),
            is_active=True
        )
        c_checkup = Campaign.objects.create(
            code="CMP-INSTA-CHECKUP",
            name="Таргет Чек-ап Здоровье",
            source="Instagram",
            utm_campaign="insta_checkup_spring",
            promoted_service="Комплексный кардио чек-ап",
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 30),
            budget=Decimal("95000.00"),
            actual_spend=Decimal("41500.00"),
            is_active=True
        )

        self.stdout.write("4. Создание пациентов с ИИН и согласиями (Раздел 5 ТЗ)...")
        p1 = Patient.objects.create(
            first_name="Никита",
            last_name="Барабан",
            iin="080814500123",
            phone="+77478961765",
            extra_phone="+77010001122",
            whatsapp_consent=True,
            consent_updated_at=now,
            consent_source=Patient.ConsentSource.WHATSAPP_BOT,
            external_id="MIS-PAT-9081",
            notes="VIP-профиль: демонстрация полного цикла воронки"
        )
        p2 = Patient.objects.create(
            first_name="Елена",
            last_name="Иванова",
            iin="950925400987",
            phone="+77771234567",
            whatsapp_consent=False,
            consent_updated_at=now - timedelta(days=2),
            consent_source=Patient.ConsentSource.CALL_CENTER,
            notes="Отказ от маркетинговых коммуникаций"
        )
        p3 = Patient.objects.create(
            first_name="Данияр",
            last_name="Нурланов",
            iin="011103500654",
            phone="+77059876543",
            whatsapp_consent=True,
            consent_updated_at=now - timedelta(days=1),
            consent_source=Patient.ConsentSource.WEBSITE
        )

        self.stdout.write("5. Создание обращений, задач, воронки и 3-х признаков аналитики (Разделы 6, 7, 13 ТЗ)...")
        t1 = Ticket.objects.create(
            patient=p1,
            assigned_to=admin_user,
            campaign=c_checkup,
            channel=Ticket.Channel.WHATSAPP,
            lead_source="Instagram Таргет",
            status=status_map['in_progress'],
            subject="Консультация по акции чек-апа",
            service_name="Комплексный кардио чек-ап",
            is_booked=False,
            revenue=Decimal("0.00"),
            result="В диалоге"
        )
        TicketHistory.objects.create(ticket=t1, author=admin_user, comment="Пациент открыл диалог в WhatsApp")

        # Переписка WhatsApp (Раздел 10 ТЗ)
        WhatsAppMessage.objects.create(
            ticket=t1,
            direction=WhatsAppMessage.Direction.INBOUND,
            sender_phone=p1.phone,
            message_text="Здравствуйте! Подскажите, что входит в кардио чек-ап и какая сейчас стоимость?"
        )
        WhatsAppMessage.objects.create(
            ticket=t1,
            direction=WhatsAppMessage.Direction.OUTBOUND,
            sender_phone=p1.phone,
            message_text="Добрый день, Никита! В чек-ап входит ЭКГ с расшифровкой, УЗИ сердца, консультация кардиолога и базовые анализы. По акции стоимость 45 000 ₸. В какое время удобно подойти?",
            author=admin_user
        )
        WhatsAppMessage.objects.create(
            ticket=t1,
            direction=WhatsAppMessage.Direction.INBOUND,
            sender_phone=p1.phone,
            message_text="Отлично, можно ли записаться на эту субботу в первой половине дня?"
        )

        # Просроченная задача супервайзеру по пропущенному (п. 7.4)
        t2 = Ticket.objects.create(
            patient=p2,
            assigned_to=admin_user,
            channel=Ticket.Channel.MISSED_CALL,
            lead_source="Повторный клиент",
            status=status_map['followup_needed'],
            subject="Пропущенный входящий вызов",
            next_contact_date=now - timedelta(minutes=45),
            result="Недозвон"
        )
        FollowUp.objects.create(
            patient=p2,
            ticket=t2,
            assigned_to=admin_user,
            scheduled_at=now - timedelta(minutes=45),
            reason="Срочный авто-перезвон по пропущенному звонку (п. 2.2, 7.4 ТЗ)",
            status=FollowUp.Status.SCHEDULED
        )

        # Обращение на операторе смены (п. 7.5)
        t3 = Ticket.objects.create(
            patient=p1,
            assigned_to=operator2,
            campaign=c_mrt,
            channel=Ticket.Channel.INBOUND_CALL,
            lead_source="Google Поиск",
            status=status_map['in_progress'],
            subject="УЗИ суставов",
            service_name="УЗИ коленного сустава",
            next_contact_date=now + timedelta(hours=2)
        )
        FollowUp.objects.create(
            patient=p1,
            ticket=t3,
            assigned_to=operator2,
            scheduled_at=now + timedelta(hours=2),
            reason="Уточнить удобное время приема у врача-диагноста",
            status=FollowUp.Status.SCHEDULED
        )

        # Отказ с фиксацией причины (п. 6.5, 6.6)
        Ticket.objects.create(
            patient=p3,
            assigned_to=admin_user,
            campaign=c_mrt,
            channel=Ticket.Channel.WEBSITE_FORM,
            lead_source="Google Ads",
            status=status_map['rejected'],
            rejection_reason=reason_map['expensive'],
            subject="Заявка на МРТ с сайта",
            service_name="МРТ поясничного отдела",
            result="Отказ",
            closed_at=now
        )

        # Анонимный звонок до идентификации (п. 5.6)
        Ticket.objects.create(
            patient=None,
            raw_contact="+77051112233",
            channel=Ticket.Channel.INBOUND_CALL,
            lead_source="Не определен",
            status=status_map['new'],
            subject="Анонимный входящий звонок: консультация по прайсу",
            description="Звонящий не назвал ФИО. Интересовался стоимостью консультации терапевта."
        )

        self.stdout.write("6. Создание событий телефонии и записей разговоров (Разделы 8, 9 ТЗ)...")
        CallLog.objects.create(
            call_id="CALL-MISSED-1049",
            direction=CallLog.Direction.INBOUND,
            phone="+77771234567",
            extension="101",
            duration=0,
            is_missed=True,
            processing_status=CallLog.ProcessingStatus.UNPROCESSED,
            ticket=t2,
            started_at=now - timedelta(minutes=45)
        )

        CallLog.objects.create(
            call_id="CALL-ASTERISK-9812",
            direction=CallLog.Direction.INBOUND,
            phone="+77478961765",
            extension="102",
            duration=145,
            is_missed=False,
            processing_status=CallLog.ProcessingStatus.PROCESSED,
            ticket=t3,
            record_id="REC-98124-EXT",
            record_url="https://pbx-storage.hospital.local/records/2026/11/17/rec_98124.mp3",
            comment="Консультация по подготовке к УЗИ",
            started_at=now - timedelta(hours=1)
        )

        self.stdout.write("7. Создание одобренных шаблонов WABA для рассылок (Раздел 12 ТЗ)...")
        tpl1 = MessageTemplate.objects.create(
            name="Акция на Кардио Чек-ап (-20%)",
            waba_template_code="promo_cardio_checkup_2026",
            body="Здравствуйте, {name}! Напоминаем, что в нашей клинике действует специальное предложение на комплексный кардио чек-ап.",
            is_approved=True
        )
        MessageTemplate.objects.create(
            name="Открытие нового кабинета МРТ",
            waba_template_code="new_mri_cabinet_info",
            body="Добрый день, {name}! В клинике открыта запись на высокоточный томограф МРТ без очередей.",
            is_approved=True
        )

        BroadcastLog.objects.create(
            template=tpl1,
            patient=p1,
            rendered_text="Здравствуйте, Никита! Напоминаем, что в нашей клинике действует специальное предложение на комплексный кардио чек-ап.",
            status=BroadcastLog.Status.SENT
        )

        self.stdout.write("8. Буфер Outbox (п. 1.4 ТЗ)...")
        OutboxEvent.objects.create(
            target_system="WhatsApp_Official_WABA",
            event_type="send_chat_message",
            payload={"phone": p1.phone, "message": "Добрый день, Никита!", "ticket_id": t1.id},
            status="sent"
        )
        OutboxEvent.objects.create(
            target_system="Виртуальная АТС",
            event_type="call_record_fetch",
            payload={"call_id": "CALL-98214", "ticket_id": t1.id},
            status="failed",
            retry_count=3,
            last_error="Connection timed out (АТС недоступна, CRM изолирована согласно п. 1.4 ТЗ)"
        )

        self.stdout.write(self.style.SUCCESS("База успешно наполнена всеми данными ТЗ 1.1–14.5!"))