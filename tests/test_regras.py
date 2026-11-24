"""Cada regra: um caso que dispara e um que não dispara."""

import copy
from decimal import Decimal

import pytest

from nfe_conf.banco import ler_sql
from nfe_conf.modelo import arredondar
from nfe_conf.motor import aplicar_regras
from nfe_conf.regras import CATALOGO

from .conftest import _notas_limpas, rodar


@pytest.mark.parametrize("indice", range(9), ids=lambda i: f"fornecedor{i}")
def test_nota_limpa_nao_dispara_nenhuma_regra(indice, tabelas):
    nota = _notas_limpas()[indice]
    assert aplicar_regras([nota], tabelas) == []


def test_catalogo_completo():
    for regra in CATALOGO.values():
        assert regra.descricao and regra.como_corrigir
        if regra.escopo == "erp":
            assert ler_sql(regra.consulta_sql).strip()  # o .sql existe e não está vazio
        elif regra.escopo in {"nota", "item", "lote"}:
            assert callable(regra.funcao)


# ------------------------------------------------------------------ chave / cadastro


def test_chave_dv(nota_sp, tabelas):
    assert rodar("CHAVE_DV", nota_sp, tabelas) == []
    nota_sp.chave = nota_sp.chave[:-1] + str((int(nota_sp.chave[-1]) + 1) % 10)
    assert len(rodar("CHAVE_DV", nota_sp, tabelas)) == 1


def test_chave_campos(nota_sp, tabelas):
    assert rodar("CHAVE_CAMPOS", nota_sp, tabelas) == []
    nota_sp.numero += 1
    achados = rodar("CHAVE_CAMPOS", nota_sp, tabelas)
    assert [a.mensagem for a in achados] == ["número da chave diferente do XML"]


def test_cnpj_emitente(nota_sp, tabelas):
    assert rodar("CNPJ_EMITENTE_DV", nota_sp, tabelas) == []
    nota_sp.emit_cnpj = nota_sp.emit_cnpj[:-1] + str((int(nota_sp.emit_cnpj[-1]) + 1) % 10)
    assert len(rodar("CNPJ_EMITENTE_DV", nota_sp, tabelas)) == 1


@pytest.mark.parametrize("ncm", ["7318150", "77010000", "00000000", "9801000A"])
def test_ncm_invalido(nota_sp, tabelas, ncm):
    assert rodar("NCM_INVALIDO", nota_sp, tabelas) == []
    nota_sp.itens[0].ncm = ncm
    assert len(rodar("NCM_INVALIDO", nota_sp, tabelas)) == 1


# ------------------------------------------------------------------ CFOP


def test_cfop_interestadual_com_5xxx(nota_sp, tabelas):
    assert rodar("CFOP_OPERACAO", nota_sp, tabelas) == []
    nota_sp.itens[0].cfop = "5" + nota_sp.itens[0].cfop[1:]
    [achado] = rodar("CFOP_OPERACAO", nota_sp, tabelas)
    assert achado.esperado == "6xxx"


def test_cfop_interna_com_6xxx(nota_go, tabelas):
    assert rodar("CFOP_OPERACAO", nota_go, tabelas) == []
    nota_go.itens[0].cfop = "6102"
    [achado] = rodar("CFOP_OPERACAO", nota_go, tabelas)
    assert achado.esperado == "5xxx"


def test_cfop_de_entrada_na_nota_do_fornecedor(nota_go, tabelas):
    nota_go.itens[0].cfop = "1102"
    assert len(rodar("CFOP_OPERACAO", nota_go, tabelas)) == 1


# ------------------------------------------------------------------ ICMS


@pytest.mark.parametrize(
    ("origem", "aliquota_errada", "esperada"),
    [("0", "12", "7.00%"), ("1", "12", "4.00%"), ("0", "4", "7.00%")],
)
def test_icms_aliquota_interestadual(nota_sp, tabelas, origem, aliquota_errada, esperada):
    item = nota_sp.itens[0]
    item.icms_origem = origem
    item.icms_aliquota = tabelas.aliquota_icms_interestadual("SP", "GO", origem)
    assert rodar("ICMS_ALIQ_INTERESTADUAL", nota_sp, tabelas) == []
    item.icms_aliquota = Decimal(aliquota_errada)
    [achado] = rodar("ICMS_ALIQ_INTERESTADUAL", nota_sp, tabelas)
    assert achado.esperado == esperada


def test_icms_aliquota_nao_vale_para_operacao_interna(nota_go, tabelas):
    for item in nota_go.itens:
        item.icms_aliquota = Decimal("12")
    assert rodar("ICMS_ALIQ_INTERESTADUAL", nota_go, tabelas) == []


def test_icms_base(nota_sp, tabelas):
    assert rodar("ICMS_BASE", nota_sp, tabelas) == []
    nota_sp.itens[0].icms_base += Decimal("10.00")
    assert len(rodar("ICMS_BASE", nota_sp, tabelas)) == 1


def test_icms_base_respeita_reducao_do_cst20(notas_limpas, tabelas):
    nota_pr = notas_limpas[2]
    item = nota_pr.itens[0]
    assert item.icms_cst == "20" and item.icms_reducao_base == Decimal("20")
    assert rodar("ICMS_BASE", nota_pr, tabelas) == []
    item.icms_base = item.valor_produto - item.valor_desconto  # esqueceu a redução
    assert len(rodar("ICMS_BASE", nota_pr, tabelas)) == 1


def test_icms_valor(nota_sp, tabelas):
    assert rodar("ICMS_VALOR", nota_sp, tabelas) == []
    nota_sp.itens[0].icms_valor += Decimal("0.05")
    assert len(rodar("ICMS_VALOR", nota_sp, tabelas)) == 1


def test_icms_valor_tolera_um_centavo(nota_sp, tabelas):
    nota_sp.itens[0].icms_valor += Decimal("0.01")
    assert rodar("ICMS_VALOR", nota_sp, tabelas) == []


def test_icms_regime(nota_simples, nota_sp, tabelas):
    assert rodar("ICMS_REGIME", nota_simples, tabelas) == []
    assert rodar("ICMS_REGIME", nota_sp, tabelas) == []
    nota_simples.itens[0].icms_cst = "00"  # Simples usando CST de regime normal
    assert len(rodar("ICMS_REGIME", nota_simples, tabelas)) == 1
    nota_sp.emit_crt = "1"
    assert len(rodar("ICMS_REGIME", nota_sp, tabelas)) == len(nota_sp.itens)


# ------------------------------------------------------------------ IPI / PIS / COFINS


def test_ipi_valor(nota_sp, tabelas):
    item = nota_sp.itens[0]
    assert item.ipi_aliquota > 0
    assert rodar("IPI_VALOR", nota_sp, tabelas) == []
    item.ipi_valor = arredondar(item.ipi_valor * 2)
    assert len(rodar("IPI_VALOR", nota_sp, tabelas)) == 1


@pytest.mark.parametrize(("pis", "cofins"), [("1.65", "3.00"), ("0.65", "7.60"), ("2", "9")])
def test_pis_cofins_aliquota(nota_sp, tabelas, pis, cofins):
    assert rodar("PIS_COFINS_ALIQUOTA", nota_sp, tabelas) == []
    nota_sp.itens[0].pis_aliquota = Decimal(pis)
    nota_sp.itens[0].cofins_aliquota = Decimal(cofins)
    assert len(rodar("PIS_COFINS_ALIQUOTA", nota_sp, tabelas)) == 1


def test_pis_cofins_aliquota_ignora_simples(nota_simples, tabelas):
    assert nota_simples.itens[0].pis_cst == "99"
    assert rodar("PIS_COFINS_ALIQUOTA", nota_simples, tabelas) == []


def test_pis_cofins_valor(nota_sp, tabelas):
    assert rodar("PIS_COFINS_VALOR", nota_sp, tabelas) == []
    nota_sp.itens[0].cofins_valor += Decimal("1.00")
    [achado] = rodar("PIS_COFINS_VALOR", nota_sp, tabelas)
    assert "COFINS" in achado.mensagem


# ------------------------------------------------------------------ totais e lote


def test_total_nota(nota_sp, tabelas):
    assert rodar("TOTAL_NOTA", nota_sp, tabelas) == []
    nota_sp.totais.valor_nota += Decimal("150.00")
    [achado] = rodar("TOTAL_NOTA", nota_sp, tabelas)
    assert "vNF" in achado.mensagem and "vProd" not in achado.mensagem


def test_total_nota_aponta_varios_campos(nota_sp, tabelas):
    nota_sp.totais.valor_produtos += Decimal("150.00")
    nota_sp.totais.valor_nota += Decimal("150.00")
    [achado] = rodar("TOTAL_NOTA", nota_sp, tabelas)
    assert "vProd" in achado.mensagem and "vNF" in achado.mensagem


def test_nota_duplicada(nota_sp, nota_go, tabelas):
    funcao = CATALOGO["NOTA_DUPLICADA"].funcao
    assert list(funcao([nota_sp, nota_go], tabelas)) == []
    copia = copy.deepcopy(nota_sp)
    copia.arquivo = "copia.xml"
    [(nota, achado)] = list(funcao([nota_sp, nota_go, copia], tabelas))
    assert nota.arquivo == "copia.xml" and nota_sp.arquivo in achado.mensagem


def test_copia_nao_duplica_as_demais_divergencias(nota_sp, tabelas):
    nota_sp.itens[0].ncm = "123"
    copia = copy.deepcopy(nota_sp)
    copia.arquivo = "copia.xml"
    codigos = sorted(d.codigo for d in aplicar_regras([nota_sp, copia], tabelas))
    assert codigos == ["NCM_INVALIDO", "NOTA_DUPLICADA"]
