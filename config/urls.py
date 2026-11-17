from django.contrib import admin
from django.urls import path, include
from crm_core.views import dashboard_view, patient_card_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('', dashboard_view, name='home'),
    path('patient/<int:patient_id>/', patient_card_view, name='patient-detail'),
    path('api/', include('crm_core.urls')),
]