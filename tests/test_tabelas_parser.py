import random
from decimal import Decimal

import pytest

from nfe_conf.dv import gerar_cnpj
from nfe_conf.parser import ErroLeituraXML, ler_nota


@pytest.mark.parametrize(
    ("origem_uf", "destino_uf", "origem_merc", "esperada"),
    [
        ("SP", "GO", "0", "7"),   # Sul/Sudeste -> Centro-Oeste
        ("SP", "ES", "0", "7"),   # ES é exceção do Sudeste: recebe 7%
        ("ES", "SP", "0", "12"),  # ...e envia 12%
        ("SP", "MG", "0", "12"),  # Sul/Sudeste entre si
        ("GO", "SP", "0", "12"),  # Centro-Oeste -> Sudeste
        ("BA", "GO", "0", "12"),
        ("SP", "GO", "1", "4"),   # importado (Res. SF 13/2012)
        ("BA", "GO", "8", "4"),
        ("SP", "GO", "6", "7"),   # importado sem similar (CAMEX) fica fora dos 4%
    ],
)
def test_aliquota_interestadual(tabelas, origem_uf, destino_uf, origem_merc, esperada):
    assert tabelas.aliquota_icms_interestadual(origem_uf, destino_uf, origem_merc) == Decimal(
        esperada
    )


def test_matriz_tem_todos_os_pares(tabelas):
    assert len(tabelas.aliquota_interestadual) == 27 * 26
    with pytest.raises(ValueError):
        tabelas.aliquota_icms_interestadual("GO", "GO", "0")


def test_regime_pis_cofins(tabelas):
    assert tabelas.regime_pis_cofins(Decimal("1.6500"), Decimal("7.60")) == "nao_cumulativo"
    assert tabelas.regime_pis_cofins(Decimal("0.65"), Decimal("3")) == "cumulativo"
    assert tabelas.regime_pis_cofins(Decimal("1.65"), Decimal("3.00")) is None


def test_parser_le_valores_em_decimal(nota_sp):
    assert nota_sp.modelo == "55"
    assert nota_sp.emit_uf == "SP" and nota_sp.dest_uf == "GO"
    item = nota_sp.itens[0]
    assert isinstance(item.valor_produto, Decimal)
    assert item.icms_cst == "00" and item.icms_aliquota in {Decimal("7"), Decimal("4")}
    assert nota_sp.totais.valor_nota > 0


def test_parser_le_csosn_do_simples(nota_simples):
    assert nota_simples.emit_crt == "1"
    assert all(i.icms_cst == "102" for i in nota_simples.itens)


def test_parser_aceita_nfe_sem_nfeproc():
    cnpj = gerar_cnpj(random.Random(9)).encode()
    xml = (
        b'<NFe xmlns="http://www.portalfiscal.inf.br/nfe"><infNFe Id="NFe123" versao="4.00">'
        b"<ide><cUF>35</cUF><mod>55</mod><serie>1</serie><nNF>9</nNF>"
        b"<dhEmi>2026-10-01T10:00:00-03:00</dhEmi></ide>"
        b"<emit><CNPJ>" + cnpj + b"</CNPJ><enderEmit><UF>SP</UF></enderEmit></emit>"
        b"</infNFe></NFe>"
    )
    nota = ler_nota(xml)
    assert nota.chave == "123" and nota.numero == 9 and nota.itens == []


@pytest.mark.parametrize(
    "conteudo",
    [
        b"<nfeProc><NFe>sem fechar",
        b"<NFe><infNFe Id='NFe1'/></NFe>",  # sem namespace do Portal Fiscal
    ],
)
def test_parser_rejeita_xml_invalido(conteudo):
    with pytest.raises(ErroLeituraXML):
        ler_nota(conteudo)
