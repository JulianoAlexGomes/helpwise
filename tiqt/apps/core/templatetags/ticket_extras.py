import os
from django import template

register = template.Library()

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg', '.heic'}


def _name(value):
    return value.name if hasattr(value, 'name') else str(value)


@register.filter
def basename(value):
    """Retorna apenas o nome do arquivo (sem o caminho)."""
    try:
        return os.path.basename(_name(value))
    except Exception:
        return value


@register.simple_tag(takes_context=True)
def url_replace(context, **kwargs):
    """Mantém os parâmetros GET atuais, trocando/adicionando os informados.
    Ex.: ?{% url_replace page=3 %}"""
    request = context.get('request')
    query = request.GET.copy() if request else None
    if query is None:
        return ''
    for key, value in kwargs.items():
        query[key] = value
    return query.urlencode()


@register.filter
def is_image(value):
    """True se o arquivo for uma imagem (pela extensão)."""
    try:
        return os.path.splitext(_name(value))[1].lower() in IMAGE_EXTS
    except Exception:
        return False


@register.filter
def traco_se_vazio(value):
    """None/'' viram travessão. Célula vazia em relatório parece erro de geração."""
    if value is None or value == '':
        return '—'
    return value
