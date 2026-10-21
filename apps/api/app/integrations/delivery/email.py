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
    purpose=payload.get('purpose')
    from app.integrations.delivery.registry import email_purpose
    policy=email_purpose(purpose) if purpose not in ('login','contact_change','register','password_reset','notification') else None
    if (purpose not in ('login','contact_change','register','password_reset','notification') and policy is None) or not payload.get('to') or any(c in payload['to'] for c in ('\r','\n')):
        return DeliveryOutcome("unavailable","template_unavailable")
    email=EmailMessage()
    email['From']=settings.smtp_from
    email['To']=payload['to']
    if payload.get('message_id'):
        email['Message-ID']=payload['message_id']
    if purpose in ('register','password_reset'):
        code=payload.get('code','')
        if len(code)!=6 or not code.isascii() or not code.isdigit() or not payload.get('challenge_id'):
            return DeliveryOutcome('unavailable','template_unavailable')
        email['Subject']='Опора — подтверждение почты' if purpose=='register' else 'Опора — восстановление пароля'
        email.set_content(f"Код подтверждения: {code}\n\nКод действует 10 минут. Если вы не запрашивали это действие, проигнорируйте письмо.")
    elif purpose in ('login','contact_change'):
        if not all(payload.get(k) for k in ('challenge_id','token')):
            return DeliveryOutcome('unavailable','template_unavailable')
        email['Subject']='Опора — подтверждение смены почты' if purpose=='contact_change' else 'Опора — подтверждение входа'
        email.set_content(f"Код подтверждения запроса в Опоре:\n{payload['token']}\n\nЗапрос: {payload['challenge_id']}\nКод действует 15 минут. Если вы не запрашивали вход, не используйте его.")
    else:
        if policy:
            subject,body=policy.render(payload)
            payload={**payload,'subject':subject,'text':body}
        if not payload.get('subject') or not payload.get('text') or len(payload['subject'])>300 or len(payload['text'])>10000 or any(c in payload['subject'] for c in ('\r','\n')):
            return DeliveryOutcome('unavailable','template_unavailable')
        email['Subject']=payload['subject']
        email.set_content(payload['text'])
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
            return DeliveryOutcome("rejected","recipient_rejected") if refused else DeliveryOutcome("accepted")
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
