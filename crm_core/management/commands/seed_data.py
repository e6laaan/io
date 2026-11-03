from datetime import timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone

from crm_core.models import (
    Patient, Ticket, TicketHistory, FollowUp, OutboxEvent, 
    Campaign, TicketStatus, RejectionReason
)


class Command(BaseCommand):
    help = "Наполняет базу полным набором справочников и тестовых сценариев (ТЗ 1.1–7.6)"

    def handle(self, *args, **options):
        self.stdout.write("Очистка старых данных...")
        OutboxEvent.objects.all().delete()
        FollowUp.objects.all().delete()
        TicketHistory.objects.all().delete()
        Ticket.objects.all().delete()
        Patient.objects.all().delete()
        Campaign.objects.all().delete()
        TicketStatus.objects.all().delete()
        RejectionReason.objects.all().delete()

        # Создаем суперпользователя и второго оператора для проверки сменности (п. 7.5, 7.6)
        admin_user = User.objects.filter(is_superuser=True).first()
        if not admin_user:
            admin_user = User.objects.create_superuser('admin', 'admin@medcrm.local', 'admin123')
            self.stdout.write("Создан супервайзер: admin / admin123")

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

        self.stdout.write("3. Создание рекламных кампаний (п. 4.5 ТЗ)...")
        c_mrt = Campaign.objects.create(
            name="Контекст УЗИ и МРТ",
            source="Google Ads", 
            utm_campaign="google_uzi_2026", 
            budget=Decimal("150000.00")
        )
        c_checkup = Campaign.objects.create(
            name="Таргет Чек-ап Здоровье",
            source="Instagram",
            utm_campaign="insta_checkup_spring",
            budget=Decimal("95000.00")
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

        self.stdout.write("5. Создание обращений, истории и воронки...")
        # Сценарий А: Успешная запись и оплата (закрыто)
        t1 = Ticket.objects.create(
            patient=p1,
            assigned_to=admin_user,
            campaign=c_checkup,
            channel=Ticket.Channel.WHATSAPP,
            status=status_map['completed'],
            subject="Консультация по акции чек-апа",
            service_name="Комплексный кардио чек-ап",
            is_booked=True,
            is_service_rendered=True,
            revenue=Decimal("45000.00"),
            result="Записан на прием",
            closed_at=now
        )
        TicketHistory.objects.create(ticket=t1, author=admin_user, comment="Пациент согласовал запись на 15:00")

        # Сценарий Б: Пропущенный звонок + просроченная задача для супервайзера (п. 7.4)
        t2 = Ticket.objects.create(
            patient=p2,
            assigned_to=admin_user,
            channel=Ticket.Channel.MISSED_CALL,
            status=status_map['followup_needed'],
            subject="Пропущенный входящий вызов",
            next_contact_date=now - timedelta(minutes=45),  # 45 минут назад = просрочено
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

        # Сценарий В: Обращение в работе на второй смене (п. 7.5)
        t3 = Ticket.objects.create(
            patient=p1,
            assigned_to=operator2,
            campaign=c_mrt,
            channel=Ticket.Channel.INBOUND_CALL,
            status=status_map['in_progress'],
            subject="УЗИ коленного сустава",
            service_name="УЗИ суставов",
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

        # Сценарий Г: Отказ с обязательной фиксацией причины (п. 6.5, 6.6)
        Ticket.objects.create(
            patient=p3,
            assigned_to=admin_user,
            campaign=c_mrt,
            channel=Ticket.Channel.WEBSITE_FORM,
            status=status_map['rejected'],
            rejection_reason=reason_map['expensive'],
            subject="Заявка на МРТ с сайта",
            service_name="МРТ поясничного отдела",
            result="Отказ",
            closed_at=now
        )

        # Сценарий Д: Неидентифицированное обращение до установления личности (п. 5.6 ТЗ)
        Ticket.objects.create(
            patient=None,
            raw_contact="+77051112233",
            channel=Ticket.Channel.INBOUND_CALL,
            status=status_map['new'],
            subject="Анонимный входящий звонок: консультация по прайсу",
            description="Звонящий не назвал ФИО. Интересовался стоимостью приема терапевта."
        )

        self.stdout.write("6. Буфер Outbox (п. 1.4 ТЗ)...")
        OutboxEvent.objects.create(
            target_system="WhatsApp Business Gateway",
            event_type="send_template_reminder",
            payload={"phone": p1.phone, "template": "visit_confirmation_24h"},
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

        self.stdout.write(self.style.SUCCESS("База успешно наполнена всеми данными ТЗ 1.1–7.6!"))