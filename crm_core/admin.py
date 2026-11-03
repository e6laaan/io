from django.contrib import admin
from .models import Patient, Ticket, TicketHistory, FollowUp, OutboxEvent, Campaign


class TicketHistoryInline(admin.TabularInline):
    model = TicketHistory
    extra = 1
    readonly_fields = ('created_at',)


class FollowUpInline(admin.StackedInline):
    model = FollowUp
    extra = 0


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ('name', 'source', 'utm_campaign', 'budget', 'is_active', 'created_at')
    list_filter = ('source', 'is_active')
    search_fields = ('name', 'utm_campaign')


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ('last_name', 'first_name', 'phone', 'whatsapp_consent', 'personal_data_consent', 'created_at')
    list_filter = ('whatsapp_consent', 'personal_data_consent', 'created_at')
    search_fields = ('last_name', 'first_name', 'phone')


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'patient', 'channel', 'status', 'result', 
        'rejection_reason', 'is_booked', 'revenue', 'campaign', 'created_at'
    )
    list_filter = (
        'status', 'channel', 'result', 'rejection_reason', 
        'is_booked', 'is_service_rendered', 'campaign'
    )
    search_fields = ('subject', 'patient__last_name', 'patient__phone', 'service_name')
    inlines = [TicketHistoryInline, FollowUpInline]
    date_hierarchy = 'created_at'


@admin.register(FollowUp)
class FollowUpAdmin(admin.ModelAdmin):
    list_display = ('patient', 'scheduled_at', 'reason', 'status', 'assigned_to')
    list_filter = ('status', 'scheduled_at')
    search_fields = ('patient__last_name', 'patient__phone', 'reason')


@admin.register(TicketHistory)
class TicketHistoryAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'author', 'created_at')
    search_fields = ('comment', 'ticket__patient__last_name')


@admin.register(OutboxEvent)
class OutboxEventAdmin(admin.ModelAdmin):
    list_display = ('id', 'target_system', 'event_type', 'status', 'retry_count', 'created_at')
    list_filter = ('status', 'target_system', 'created_at')