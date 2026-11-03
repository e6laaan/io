from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Campaign(models.Model):
    name = models.CharField("Название кампании", max_length=150)
    source = models.CharField("Источник", max_length=100)
    utm_campaign = models.CharField("UTM метка", max_length=100, unique=True)
    budget = models.DecimalField("Бюджет", max_digits=12, decimal_places=2, default=0.00)
    is_active = models.BooleanField("Активна", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Рекламная кампания"
        verbose_name_plural = "Рекламные кампании"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.source})"


class TicketStatus(models.Model):
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

    channel = models.CharField("Канал", max_length=30, choices=Channel.choices, default=Channel.INBOUND_CALL)
    subject = models.CharField("Тема / направление", max_length=255)
    description = models.TextField("Содержание обращения", blank=True)
    result = models.CharField("Результат", max_length=100, blank=True)
    next_contact_date = models.DateTimeField("Дата следующего контакта", null=True, blank=True)

    utm_source = models.CharField(max_length=100, blank=True)
    utm_medium = models.CharField(max_length=100, blank=True)
    utm_campaign = models.CharField(max_length=100, blank=True)

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