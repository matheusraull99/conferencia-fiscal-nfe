"""Leitura do XML da NF-e (layout 4.00) com namespace do Portal Fiscal.

Aceita tanto o ``nfeProc`` (nota + protocolo de autorização) quanto o ``NFe`` solto.
Usa só a biblioteca padrão (``xml.etree``) — nenhuma dependência para ler XML.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .dv import limpar_cnpj
from .modelo import ZERO, Item, Nota, Totais

NS_NFE = "http://www.portalfiscal.inf.br/nfe"
NS = {"nfe": NS_NFE}


class ErroLeituraXML(Exception):
    """XML que não dá para ler como NF-e (malformado, sem infNFe, campo obrigatório ausente)."""


def _texto(elemento: ET.Element | None, caminho: str, padrao: str = "") -> str:
    if elemento is None:
        return padrao
    achado = elemento.find(caminho, NS)
    if achado is None or achado.text is None:
        return padrao
    return achado.text.strip()


def _decimal(elemento: ET.Element | None, caminho: str) -> Decimal:
    texto = _texto(elemento, caminho)
    if not texto:
        return ZERO
    try:
        return Decimal(texto)
    except InvalidOperation as exc:
        raise ErroLeituraXML(f"Valor numérico inválido em {caminho}: {texto!r}") from exc


def _primeiro_filho(elemento: ET.Element | None) -> ET.Element | None:
    if elemento is None:
        return None
    return next(iter(elemento), None)


def _ler_item(det: ET.Element) -> Item:
    prod = det.find("nfe:prod", NS)
    imposto = det.find("nfe:imposto", NS)
    icms = _primeiro_filho(imposto.find("nfe:ICMS", NS)) if imposto is not None else None
    ipi_trib = imposto.find("nfe:IPI/nfe:IPITrib", NS) if imposto is not None else None
    pis = _primeiro_filho(imposto.find("nfe:PIS", NS)) if imposto is not None else None
    cofins = _primeiro_filho(imposto.find("nfe:COFINS", NS)) if imposto is not None else None

    return Item(
        n_item=int(det.get("nItem", "0")),
        codigo=_texto(prod, "nfe:cProd"),
        descricao=_texto(prod, "nfe:xProd"),
        ncm=_texto(prod, "nfe:NCM"),
        cfop=_texto(prod, "nfe:CFOP"),
        quantidade=_decimal(prod, "nfe:qCom"),
        valor_unitario=_decimal(prod, "nfe:vUnCom"),
        valor_produto=_decimal(prod, "nfe:vProd"),
        valor_desconto=_decimal(prod, "nfe:vDesc"),
        icms_origem=_texto(icms, "nfe:orig", "0"),
        icms_cst=_texto(icms, "nfe:CST") or _texto(icms, "nfe:CSOSN"),
        icms_base=_decimal(icms, "nfe:vBC"),
        icms_reducao_base=_decimal(icms, "nfe:pRedBC"),
        icms_aliquota=_decimal(icms, "nfe:pICMS"),
        icms_valor=_decimal(icms, "nfe:vICMS"),
        icms_st_base=_decimal(icms, "nfe:vBCST"),
        icms_st_valor=_decimal(icms, "nfe:vICMSST"),
        ipi_base=_decimal(ipi_trib, "nfe:vBC"),
        ipi_aliquota=_decimal(ipi_trib, "nfe:pIPI"),
        ipi_valor=_decimal(ipi_trib, "nfe:vIPI"),
        pis_cst=_texto(pis, "nfe:CST"),
        pis_base=_decimal(pis, "nfe:vBC"),
        pis_aliquota=_decimal(pis, "nfe:pPIS"),
        pis_valor=_decimal(pis, "nfe:vPIS"),
        cofins_cst=_texto(cofins, "nfe:CST"),
        cofins_base=_decimal(cofins, "nfe:vBC"),
        cofins_aliquota=_decimal(cofins, "nfe:pCOFINS"),
        cofins_valor=_decimal(cofins, "nfe:vCOFINS"),
    )


def _ler_totais(tot: ET.Element | None) -> Totais:
    return Totais(
        base_icms=_decimal(tot, "nfe:vBC"),
        valor_icms=_decimal(tot, "nfe:vICMS"),
        base_st=_decimal(tot, "nfe:vBCST"),
        valor_st=_decimal(tot, "nfe:vST"),
        valor_produtos=_decimal(tot, "nfe:vProd"),
        valor_frete=_decimal(tot, "nfe:vFrete"),
        valor_seguro=_decimal(tot, "nfe:vSeg"),
        valor_desconto=_decimal(tot, "nfe:vDesc"),
        valor_ipi=_decimal(tot, "nfe:vIPI"),
        valor_pis=_decimal(tot, "nfe:vPIS"),
        valor_cofins=_decimal(tot, "nfe:vCOFINS"),
        valor_outros=_decimal(tot, "nfe:vOutro"),
        valor_nota=_decimal(tot, "nfe:vNF"),
    )


def ler_nota(conteudo: bytes, arquivo: str = "<memória>") -> Nota:
    """Converte o conteúdo de um XML de NF-e em ``Nota``."""
    try:
        raiz = ET.fromstring(conteudo)
    except ET.ParseError as exc:
        raise ErroLeituraXML(f"XML malformado: {exc}") from exc

    inf = raiz if raiz.tag == f"{{{NS_NFE}}}infNFe" else raiz.find(".//nfe:infNFe", NS)
    if inf is None:
        raise ErroLeituraXML("Não encontrei <infNFe> no namespace da NF-e")

    chave = inf.get("Id", "").removeprefix("NFe") or _texto(raiz, ".//nfe:protNFe//nfe:chNFe")
    ide = inf.find("nfe:ide", NS)
    emit = inf.find("nfe:emit", NS)
    dest = inf.find("nfe:dest", NS)
    if ide is None or emit is None:
        raise ErroLeituraXML("Grupo <ide> ou <emit> ausente")

    dh_emi = _texto(ide, "nfe:dhEmi")
    try:
        data_emissao = datetime.fromisoformat(dh_emi).date()
    except ValueError as exc:
        raise ErroLeituraXML(f"dhEmi inválido: {dh_emi!r}") from exc

    return Nota(
        arquivo=arquivo,
        chave=chave,
        numero=int(_texto(ide, "nfe:nNF", "0")),
        serie=int(_texto(ide, "nfe:serie", "0")),
        modelo=_texto(ide, "nfe:mod"),
        data_emissao=data_emissao,
        cuf=_texto(ide, "nfe:cUF"),
        id_dest=_texto(ide, "nfe:idDest"),
        natureza_operacao=_texto(ide, "nfe:natOp"),
        tp_emis=_texto(ide, "nfe:tpEmis"),
        cnf=_texto(ide, "nfe:cNF"),
        emit_cnpj=limpar_cnpj(_texto(emit, "nfe:CNPJ")),
        emit_nome=_texto(emit, "nfe:xNome"),
        emit_uf=_texto(emit, "nfe:enderEmit/nfe:UF"),
        emit_crt=_texto(emit, "nfe:CRT"),
        dest_cnpj=limpar_cnpj(_texto(dest, "nfe:CNPJ")),
        dest_nome=_texto(dest, "nfe:xNome"),
        dest_uf=_texto(dest, "nfe:enderDest/nfe:UF"),
        itens=[_ler_item(det) for det in inf.findall("nfe:det", NS)],
        totais=_ler_totais(inf.find("nfe:total/nfe:ICMSTot", NS)),
    )


def ler_arquivo(caminho: Path) -> Nota:
    return ler_nota(caminho.read_bytes(), arquivo=caminho.name)
