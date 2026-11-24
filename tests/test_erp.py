"""Leitura do export do ERP e cruzamento XML × ERP via SQL."""

from datetime import date
from decimal import Decimal

import pytest

from nfe_conf import banco
from nfe_conf.erp import ErroLeituraERP, formatar_br, ler_erp, valor_br
from nfe_conf.modelo import Lancamento

CABECALHO = "Nº NF-e;Série;CNPJ Emitente;Valor NF;ICMS;Dt.Lçto;Nº Doc.\n"


def test_valor_br_ida_e_volta():
    assert valor_br("1.234,56") == Decimal("1234.56")
    assert valor_br("0,07") == Decimal("0.07")
    assert formatar_br(Decimal("1234567.8")) == "1.234.567,80"


def test_ler_erp(tmp_path):
    csv = tmp_path / "erp.csv"
    csv.write_text(CABECALHO + "123;1;12.ABC.345/01DE-35;1.000,50;70,04;03.10.2026;5100000001\n",
                   encoding="utf-8-sig")
    [lanc] = ler_erp(csv)
    assert lanc.emit_cnpj == "12ABC34501DE35"
    assert lanc.valor == Decimal("1000.50") and lanc.icms == Decimal("70.04")
    assert lanc.data_lancamento == date(2026, 10, 3) and lanc.linha == 2


def test_ler_erp_reclama_de_coluna_ausente(tmp_path):
    csv = tmp_path / "erp.csv"
    csv.write_text("Nº NF-e;Série\n1;1\n", encoding="utf-8")
    with pytest.raises(ErroLeituraERP, match="Colunas ausentes"):
        ler_erp(csv)


def _lanc(linha, nota, valor=None, icms=None, numero=None):
    return Lancamento(
        linha=linha, doc_contabil=f"51{linha:08d}", numero=numero or nota.numero,
        serie=nota.serie, emit_cnpj=nota.emit_cnpj,
        valor=nota.totais.valor_nota if valor is None else valor,
        icms=nota.totais.valor_icms if icms is None else icms,
        data_lancamento=date(2026, 10, 30),
    )


@pytest.fixture
def cenario(notas_limpas):
    """5 notas: [0] ok, [1] sem lançamento, [2] lançada 2x, [3] valor errado, [4] ICMS errado."""
    n = notas_limpas[:5]
    lancamentos = [
        _lanc(2, n[0]),
        _lanc(3, n[2]),
        _lanc(4, n[2]),
        _lanc(5, n[3], valor=n[3].totais.valor_nota + Decimal("9.00")),
        _lanc(6, n[4], icms=n[4].totais.valor_icms + Decimal("1.00")),
        _lanc(7, n[0], numero=999_999),  # lançamento sem XML
    ]
    con = banco.criar_banco()
    banco.carregar_notas(con, n)
    banco.carregar_lancamentos(con, lancamentos)
    return con, n


def test_sql_notas_sem_lancamento(cenario):
    con, n = cenario
    [linha] = banco.consultar(con, "notas_sem_lancamento.sql")
    assert linha["chave"] == n[1].chave
    assert linha["valor_nota"] == pytest.approx(float(n[1].totais.valor_nota))


def test_sql_lancamentos_sem_nota(cenario):
    con, _ = cenario
    [linha] = banco.consultar(con, "lancamentos_sem_nota.sql")
    assert linha["numero"] == 999_999 and linha["linha"] == 7


def test_sql_lancamentos_duplicados(cenario):
    con, n = cenario
    [linha] = banco.consultar(con, "lancamentos_duplicados.sql")
    assert linha["numero"] == n[2].numero and linha["qtd_lancamentos"] == 2


def test_sql_valor_divergente(cenario):
    con, n = cenario
    [linha] = banco.consultar(con, "valor_divergente.sql")
    assert linha["chave"] == n[3].chave and linha["diferenca"] == pytest.approx(9.0)


def test_sql_icms_divergente(cenario):
    con, n = cenario
    [linha] = banco.consultar(con, "icms_divergente.sql")
    assert linha["chave"] == n[4].chave and linha["diferenca"] == pytest.approx(1.0)


def test_sql_copia_de_xml_nao_vira_nota_nova(notas_limpas):
    import copy

    copia = copy.deepcopy(notas_limpas[0])
    copia.arquivo = "copia.xml"
    con = banco.criar_banco()
    banco.carregar_notas(con, [notas_limpas[0], copia])
    assert con.execute("SELECT COUNT(*) FROM notas").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM arquivos").fetchone()[0] == 2
