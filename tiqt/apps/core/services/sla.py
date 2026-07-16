"""Cálculo de SLA em horário comercial.

O núcleo aqui é puro: recebe um `Calendario` como argumento e não toca no banco.
`carregar_calendario()` é a única função que faz query — assim as regras de
expediente/feriado são testáveis sem banco e sem fixture.

Contrato de timezone: todas as funções recebem e devolvem datetime *aware*.
Internamente convertemos para o fuso local (America/Sao_Paulo) porque os
TimeField de Expediente são naive e só fazem sentido no horário da parede.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

# Sem expediente cadastrado, procurar "o próximo dia útil" nunca termina.
# 400 dias cobre qualquer meta realista e ainda estoura antes de travar o worker.
_MAX_DIAS = 400

CACHE_KEY = 'sla:calendario'
CACHE_TTL = 300


@dataclass(frozen=True)
class Calendario:
    """Expediente + feriados, num formato que o núcleo consome sem tocar no banco.

    faixas: {dia_semana (0=segunda): [(hora_inicio, hora_fim), ...]} já ordenado.
             Várias faixas no mesmo dia = intervalo de almoço.
    feriados: datas específicas que não contam.
    fixos_anuais: (mês, dia) que não contam em nenhum ano — Natal, Tiradentes...
                  Feriado móvel (Carnaval, Páscoa) se cadastra ano a ano em `feriados`.
    """

    faixas: dict
    feriados: frozenset = frozenset()
    fixos_anuais: frozenset = frozenset()
    tz: ZoneInfo = None

    def __post_init__(self):
        if self.tz is None:
            object.__setattr__(self, 'tz', ZoneInfo(settings.TIME_ZONE))

    def e_dia_util(self, dia: date) -> bool:
        if dia in self.feriados or (dia.month, dia.day) in self.fixos_anuais:
            return False
        return bool(self.faixas.get(dia.weekday()))

    def faixas_do_dia(self, dia: date) -> list:
        if not self.e_dia_util(dia):
            return []
        return self.faixas.get(dia.weekday(), [])


def _aware(dia: date, hora: time, cal: Calendario) -> datetime:
    """Monta um datetime aware no fuso do calendário.

    Sempre via `combine` + `replace(tzinfo=...)`, nunca somando timedelta a um
    naive e convertendo depois: o backfill processa tickets de 2018, quando o
    Brasil ainda tinha horário de verão, e existem horas que simplesmente não
    aconteceram (04/11/2018 00:00). O zoneinfo resolve essas com fold=0.
    """
    return datetime.combine(dia, hora).replace(tzinfo=cal.tz)


def _local(dt: datetime, cal: Calendario) -> datetime:
    return dt.astimezone(cal.tz)


def esta_no_expediente(dt: datetime, cal: Calendario) -> bool:
    loc = _local(dt, cal)
    for inicio, fim in cal.faixas_do_dia(loc.date()):
        if _aware(loc.date(), inicio, cal) <= dt < _aware(loc.date(), fim, cal):
            return True
    return False


def proxima_abertura(dt: datetime, cal: Calendario) -> datetime:
    """Quando o expediente volta a correr. Devolve o próprio `dt` se já está aberto."""
    loc = _local(dt, cal)
    dia = loc.date()
    for _ in range(_MAX_DIAS):
        for inicio, fim in cal.faixas_do_dia(dia):
            ini_dt = _aware(dia, inicio, cal)
            fim_dt = _aware(dia, fim, cal)
            if dt < ini_dt:
                return ini_dt
            if ini_dt <= dt < fim_dt:
                return dt
        dia += timedelta(days=1)
    raise ImproperlyConfigured(
        'Nenhum expediente ativo cadastrado — cadastre ao menos uma faixa em Expediente.'
    )


def proximo_fechamento(dt: datetime, cal: Calendario):
    """Fim da faixa de expediente que está correndo agora, ou None se está fechado."""
    loc = _local(dt, cal)
    for inicio, fim in cal.faixas_do_dia(loc.date()):
        ini_dt = _aware(loc.date(), inicio, cal)
        fim_dt = _aware(loc.date(), fim, cal)
        if ini_dt <= dt < fim_dt:
            return fim_dt
    return None


def minutos_uteis(inicio: datetime, fim: datetime, cal: Calendario) -> int:
    """Minutos de expediente entre dois instantes. Nunca negativo."""
    if fim <= inicio:
        return 0

    total = timedelta()
    dia = _local(inicio, cal).date()
    ultimo_dia = _local(fim, cal).date()

    while dia <= ultimo_dia:
        for f_ini, f_fim in cal.faixas_do_dia(dia):
            faixa_ini = _aware(dia, f_ini, cal)
            faixa_fim = _aware(dia, f_fim, cal)
            # interseção entre [inicio, fim] e a faixa
            ini = max(inicio, faixa_ini)
            f = min(fim, faixa_fim)
            if f > ini:
                total += f - ini
        dia += timedelta(days=1)

    return int(total.total_seconds() // 60)


def prazo_a_partir_de(inicio: datetime, minutos: int, cal: Calendario) -> datetime:
    """O instante em que `minutos` de expediente terão se passado desde `inicio`.

    Inverso de minutos_uteis: minutos_uteis(t, prazo_a_partir_de(t, n)) == n.
    """
    restante = timedelta(minutes=minutos)
    atual = proxima_abertura(inicio, cal)
    if restante <= timedelta():
        return atual

    dia = _local(atual, cal).date()
    for _ in range(_MAX_DIAS):
        for f_ini, f_fim in cal.faixas_do_dia(dia):
            faixa_ini = _aware(dia, f_ini, cal)
            faixa_fim = _aware(dia, f_fim, cal)
            ini = max(atual, faixa_ini)
            if faixa_fim <= ini:
                continue
            disponivel = faixa_fim - ini
            if disponivel >= restante:
                return ini + restante
            restante -= disponivel
        dia += timedelta(days=1)

    raise ImproperlyConfigured(
        'Nenhum expediente ativo cadastrado — cadastre ao menos uma faixa em Expediente.'
    )


def _montar_calendario() -> Calendario:
    from tiqt.apps.core.models import Expediente, Feriado

    faixas = {}
    for exp in Expediente.objects.filter(ativo=True).order_by('dia_semana', 'hora_inicio'):
        faixas.setdefault(exp.dia_semana, []).append((exp.hora_inicio, exp.hora_fim))

    feriados, fixos = set(), set()
    for fer in Feriado.objects.all():
        if fer.recorrente_anual:
            fixos.add((fer.data.month, fer.data.day))
        else:
            feriados.add(fer.data)

    return Calendario(
        faixas=faixas,
        feriados=frozenset(feriados),
        fixos_anuais=frozenset(fixos),
        tz=ZoneInfo(settings.TIME_ZONE),
    )


def carregar_calendario() -> Calendario:
    """Calendário do banco, cacheado por 5 min.

    Cache (e não lru_cache) de propósito: num processo WSGI longo, um feriado
    recém-cadastrado nunca entraria em lru_cache.
    """
    cal = cache.get(CACHE_KEY)
    if cal is None:
        cal = _montar_calendario()
        cache.set(CACHE_KEY, cal, CACHE_TTL)
    return cal


def invalidar_calendario():
    cache.delete(CACHE_KEY)


def politica_para(ticket):
    """A SlaPolitica mais específica que serve a este ticket, ou None.

    Especificidade: (depto, prio) > (—, prio) > (depto, —) > (—, —).
    Sem política, o ticket é "sem SLA": aparece neutro no painel, nunca vermelho.
    Meta inventada por default silencioso é pior que meta ausente.
    """
    from django.db.models import Case, IntegerField, Q, When

    from tiqt.apps.core.models import SlaPolitica

    return (
        SlaPolitica.objects.filter(ativo=True)
        .filter(Q(departamento_id=ticket.departamento_id) | Q(departamento__isnull=True))
        .filter(Q(prioridade_id=ticket.prioridade_id) | Q(prioridade__isnull=True))
        .annotate(
            score=Case(When(departamento__isnull=False, then=2), default=0, output_field=IntegerField())
            + Case(When(prioridade__isnull=False, then=1), default=0, output_field=IntegerField())
        )
        .order_by('-score')
        .first()
    )
