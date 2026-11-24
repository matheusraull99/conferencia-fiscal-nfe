from __future__ import annotations

import random

import pytest

from nfe_conf import gerador
from nfe_conf.modelo import Nota
from nfe_conf.parser import ler_nota
from nfe_conf.regras import CATALOGO, Achado
from nfe_conf.tabelas import Tabelas, carregar_tabelas


@pytest.fixture(scope="session")
def tabelas() -> Tabelas:
    return carregar_tabelas()


def _notas_limpas() -> list[Nota]:
    """Uma nota limpa por fornecedor fictício, já passada por XML -> parser (ida e volta)."""
    lote = gerador._montar_notas(random.Random(7), 9)
    return [
        ler_nota(
            gerador.nota_para_xml(n, lote.emitentes[n.emit_cnpj], lote.destinatario,
                                  lote.unidades),
            arquivo=n.arquivo,
        )
        for n in lote.notas
    ]


@pytest.fixture
def notas_limpas() -> list[Nota]:
    return _notas_limpas()


@pytest.fixture
def nota_sp(notas_limpas) -> Nota:
    """Metalúrgica (SP, regime normal, não cumulativo) vendendo para GO: alíquota 7%."""
    return notas_limpas[0]


@pytest.fixture
def nota_go(notas_limpas) -> Nota:
    """Atacadista (GO) vendendo para GO: operação interna."""
    return notas_limpas[6]


@pytest.fixture
def nota_simples(notas_limpas) -> Nota:
    """Papelaria (SP, Simples Nacional, CSOSN 102)."""
    return notas_limpas[7]


def rodar(codigo: str, nota: Nota, tabelas: Tabelas) -> list[Achado]:
    """Executa uma única regra do catálogo numa nota (respeitando o escopo)."""
    regra = CATALOGO[codigo]
    if regra.escopo == "nota":
        return list(regra.funcao(nota, tabelas))
    if regra.escopo == "item":
        return [a for item in nota.itens for a in regra.funcao(item, nota, tabelas)]
    raise ValueError(f"Use a função de lote diretamente para {codigo}")
