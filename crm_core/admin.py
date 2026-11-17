from django.contrib import admin
from .models import (
    Patient, Ticket, TicketHistory, FollowUp, OutboxEvent,
    Campaign, TicketStatus, RejectionReason, CallLog, WhatsAppMessage,
    MessageTemplate, BroadcastLog
)


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'source', 'promoted_service', 'start_date', 'end_date', 'budget', 'actual_spend', 'is_active')
    list_filter = ('is_active', 'source')
    search_fields = ('code', 'name', 'utm_campaign', 'promoted_service')


@admin.register(TicketStatus)
class TicketStatusAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_final', 'order')
    list_editable = ('order', 'is_final')


@admin.register(RejectionReason)
class RejectionReasonAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active')
    list_editable = ('is_active',)


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ('last_name', 'first_name', 'iin', 'phone', 'whatsapp_consent', 'consent_source', 'created_at')
    list_filter = ('whatsapp_consent', 'consent_source')
    search_fields = ('last_name', 'first_name', 'iin', 'phone', 'external_id')


class TicketHistoryInline(admin.TabularInline):
    model = TicketHistory
    extra = 0
    readonly_fields = ('author', 'comment', 'created_at')


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('id', 'subject', 'patient', 'raw_contact', 'channel', 'lead_source', 'campaign', 'status', 'is_booked', 'revenue', 'created_at')
    list_filter = ('status', 'channel', 'is_booked', 'campaign')
    search_fields = ('subject', 'raw_contact', 'patient__last_name', 'patient__phone')
    inlines = [TicketHistoryInline]


@admin.register(FollowUp)
class FollowUpAdmin(admin.ModelAdmin):
    list_display = ('id', 'patient', 'ticket', 'assigned_to', 'scheduled_at', 'status')
    list_filter = ('status', 'assigned_to')


@admin.register(OutboxEvent)
class OutboxEventAdmin(admin.ModelAdmin):
    list_display = ('id', 'target_system', 'event_type', 'status', 'retry_count', 'created_at')
    list_filter = ('status', 'target_system')


@admin.register(CallLog)
class CallLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'direction', 'phone', 'extension', 'duration', 'is_missed', 'processing_status', 'started_at')
    list_filter = ('direction', 'is_missed', 'processing_status')
    search_fields = ('phone', 'call_id')


@admin.register(WhatsAppMessage)
class WhatsAppMessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'ticket', 'direction', 'sender_phone', 'author', 'created_at')
    list_filter = ('direction',)
    search_fields = ('sender_phone', 'message_text')


@admin.register(MessageTemplate)
class MessageTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'waba_template_code', 'is_approved', 'created_at')
    list_filter = ('is_approved',)


@admin.register(BroadcastLog)
class BroadcastLogAdmin(admin.ModelAdmin):
    list_display = ('sent_at', 'patient', 'template', 'channel', 'status')
    list_filter = ('status', 'channel')