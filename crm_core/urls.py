from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    PatientViewSet,
    TicketViewSet,
    FollowUpViewSet,
    AnalyticsSummaryView,
    ExportAnalyticsCSVView,
    dashboard_view,
    patient_card_view,
)
from .views_integration import (
    WebsiteLeadWebhookView,
    MissedCallWebhookView,
    ProcessOutboxQueueView,
)

router = DefaultRouter()
router.register(r'patients', PatientViewSet, basename='patient')
router.register(r'tickets', TicketViewSet, basename='ticket')
router.register(r'follow-ups', FollowUpViewSet, basename='followup')

urlpatterns = [
    path('', dashboard_view, name='crm-dashboard'),
    path('patient/<int:patient_id>/', patient_card_view, name='patient-card'),
    path('analytics/summary/', AnalyticsSummaryView.as_view(), name='analytics-summary'),
    path('analytics/export-csv/', ExportAnalyticsCSVView.as_view(), name='export-analytics-csv'),
    path('integrations/webhooks/website-lead/', WebsiteLeadWebhookView.as_view(), name='webhook-lead'),
    path('integrations/webhooks/missed-call/', MissedCallWebhookView.as_view(), name='webhook-missed-call'),
    path('integrations/outbox/process/', ProcessOutboxQueueView.as_view(), name='process-outbox'),
    path('', include(router.urls)),
]