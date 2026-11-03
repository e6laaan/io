from django.contrib import admin
from django.urls import path, include
from crm_core.views import dashboard_view, patient_card_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api-auth/', include('rest_framework.urls')),
    
    # Прямые ссылки на интерфейс дашборда и карточку пациента
    path('', dashboard_view, name='home'),
    path('patient/<int:patient_id>/', patient_card_view, name='patient-card-root'),
    
    # API эндпоинты
    path('api/', include('crm_core.urls')),
]