import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from .models import Admin, Staff, TravelAgency

logger = logging.getLogger(__name__)


ROLE_MODELS = {
    "admin": (Admin, "admin", {"approval_status": True}),
    "staff": (Staff, "staff", {}),
    "travel_agency": (TravelAgency, "admin", {"approval_status": True}),
}


def unique_emails(emails):
    seen = set()
    cleaned = []
    for email in emails:
        normalized = (email or "").strip()
        key = normalized.lower()
        if normalized and key not in seen:
            cleaned.append(normalized)
            seen.add(key)
    return cleaned


def role_recipients(roles, include_unapproved=False, include_fallback=True):
    if isinstance(roles, str):
        roles = [roles]

    emails = []
    configured_recipients = getattr(settings, "ROLE_EMAIL_RECIPIENTS", {})

    for role in roles:
        role_key = str(role).strip().lower()
        manual_emails = configured_recipients.get(role_key)
        if manual_emails:
            emails.extend(manual_emails)
            continue

        model_config = ROLE_MODELS.get(role_key)
        if not model_config:
            logger.warning("Unknown email role requested: %s", role)
            continue

        model, user_field, required_filters = model_config
        filters = {
            f"{user_field}__is_active": True,
            f"{user_field}__email__isnull": False,
        }
        if not include_unapproved:
            filters.update(required_filters)

        emails.extend(
            model.objects.select_related(user_field)
            .filter(**filters)
            .exclude(**{f"{user_field}__email": ""})
            .values_list(f"{user_field}__email", flat=True)
        )

    recipients = unique_emails(emails)
    if not recipients and include_fallback:
        recipients = unique_emails(getattr(settings, "ROLE_EMAIL_FALLBACK_RECIPIENTS", []))
    return recipients


def user_recipients(*users):
    return unique_emails(getattr(user, "email", "") for user in users if user)


def send_html_email(subject, template_name, context, recipients):
    recipients = unique_emails(recipients)
    if not recipients:
        logger.warning("Skipped email '%s' because no recipients were found.", subject)
        return 0

    html_content = render_to_string(template_name, context)
    text_content = strip_tags(html_content)
    email = EmailMultiAlternatives(
        subject,
        text_content,
        settings.EMAIL_HOST_USER,
        recipients,
    )
    email.attach_alternative(html_content, "text/html")
    return email.send(fail_silently=False)


def send_html_email_to_roles(subject, template_name, context, roles, include_fallback=True):
    return send_html_email(
        subject,
        template_name,
        context,
        role_recipients(roles, include_fallback=include_fallback),
    )


def send_html_email_to_users(subject, template_name, context, *users):
    return send_html_email(
        subject,
        template_name,
        context,
        user_recipients(*users),
    )
