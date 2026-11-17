import logging
from .models import OutboxEvent

logger = logging.getLogger(__name__)


class IntegrationService:
    """Сервис отправки данных во внешние системы"""

    @staticmethod
    def emit_event(target_system: str, event_type: str, payload: dict) -> OutboxEvent:
        """Регистрирует событие в Outbox и пробует безопасно отправить его"""
        event = OutboxEvent.objects.create(
            target_system=target_system,
            event_type=event_type,
            payload=payload,
            status=OutboxEvent.Status.PENDING
        )
        # Пробуем отправить синхронно (в продакшене переводится на Celery/RQ)
        IntegrationService.dispatch(event)
        return event

    @staticmethod
    def dispatch(event: OutboxEvent):
        """
        Безопасная отправка: при любых сетевых ошибках или сбоях API
        основная логика CRM НЕ падает (п. 1.4 ТЗ).
        """
        try:
            # Имитация вызова внешнего API
            # В будущем здесь будет реальный HTTP-клиент (requests / httpx)
            logger.info(f"Отправка события {event.id} в систему '{event.target_system}'...")
            
            # Фейковая успешная доставка (нативная заглушка)
            event.status = OutboxEvent.Status.SENT
            event.save(update_fields=['status', 'updated_at'])
        except Exception as exc:
            logger.warning(f"Ошибка связи с {event.target_system}: {exc}")
            event.status = OutboxEvent.Status.FAILED
            event.retry_count += 1
            event.last_error = str(exc)
            event.save(update_fields=['status', 'retry_count', 'last_error', 'updated_at'])