"""Gera o lote fictício, roda a conferência e compara com o gabarito do gerador."""

import json
from collections import Counter

import pytest
from openpyxl import load_workbook

from nfe_conf.cli import main
from nfe_conf.gerador import gerar_lote, salvar_lote
from nfe_conf.motor import conferir


@pytest.fixture(scope="module")
def lote_em_disco(tmp_path_factory):
    destino = tmp_path_factory.mktemp("lote")
    caminhos = salvar_lote(gerar_lote(), destino)
    return caminhos


def test_lote_tem_60_xmls_e_gabarito(lote_em_disco):
    assert len(list(lote_em_disco["xml"].glob("*.xml"))) == 60
    gabarito = json.loads(lote_em_disco["gabarito"].read_text(encoding="utf-8"))
    codigos = {d["codigo"] for d in gabarito["divergencias"]}
    assert {"ICMS_BASE", "ICMS_ALIQ_INTERESTADUAL", "CFOP_OPERACAO", "TOTAL_NOTA",
            "PIS_COFINS_ALIQUOTA", "NCM_INVALIDO", "NOTA_DUPLICADA", "CHAVE_DV",
            "ERP_NAO_LANCADA", "ERP_DUPLICIDADE", "ERP_VALOR_DIVERGENTE",
            "ERP_SEM_XML"} <= codigos


def test_motor_acha_exatamente_o_que_foi_plantado(lote_em_disco):
    """Recall e precisão de 100%: nem divergência perdida, nem falso positivo."""
    resultado = conferir(lote_em_disco["xml"], lote_em_disco["erp"])
    gabarito = json.loads(lote_em_disco["gabarito"].read_text(encoding="utf-8"))
    esperado = Counter(
        (d["codigo"], d["emit_cnpj"], d["numero"], d["serie"]) for d in gabarito["divergencias"]
    )
    encontrado = Counter(
        (d.codigo, d.emit_cnpj, d.numero, d.serie) for d in resultado.divergencias
    )
    assert encontrado == esperado


def test_xml_ilegivel_vira_divergencia(tmp_path, lote_em_disco):
    pasta = tmp_path / "xml"
    pasta.mkdir()
    (pasta / "quebrado.xml").write_text("<nfeProc>", encoding="utf-8")
    resultado = conferir(pasta, lote_em_disco["erp"])
    assert [d.codigo for d in resultado.divergencias if d.arquivo == "quebrado.xml"] == [
        "XML_ILEGIVEL"
    ]


def test_cli_gera_planilha_markdown_e_sqlite(tmp_path, lote_em_disco):
    saida = tmp_path / "relatorio.xlsx"
    db = tmp_path / "pasta-nova" / "conferencia.sqlite"  # pasta ainda não existe
    codigo = main(["conferir", "--xml", str(lote_em_disco["xml"]), "--erp",
                   str(lote_em_disco["erp"]), "--saida", str(saida), "--db", str(db)])
    assert codigo == 0
    assert saida.exists() and saida.with_suffix(".md").exists() and db.exists()

    wb = load_workbook(saida)
    assert wb.sheetnames == ["Resumo", "Divergências", "Notas sem lançamento",
                             "Lançamentos sem nota", "Regras"]
    div = wb["Divergências"]
    assert div.auto_filter.ref.startswith("A1:")
    assert div["A2"].value == "ALTA" and div["A2"].fill.fgColor.rgb.endswith("F8CBAD")
    assert wb["Notas sem lançamento"].max_row == 1 + 4
    assert wb["Lançamentos sem nota"].max_row == 1 + 2
    assert "relatório executivo" in saida.with_suffix(".md").read_text(encoding="utf-8")


def test_cli_falhar_se_alta(tmp_path, lote_em_disco):
    codigo = main(["conferir", "--xml", str(lote_em_disco["xml"]), "--erp",
                   str(lote_em_disco["erp"]), "--saida", str(tmp_path / "r.xlsx"),
                   "--falhar-se-alta"])
    assert codigo == 1


def test_cli_pasta_inexistente(tmp_path, lote_em_disco):
    assert main(["conferir", "--xml", str(tmp_path / "nao-existe"), "--erp",
                 str(lote_em_disco["erp"])]) == 2
