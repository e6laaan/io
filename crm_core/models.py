from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Campaign(models.Model):
    """Справочник рекламных кампаний (Раздел 14 ТЗ)"""
    code = models.CharField("Уникальный код / Внешний ID (п. 14.2, 14.3)", max_length=64, unique=True, db_index=True)
    name = models.CharField("Наименование кампании (п. 14.2)", max_length=150)
    source = models.CharField("Источник / вид размещения (п. 14.2)", max_length=100)
    utm_campaign = models.CharField("UTM-метка кампании", max_length=100, blank=True, db_index=True)
    promoted_service = models.CharField("Продвигаемая услуга / направление (п. 14.2)", max_length=150, blank=True)
    start_date = models.DateField("Дата начала (п. 14.2)", null=True, blank=True)
    end_date = models.DateField("Дата окончания (п. 14.2)", null=True, blank=True)
    budget = models.DecimalField("Плановый бюджет (п. 14.4)", max_digits=12, decimal_places=2, default=0.00)
    actual_spend = models.DecimalField("Фактический расход (п. 14.4)", max_digits=12, decimal_places=2, default=0.00)
    is_active = models.BooleanField("Статус кампании (активна) (п. 14.2)", default=True)
    extra_metrics = models.JSONField("Доп. показатели (п. 14.5)", default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Рекламная кампания"
        verbose_name_plural = "Справочник рекламных кампаний (Раздел 14)"
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.code}] {self.name} ({self.source})"


class TicketStatus(models.Model):
    """Справочник статусов обращений (Раздел 6 ТЗ)"""
    name = models.CharField("Название статуса", max_length=100, unique=True)
    code = models.SlugField("Системный код", max_length=50, unique=True)
    is_final = models.BooleanField("Финальный статус", default=False)
    order = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        verbose_name = "Статус обращения"
        verbose_name_plural = "Справочник статусов"
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class RejectionReason(models.Model):
    """Справочник причин незаписи/отказа (Раздел 6 ТЗ)"""
    name = models.CharField("Причина отказа", max_length=150, unique=True)
    code = models.SlugField("Системный код", max_length=50, unique=True)
    is_active = models.BooleanField("Активна", default=True)

    class Meta:
        verbose_name = "Причина отказа"
        verbose_name_plural = "Справочник причин отказа"
        ordering = ['name']

    def __str__(self):
        return self.name


class Patient(models.Model):
    """Единая карточка пациента (Раздел 5 ТЗ)"""
    class ConsentSource(models.TextChoices):
        RECEPTION = 'reception', 'Лично на стойке регистрации (бумага)'
        WEBSITE = 'website', 'Форма на официальном сайте'
        WHATSAPP_BOT = 'whatsapp_bot', 'Чат-бот WhatsApp'
        CALL_CENTER = 'call_center', 'Устное согласие оператору'
        IMPORT = 'import', 'Файловый импорт / МИС'

    first_name = models.CharField("Имя", max_length=100)
    last_name = models.CharField("Фамилия", max_length=100)
    patronymic = models.CharField("Отчество", max_length=100, blank=True)
    iin = models.CharField("ИИН", max_length=12, blank=True, null=True, db_index=True)
    phone = models.CharField("Основной телефон", max_length=20, db_index=True)
    extra_phone = models.CharField("Дополнительный телефон", max_length=20, blank=True)
    email = models.EmailField("Email", blank=True, null=True)
    birth_date = models.DateField("Дата рождения", blank=True, null=True)
    external_id = models.CharField("Внешний ID (МИС / 1С)", max_length=100, blank=True, db_index=True)

    whatsapp_consent = models.BooleanField("Согласие на WhatsApp", default=False)
    personal_data_consent = models.BooleanField("Согласие на ПДн", default=True)
    consent_updated_at = models.DateTimeField("Дата фиксации согласия", null=True, blank=True)
    consent_source = models.CharField(
        "Источник согласия",
        max_length=30,
        choices=ConsentSource.choices,
        default=ConsentSource.RECEPTION
    )

    notes = models.TextField("Сервисные заметки", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Пациент"
        verbose_name_plural = "Пациенты"
        ordering = ['-created_at']

    def __str__(self):
        iin_str = f" | ИИН: {self.iin}" if self.iin else ""
        return f"{self.last_name} {self.first_name} ({self.phone}){iin_str}"

    @property
    def total_tickets_count(self):
        return self.tickets.count()

    @property
    def total_booked_count(self):
        return self.tickets.filter(is_booked=True).count()

    @property
    def total_revenue(self):
        res = self.tickets.aggregate(total=models.Sum('revenue'))['total']
        return res or Decimal('0.00')

    @property
    def total_rejections_count(self):
        return self.tickets.filter(rejection_reason__isnull=False).count()


class Ticket(models.Model):
    """Обращение пациента (Разделы 1, 6, 13 ТЗ)"""
    class Channel(models.TextChoices):
        INBOUND_CALL = 'inbound_call', 'Входящий звонок'
        MISSED_CALL = 'missed_call', 'Пропущенный звонок'
        OUTBOUND_CALL = 'outbound_call', 'Исходящий звонок'
        WHATSAPP = 'whatsapp', 'WhatsApp чат'
        WEBSITE_FORM = 'website_form', 'Заявка с сайта'
        FILE_IMPORT = 'file_import', 'Файловый импорт'
        OFFLINE = 'offline', 'Стойка / Визит'
        OTHER = 'other', 'Другое'

    patient = models.ForeignKey(Patient, on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets')
    raw_contact = models.CharField("Контакт до идентификации", max_length=100, blank=True)
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_tickets')
    campaign = models.ForeignKey(Campaign, on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets')

    status = models.ForeignKey(TicketStatus, on_delete=models.PROTECT, related_name='tickets', null=True, blank=True)
    rejection_reason = models.ForeignKey(RejectionReason, on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets')

    channel = models.CharField("Канал обращения (п. 13.2)", max_length=30, choices=Channel.choices, default=Channel.INBOUND_CALL)
    lead_source = models.CharField("Источник привлечения (п. 13.3, 13.7)", max_length=100, blank=True)
    subject = models.CharField("Тема / направление", max_length=255)
    description = models.TextField("Содержание обращения", blank=True)
    result = models.CharField("Результат", max_length=100, blank=True)
    next_contact_date = models.DateTimeField("Дата следующего контакта", null=True, blank=True)

    utm_source = models.CharField(max_length=100, blank=True)
    utm_medium = models.CharField(max_length=100, blank=True)
    utm_campaign = models.CharField(max_length=100, blank=True)
    utm_term = models.CharField(max_length=100, blank=True)
    utm_content = models.CharField(max_length=100, blank=True)

    service_name = models.CharField("Услуга / Врач", max_length=150, blank=True)
    is_booked = models.BooleanField("Факт записи", default=False)
    is_service_rendered = models.BooleanField("Услуга оказана", default=False)
    revenue = models.DecimalField("Сумма оплаты", max_digits=12, decimal_places=2, default=0.00)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Обращение"
        verbose_name_plural = "Обращения"
        ordering = ['-created_at']

    def __str__(self):
        pat_name = self.patient.last_name if self.patient else f"Неопознан ({self.raw_contact})"
        st_name = self.status.name if self.status else "Без статуса"
        return f"№{self.id} | {pat_name} | {st_name}"


class TicketHistory(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='history')
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    comment = models.TextField("Комментарий / Действие")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Запись истории"
        verbose_name_plural = "История взаимодействий"
        ordering = ['created_at']


class FollowUp(models.Model):
    """Задачи и повторные контакты (Раздел 7 ТЗ)"""
    class Status(models.TextChoices):
        SCHEDULED = 'scheduled', 'Запланирована'
        COMPLETED = 'completed', 'Выполнена'
        CANCELLED = 'cancelled', 'Отменена'

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='follow_ups', null=True, blank=True)
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='follow_ups', null=True, blank=True)
    assigned_to = models.ForeignKey(User, on_delete=models.CASCADE, related_name='follow_ups')
    scheduled_at = models.DateTimeField("Срок выполнения", db_index=True)
    reason = models.CharField("Описание задачи", max_length=255)
    status = models.CharField("Статус", max_length=20, choices=Status.choices, default=Status.SCHEDULED, db_index=True)
    result_note = models.TextField("Результат", blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Задача"
        verbose_name_plural = "Задачи и повторные контакты"
        ordering = ['scheduled_at']

    @property
    def is_overdue(self):
        return self.status == self.Status.SCHEDULED and self.scheduled_at < timezone.now()


class OutboxEvent(models.Model):
    """Буфер Outbox для изоляции внешних сбоев (п. 1.4 ТЗ)"""
    event_type = models.CharField("Тип события", max_length=100, db_index=True)
    payload = models.JSONField("Тело события")
    target_system = models.CharField("Система", max_length=50)
    status = models.CharField("Статус", max_length=20, default='pending', db_index=True)
    retry_count = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Событие Outbox"
        verbose_name_plural = "Журнал Outbox"
        ordering = ['-created_at']


class CallLog(models.Model):
    """Журнал телефонных событий, CDR и записей (Разделы 8, 9 ТЗ)"""
    class Direction(models.TextChoices):
        INBOUND = 'inbound', 'Входящий'
        OUTBOUND = 'outbound', 'Исходящий'

    class ProcessingStatus(models.TextChoices):
        UNPROCESSED = 'unprocessed', 'Не обработан'
        IN_PROGRESS = 'in_progress', 'В работе'
        PROCESSED = 'processed', 'Обработан'

    call_id = models.CharField("Идентификатор звонка АТС", max_length=100, blank=True, db_index=True)
    direction = models.CharField("Направление вызова (п. 8.2)", max_length=10, choices=Direction.choices, default=Direction.INBOUND)
    phone = models.CharField("Номер телефона (п. 8.2)", max_length=30, db_index=True)
    extension = models.CharField("Внутренний номер / линия (п. 8.2)", max_length=50, blank=True)
    operator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Оператор (п. 8.2)")

    started_at = models.DateTimeField("Дата и время начала (п. 8.2)", default=timezone.now, db_index=True)
    duration = models.PositiveIntegerField("Длительность (сек) (п. 8.2)", default=0)
    is_missed = models.BooleanField("Признак пропущенного вызова (п. 8.1, 8.2)", default=False, db_index=True)

    processing_status = models.CharField(
        "Статус обработки (п. 8.2)",
        max_length=20,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.UNPROCESSED,
        db_index=True
    )

    ticket = models.ForeignKey(
        'Ticket', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='calls', verbose_name="Связанное обращение"
    )
    record_id = models.CharField("ID записи во внешней АТС (п. 9.2)", max_length=150, blank=True)
    record_url = models.URLField("Ссылка на запись разговора (п. 9.2)", max_length=500, blank=True)
    comment = models.CharField("Примечание оператора", max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Телефонное событие (CDR)"
        verbose_name_plural = "Журнал вызовов (Раздел 8)"
        ordering = ['-started_at']

    def __str__(self):
        missed = " [ПРОПУЩЕН]" if self.is_missed else ""
        return f"{self.get_direction_display()} {self.phone}{missed} - {self.started_at.strftime('%d.%m %H:%M')}"


class WhatsAppMessage(models.Model):
    """Сообщения диалогов WhatsApp (Раздел 10 ТЗ)"""
    class Direction(models.TextChoices):
        INBOUND = 'inbound', 'Входящее'
        OUTBOUND = 'outbound', 'Исходящее'

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='whatsapp_messages')
    direction = models.CharField("Направление", max_length=10, choices=Direction.choices)
    sender_phone = models.CharField("Номер отправителя", max_length=30)
    message_text = models.TextField("Текст сообщения")
    external_message_id = models.CharField("ID сообщения в шлюзе", max_length=150, blank=True)
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Оператор")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Сообщение WhatsApp"
        verbose_name_plural = "Сообщения WhatsApp (Раздел 10)"
        ordering = ['created_at']

    def __str__(self):
        return f"[{self.get_direction_display()}] {self.sender_phone}: {self.message_text[:30]}"


class MessageTemplate(models.Model):
    """Одобренные шаблоны сообщений WhatsApp (п. 12.2, 12.6 ТЗ)"""
    name = models.CharField("Название шаблона", max_length=120)
    waba_template_code = models.CharField("Код шаблона в WABA", max_length=100, unique=True)
    body = models.TextField("Текст шаблона (используйте {name} для имени)")
    is_approved = models.BooleanField("Одобрен платформой", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Шаблон WhatsApp"
        verbose_name_plural = "Шаблоны сообщений (Раздел 12)"

    def __str__(self):
        return self.name


class BroadcastLog(models.Model):
    """Журнал массовых и адресных коммуникаций (п. 12.4 ТЗ)"""
    class Status(models.TextChoices):
        QUEUED = 'queued', 'В очереди Outbox'
        SENT = 'sent', 'Отправлено'
        FAILED = 'failed', 'Ошибка доставки'
        SKIPPED_NO_CONSENT = 'skipped', 'Отклонено (нет согласия, п. 12.3)'

    template = models.ForeignKey(MessageTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='broadcasts')
    channel = models.CharField("Канал", max_length=20, default='WhatsApp')
    rendered_text = models.TextField("Сформированный текст")
    status = models.CharField("Результат (п. 12.4)", max_length=20, choices=Status.choices, default=Status.QUEUED)
    error_detail = models.CharField("Детали ошибки", max_length=255, blank=True)
    sent_at = models.DateTimeField("Дата и время отправки", auto_now_add=True)

    class Meta:
        verbose_name = "Запись рассылки"
        verbose_name_plural = "Журнал рассылок (Раздел 12)"
        ordering = ['-sent_at']