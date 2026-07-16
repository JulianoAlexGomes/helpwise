"""Testes do núcleo de horário comercial.

Quase todos sem banco: o Calendario é montado na mão. É de propósito — as regras
de expediente são a parte mais fácil de errar e a mais barata de testar isolada.

Calendário base: seg-sex, 08:00-12:00 e 13:00-18:00 (almoço de 1h).
"""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from tiqt.apps.core.services.sla import (
    Calendario, esta_no_expediente, minutos_uteis, prazo_a_partir_de,
    proxima_abertura, proximo_fechamento,
)

TZ = ZoneInfo('America/Sao_Paulo')
COMERCIAL = [(time(8, 0), time(12, 0)), (time(13, 0), time(18, 0))]


@pytest.fixture
def cal():
    return Calendario(faixas={d: COMERCIAL for d in range(5)}, tz=TZ)


@pytest.fixture
def cal_com_feriado():
    # 09/07/2026 é uma quinta-feira.
    return Calendario(faixas={d: COMERCIAL for d in range(5)},
                      feriados=frozenset({date(2026, 7, 9)}), tz=TZ)


def dt(ano, mes, dia, hora=0, minuto=0):
    return datetime(ano, mes, dia, hora, minuto, tzinfo=TZ)


# 2026-07-17 é sexta, 2026-07-18 sábado, 2026-07-20 segunda.

class TestMinutosUteis:
    def test_dentro_do_mesmo_periodo(self, cal):
        assert minutos_uteis(dt(2026, 7, 17, 9, 0), dt(2026, 7, 17, 10, 30), cal) == 90

    def test_atravessa_o_almoco(self, cal):
        # 11:30 -> 13:30 = 30min antes + 30min depois; a hora de almoço não conta.
        assert minutos_uteis(dt(2026, 7, 17, 11, 30), dt(2026, 7, 17, 13, 30), cal) == 60

    def test_fim_de_semana_nao_conta(self, cal):
        # sexta 18:05 -> segunda 07:55: tudo fora do expediente.
        assert minutos_uteis(dt(2026, 7, 17, 18, 5), dt(2026, 7, 20, 7, 55), cal) == 0

    def test_atravessa_o_fim_de_semana(self, cal):
        # sexta 17:30 -> segunda 08:30 = 30min de sexta + 30min de segunda.
        assert minutos_uteis(dt(2026, 7, 17, 17, 30), dt(2026, 7, 20, 8, 30), cal) == 60

    def test_dia_util_inteiro(self, cal):
        assert minutos_uteis(dt(2026, 7, 17, 0, 0), dt(2026, 7, 17, 23, 59), cal) == 540  # 9h

    def test_feriado_nao_conta(self, cal_com_feriado):
        # quinta feriado -> sexta 08:30: só os 30min da sexta.
        assert minutos_uteis(dt(2026, 7, 9, 8, 0), dt(2026, 7, 10, 8, 30), cal_com_feriado) == 30

    def test_feriado_recorrente_anual(self):
        cal = Calendario(faixas={d: COMERCIAL for d in range(5)},
                         fixos_anuais=frozenset({(12, 25)}), tz=TZ)
        # 25/12/2025 é quinta.
        assert minutos_uteis(dt(2025, 12, 25, 8, 0), dt(2025, 12, 25, 18, 0), cal) == 0

    def test_intervalo_nulo(self, cal):
        x = dt(2026, 7, 17, 10, 0)
        assert minutos_uteis(x, x, cal) == 0

    def test_fim_antes_do_inicio_nao_da_negativo(self, cal):
        assert minutos_uteis(dt(2026, 7, 17, 15, 0), dt(2026, 7, 17, 9, 0), cal) == 0

    def test_inicio_fora_do_expediente(self, cal):
        # sábado 10:00 -> segunda 08:30: só conta a partir de segunda 08:00.
        assert minutos_uteis(dt(2026, 7, 18, 10, 0), dt(2026, 7, 20, 8, 30), cal) == 30

    def test_aceita_utc(self, cal):
        # O contrato é datetime aware; UTC tem que dar o mesmo resultado.
        utc = ZoneInfo('UTC')
        ini = datetime(2026, 7, 17, 12, 0, tzinfo=utc)  # 09:00 em SP
        fim = datetime(2026, 7, 17, 13, 30, tzinfo=utc)  # 10:30 em SP
        assert minutos_uteis(ini, fim, cal) == 90


class TestPrazoAPartirDe:
    def test_sexta_1730_mais_60min_vira_segunda_0830(self, cal):
        assert prazo_a_partir_de(dt(2026, 7, 17, 17, 30), 60, cal) == dt(2026, 7, 20, 8, 30)

    def test_atravessa_o_almoco(self, cal):
        assert prazo_a_partir_de(dt(2026, 7, 17, 11, 30), 60, cal) == dt(2026, 7, 17, 13, 30)

    def test_inicio_fora_do_expediente_comeca_na_abertura(self, cal):
        # sábado 10:00 + 30min = segunda 08:30
        assert prazo_a_partir_de(dt(2026, 7, 18, 10, 0), 30, cal) == dt(2026, 7, 20, 8, 30)

    def test_zero_minutos(self, cal):
        assert prazo_a_partir_de(dt(2026, 7, 17, 9, 0), 0, cal) == dt(2026, 7, 17, 9, 0)

    def test_consome_o_dia_util_inteiro(self, cal):
        # O dia útil tem 9h = 540min: sexta 08:00 + 540 dá exatamente sexta 18:00.
        assert prazo_a_partir_de(dt(2026, 7, 17, 8, 0), 540, cal) == dt(2026, 7, 17, 18, 0)

    def test_transborda_para_o_proximo_dia_util(self, cal):
        # 541min = o dia útil inteiro + 1: transborda o fim de semana e cai na segunda.
        assert prazo_a_partir_de(dt(2026, 7, 17, 8, 0), 541, cal) == dt(2026, 7, 20, 8, 1)

    def test_sem_expediente_estoura_em_vez_de_travar(self):
        from django.core.exceptions import ImproperlyConfigured
        vazio = Calendario(faixas={}, tz=TZ)
        with pytest.raises(ImproperlyConfigured):
            prazo_a_partir_de(dt(2026, 7, 17, 9, 0), 60, vazio)


class TestIdaEVolta:
    """minutos_uteis e prazo_a_partir_de são inversos.

    Esta propriedade pega quase todo erro de fronteira sozinha.
    """

    @pytest.mark.parametrize('inicio', [
        dt(2026, 7, 17, 9, 0),    # sexta de manhã
        dt(2026, 7, 17, 11, 45),  # antes do almoço
        dt(2026, 7, 17, 17, 30),  # fim da sexta
        dt(2026, 7, 18, 10, 0),   # sábado (fora do expediente)
        dt(2026, 7, 20, 8, 0),    # abertura da segunda
    ])
    @pytest.mark.parametrize('minutos', [1, 30, 60, 480, 540, 1000])
    def test_ida_e_volta(self, cal, inicio, minutos):
        prazo = prazo_a_partir_de(inicio, minutos, cal)
        assert minutos_uteis(inicio, prazo, cal) == minutos


class TestExpediente:
    def test_esta_no_expediente(self, cal):
        assert esta_no_expediente(dt(2026, 7, 17, 9, 0), cal)
        assert not esta_no_expediente(dt(2026, 7, 17, 12, 30), cal)  # almoço
        assert not esta_no_expediente(dt(2026, 7, 18, 9, 0), cal)    # sábado
        assert not esta_no_expediente(dt(2026, 7, 17, 18, 0), cal)   # fronteira: fechado

    def test_proximo_fechamento(self, cal):
        assert proximo_fechamento(dt(2026, 7, 17, 9, 0), cal) == dt(2026, 7, 17, 12, 0)
        assert proximo_fechamento(dt(2026, 7, 17, 14, 0), cal) == dt(2026, 7, 17, 18, 0)
        assert proximo_fechamento(dt(2026, 7, 18, 9, 0), cal) is None  # sábado

    def test_proxima_abertura(self, cal):
        assert proxima_abertura(dt(2026, 7, 17, 12, 30), cal) == dt(2026, 7, 17, 13, 0)
        assert proxima_abertura(dt(2026, 7, 18, 9, 0), cal) == dt(2026, 7, 20, 8, 0)
        # já aberto: devolve o próprio instante
        agora = dt(2026, 7, 17, 9, 0)
        assert proxima_abertura(agora, cal) == agora
