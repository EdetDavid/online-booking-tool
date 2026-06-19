import logging

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.message import EmailMultiAlternatives
from django.core.exceptions import ImproperlyConfigured
from django.utils.html import escape
from django.utils.module_loading import import_string


logger = logging.getLogger(__name__)


class BrevoEmailBackend(BaseEmailBackend):
    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = getattr(settings, "BREVO_API_KEY", "")
        self.api_url = getattr(
            settings,
            "BREVO_API_URL",
            "https://api.brevo.com/v3/smtp/email",
        )

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        if not self.api_key:
            if self.fail_silently:
                return 0
            raise ImproperlyConfigured("BREVO_API_KEY is not configured.")

        sent_count = 0
        for message in email_messages:
            try:
                response = requests.post(
                    self.api_url,
                    headers={
                        "accept": "application/json",
                        "api-key": self.api_key,
                        "content-type": "application/json",
                    },
                    json=self._payload_for_message(message),
                    timeout=20,
                )
                response.raise_for_status()
                sent_count += 1
            except requests.HTTPError as error:
                logger.exception("Brevo email send failed: %s", error)
                fallback_sent = self._send_with_fallback(message)
                if fallback_sent:
                    sent_count += fallback_sent
                    continue
                if not self.fail_silently:
                    raise
            except requests.RequestException as error:
                logger.exception("Brevo email send failed: %s", error)
                if not self.fail_silently:
                    raise

        return sent_count

    def _send_with_fallback(self, message):
        backend_path = getattr(settings, "EMAIL_FALLBACK_BACKEND", "")
        if not backend_path or backend_path == (
            f"{self.__class__.__module__}.{self.__class__.__name__}"
        ):
            return 0

        try:
            fallback_backend = import_string(backend_path)(
                fail_silently=self.fail_silently,
            )
            sent_count = fallback_backend.send_messages([message])
            if sent_count:
                logger.warning(
                    "Email delivered through fallback backend %s after Brevo rejection.",
                    backend_path,
                )
            return sent_count
        except Exception as fallback_error:
            logger.exception(
                "Fallback email delivery through %s failed: %s",
                backend_path,
                fallback_error,
            )
            if not self.fail_silently:
                raise
            return 0

    def _payload_for_message(self, message):
        sender_email = getattr(settings, "BREVO_SENDER_EMAIL", "") or message.from_email
        sender_name = getattr(settings, "BREVO_SENDER_NAME", "Online Booking Tool")
        payload = {
            "sender": {"email": sender_email, "name": sender_name},
            "to": self._recipients(message.to),
            "subject": message.subject,
            "htmlContent": self._html_content(message),
            "textContent": message.body or "",
        }

        if message.cc:
            payload["cc"] = self._recipients(message.cc)
        if message.bcc:
            payload["bcc"] = self._recipients(message.bcc)
        if message.reply_to:
            payload["replyTo"] = {"email": message.reply_to[0]}

        return payload

    def _html_content(self, message):
        if isinstance(message, EmailMultiAlternatives):
            for content, mimetype in message.alternatives:
                if mimetype == "text/html":
                    return content
        if message.content_subtype == "html":
            return message.body or ""
        return f"<pre>{escape(message.body or '')}</pre>"

    def _recipients(self, emails):
        return [{"email": email} for email in emails if email]
