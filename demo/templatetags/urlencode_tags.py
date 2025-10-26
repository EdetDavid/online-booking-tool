from django import template
from django.template.defaultfilters import stringfilter
from django.utils.safestring import mark_safe
import urllib.parse

register = template.Library()

@register.filter
@stringfilter
def urlencode(value):
    return mark_safe(urllib.parse.quote(value))
