"""SMTP adapter with explicit unavailable/unknown outcomes; no noop delivery."""
import asyncio
import json
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from app.core.config import get_settings

@dataclass(frozen=True)
class DeliveryOutcome:
    state: str
    error_code: str | None = None

def readiness():
    settings=get_settings()
    if settings.environment=="development" and settings.dev_inbox:
        return {"channel":"email","state":"development_only","reason":"Письма доступны только в локальном dev-inbox"}
    if not settings.smtp_host or not settings.smtp_from:
        return {"channel":"email","state":"unavailable","reason":"Почтовый провайдер не настроен"}
    return {"channel":"email","state":"available","reason":"SMTP настроен; состояние доставки фиксируется по фактическому ответу сервера"}

async def deliver_email(payload):
    settings=get_settings()
    if settings.environment=="development" and settings.dev_inbox:
        return DeliveryOutcome("dev_inbox")
    if not settings.smtp_host or not settings.smtp_from:
        return DeliveryOutcome("unavailable","provider_unavailable")
    if payload.get('purpose')!='login' or not all(payload.get(k) for k in ('to','challenge_id','token')):
        return DeliveryOutcome("unavailable","template_unavailable")
    email=EmailMessage()
    email['From']=settings.smtp_from
    email['To']=payload['to']
    email['Subject']='Опора — подтверждение входа'
    # Token consumption remains POST-only, never through a GET link.
    email.set_content(f"Код подтверждения входа в Опору:\n{payload['token']}\n\nЗапрос: {payload['challenge_id']}\nКод действует 15 минут. Если вы не запрашивали вход, не используйте его.")
    def send():
        client=None
        attempted_data=False
        try:
            client=smtplib.SMTP(settings.smtp_host,settings.smtp_port,timeout=10)
            client.ehlo()
            if settings.smtp_starttls:
                client.starttls(context=ssl.create_default_context())
                client.ehlo()
            if settings.smtp_username:
                client.login(settings.smtp_username,settings.smtp_password or '')
            attempted_data=True
            refused=client.send_message(email)
            return DeliveryOutcome("rejected","recipient_rejected") if refused else DeliveryOutcome("delivered")
        except (smtplib.SMTPRecipientsRefused,smtplib.SMTPSenderRefused,smtplib.SMTPDataError):
            return DeliveryOutcome("rejected","smtp_rejected")
        except (OSError,smtplib.SMTPException):
            return DeliveryOutcome("unknown" if attempted_data else "unavailable","smtp_unknown" if attempted_data else "smtp_unavailable")
        finally:
            if client is not None:
                try:
                    client.close()
                except OSError:
                    pass
    return await asyncio.to_thread(send)
