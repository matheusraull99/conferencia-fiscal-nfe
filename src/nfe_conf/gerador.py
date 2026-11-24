"""Gera um lote FICTÍCIO de NF-e (layout 4.00) + export do ERP, com divergências plantadas.

Tudo aqui é inventado: empresas, CNPJs (aleatórios, só com DV válido), inscrições
estaduais, produtos e valores. As notas saem em ambiente de homologação (tpAmb=2),
sem assinatura digital, e com o texto "SEM VALOR FISCAL" no destinatário — o mesmo
que a SEFAZ exige em notas de teste.

Além dos XMLs e do CSV do ERP, o gerador grava ``gabarito.json`` com cada
divergência plantada. Os testes usam o gabarito para medir se o motor acha tudo o
que foi plantado e nada além disso.
"""

from __future__ import annotations

import copy
import csv
import json
import random
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from .dv import formatar_cnpj, gerar_cnpj, montar_chave
from .erp import COLUNAS, formatar_br
from .modelo import ZERO, Item, Nota, Totais, arredondar
from .parser import NS_NFE
from .tabelas import carregar_tabelas

ALIQUOTA_INTERNA_GO = Decimal("19")  # simplificação: só o destinatário (GO) recebe operação interna
MVA_ST = Decimal("40")
# Prefixo de CEP (5 dígitos) de cada município usado; o sufixo é sorteado.
CEP_POR_MUNICIPIO = {
    "3550308": "01310", "3106200": "30140", "4106902": "80010", "4314902": "90010",
    "2927408": "40010", "2611606": "50030", "5208707": "74000", "3509502": "13010",
    "5201108": "75020",
}
NOME_HOMOLOGACAO = "NF-E EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL"


@dataclass
class Produto:
    codigo: str
    descricao: str
    ncm: str
    unidade: str
    preco: Decimal
    icms: str = "00"  # 00, 10, 20, 60 ou 102 (CSOSN)
    origem: str = "0"
    ipi: Decimal = ZERO
    reducao_base: Decimal = ZERO


@dataclass
class Empresa:
    nome: str
    uf: str
    cmun: str
    xmun: str
    crt: str
    regime_pis_cofins: str | None
    produtos: list[Produto] = field(default_factory=list)
    cnpj: str = ""
    ie: str = ""
    cep: str = ""
    numero_inicial: int = 0


def _p(*args, **kwargs) -> Produto:
    args = list(args)
    args[4] = Decimal(args[4])
    for chave in ("ipi", "reducao_base"):
        if chave in kwargs:
            kwargs[chave] = Decimal(kwargs[chave])
    return Produto(*args, **kwargs)


def _fornecedores() -> list[Empresa]:
    return [
        Empresa("Metalúrgica Horizonte Fictícia Ltda", "SP", "3550308", "São Paulo", "3",
                "nao_cumulativo", [
                    _p("MH-100", "Parafuso sextavado M8 zincado", "73181500", "CT", "38.90",
                       ipi="5"),
                    _p("MH-220", "Válvula esfera latão 1/2 pol. importada", "84818099", "UN",
                       "64.50", origem="1", ipi="5"),
                ]),
        Empresa("Plásticos Serra Azul Fictícia S.A.", "MG", "3106200", "Belo Horizonte", "3",
                "cumulativo", [
                    _p("SA-010", "Caixa organizadora plástica 20 L", "39269090", "UN", "27.40",
                       ipi="10"),
                    _p("SA-044", "Bandeja plástica empilhável", "39269090", "UN", "12.15",
                       ipi="10"),
                ]),
        Empresa("Condutores Araucária Fictícia Ltda", "PR", "4106902", "Curitiba", "3",
                "nao_cumulativo", [
                    _p("CA-25", "Cabo flexível 2,5 mm² rolo 100 m", "85444900", "RL", "289.00",
                       icms="20", reducao_base="20"),
                    _p("CA-40", "Cabo flexível 4 mm² rolo 100 m", "85444900", "RL", "452.00",
                       icms="20", reducao_base="20"),
                ]),
        Empresa("Autopeças Pampa Fictícia Ltda", "RS", "4314902", "Porto Alegre", "3",
                "nao_cumulativo", [
                    _p("AP-PF1", "Pastilha de freio dianteira", "87083090", "JG", "96.80",
                       icms="10"),
                    _p("AP-DS2", "Disco de freio ventilado", "87083090", "UN", "158.30",
                       icms="10"),
                ]),
        Empresa("Química Recôncavo Fictícia Ltda", "BA", "2927408", "Salvador", "3",
                "cumulativo", [
                    _p("QR-DT5", "Detergente industrial 5 L", "34022000", "GL", "41.70"),
                    _p("QR-DS1", "Desengraxante concentrado 1 L", "34022000", "UN", "18.90"),
                ]),
        Empresa("Embalagens Capibaribe Fictícia Ltda", "PE", "2611606", "Recife", "3",
                "nao_cumulativo", [
                    _p("EC-CX40", "Caixa de papelão ondulado 40x30x30", "48191000", "UN", "4.85"),
                    _p("EC-CX60", "Caixa de papelão ondulado 60x40x40", "48191000", "UN", "7.30"),
                ]),
        Empresa("Atacadista Cerrado Fictício Ltda", "GO", "5208707", "Goiânia", "3",
                "nao_cumulativo", [
                    _p("AC-AG50", "Água mineral 500 ml fardo c/ 12", "22011000", "FD", "14.40",
                       icms="60"),
                    _p("AC-OL1", "Óleo lubrificante 1 L", "27101932", "UN", "32.60", icms="60"),
                    _p("AC-IN10", "Interruptor simples 10 A", "85365090", "UN", "9.75"),
                ]),
        Empresa("Papelaria Ipê Fictícia ME", "SP", "3509502", "Campinas", "1", None, [
                    _p("PI-A4", "Papel sulfite A4 resma 500 fls", "48025610", "RM", "26.90",
                       icms="102"),
                    _p("PI-CN", "Caneta esferográfica azul cx 50", "96081000", "CX", "39.00",
                       icms="102"),
                ]),
        Empresa("Móveis Anápolis Fictícia ME", "GO", "5201108", "Anápolis", "1", None, [
                    _p("MA-CG", "Cadeira giratória operacional", "94013000", "UN", "389.00",
                       icms="102"),
                ]),
    ]


def _destinatario() -> Empresa:
    return Empresa("Distribuidora Fictícia Planalto Ltda", "GO", "5208707", "Goiânia", "3",
                   "nao_cumulativo")


# ====================================================================== cálculo


def _cfop(empresa: Empresa, destino: Empresa, produto: Produto) -> str:
    prefixo = "6" if empresa.uf != destino.uf else "5"
    if produto.icms == "10":
        return prefixo + "401"
    if produto.icms == "60":
        return prefixo + "405"
    return prefixo + ("101" if produto.ipi > 0 else "102")


def _calcular_item(item: Item, nota: Nota) -> None:
    """Recalcula os tributos do item a partir de valor, CST e alíquotas já definidos."""
    liquido = item.valor_produto - item.valor_desconto
    if item.icms_cst in {"00", "10", "20"}:
        reducao = item.icms_reducao_base if item.icms_cst == "20" else ZERO
        item.icms_base = arredondar(liquido * (1 - reducao / 100))
        item.icms_valor = arredondar(item.icms_base * item.icms_aliquota / 100)
    if item.ipi_aliquota > 0:
        item.ipi_base = arredondar(liquido)
        item.ipi_valor = arredondar(item.ipi_base * item.ipi_aliquota / 100)
    if item.icms_cst == "10":
        item.icms_st_base = arredondar((item.icms_base + item.ipi_valor) * (1 + MVA_ST / 100))
        item.icms_st_valor = max(
            ZERO, arredondar(item.icms_st_base * ALIQUOTA_INTERNA_GO / 100) - item.icms_valor
        )
    if item.pis_cst == "01":
        item.pis_base = item.cofins_base = arredondar(liquido)
        item.pis_valor = arredondar(item.pis_base * item.pis_aliquota / 100)
        item.cofins_valor = arredondar(item.cofins_base * item.cofins_aliquota / 100)


def _calcular_totais(nota: Nota) -> None:
    def soma(attr: str) -> Decimal:
        return sum((getattr(i, attr) for i in nota.itens), ZERO)

    t = Totais(
        base_icms=soma("icms_base"),
        valor_icms=soma("icms_valor"),
        base_st=soma("icms_st_base"),
        valor_st=soma("icms_st_valor"),
        valor_produtos=soma("valor_produto"),
        valor_desconto=soma("valor_desconto"),
        valor_ipi=soma("ipi_valor"),
        valor_pis=soma("pis_valor"),
        valor_cofins=soma("cofins_valor"),
    )
    t.valor_nota = t.valor_produtos - t.valor_desconto + t.valor_st + t.valor_ipi
    nota.totais = t


# ====================================================================== XML


def _sub(pai: ET.Element, tag: str, texto: object | None = None) -> ET.Element:
    el = ET.SubElement(pai, f"{{{NS_NFE}}}{tag}")
    if texto is not None:
        el.text = str(texto)
    return el


def _d2(v: Decimal) -> str:
    return f"{v:.2f}"


def _endereco(pai: ET.Element, tag: str, e: Empresa, rng: random.Random) -> None:
    end = _sub(pai, tag)
    _sub(end, "xLgr", "Avenida das Indústrias")
    _sub(end, "nro", rng.randint(10, 3000))
    _sub(end, "xBairro", "Distrito Industrial")
    _sub(end, "cMun", e.cmun)
    _sub(end, "xMun", e.xmun)
    _sub(end, "UF", e.uf)
    _sub(end, "CEP", e.cep)
    _sub(end, "cPais", "1058")
    _sub(end, "xPais", "Brasil")


def nota_para_xml(nota: Nota, emit: Empresa, dest: Empresa, unidades: dict[str, str],
                  hora: str = "10:00:00", seed_xml: int = 0) -> bytes:
    """Serializa a nota no layout 4.00 dentro de um ``nfeProc`` com protocolo fictício."""
    rng = random.Random(seed_xml)
    ET.register_namespace("", NS_NFE)
    proc = ET.Element(f"{{{NS_NFE}}}nfeProc", {"versao": "4.00"})
    nfe = _sub(proc, "NFe")
    inf = _sub(nfe, "infNFe")
    inf.set("Id", "NFe" + nota.chave)
    inf.set("versao", "4.00")

    dh_emi = f"{nota.data_emissao.isoformat()}T{hora}-03:00"
    ide = _sub(inf, "ide")
    for tag, valor in [
        ("cUF", nota.cuf), ("cNF", nota.cnf), ("natOp", nota.natureza_operacao),
        ("mod", nota.modelo), ("serie", nota.serie), ("nNF", nota.numero), ("dhEmi", dh_emi),
        ("tpNF", "1"), ("idDest", nota.id_dest), ("cMunFG", emit.cmun), ("tpImp", "1"),
        ("tpEmis", nota.tp_emis), ("cDV", nota.chave[-1]), ("tpAmb", "2"), ("finNFe", "1"),
        ("indFinal", "0"), ("indPres", "9"), ("procEmi", "0"), ("verProc", "gerador-ficticio 1.0"),
    ]:
        _sub(ide, tag, valor)

    em = _sub(inf, "emit")
    _sub(em, "CNPJ", nota.emit_cnpj)
    _sub(em, "xNome", nota.emit_nome)
    _endereco(em, "enderEmit", emit, rng)
    _sub(em, "IE", emit.ie)
    _sub(em, "CRT", nota.emit_crt)

    de = _sub(inf, "dest")
    _sub(de, "CNPJ", nota.dest_cnpj)
    _sub(de, "xNome", nota.dest_nome)
    _endereco(de, "enderDest", dest, rng)
    _sub(de, "indIEDest", "1")
    _sub(de, "IE", dest.ie)

    for item in nota.itens:
        det = _sub(inf, "det")
        det.set("nItem", str(item.n_item))
        prod = _sub(det, "prod")
        unidade = unidades.get(item.codigo, "UN")
        for tag, valor in [
            ("cProd", item.codigo), ("cEAN", "SEM GTIN"), ("xProd", item.descricao),
            ("NCM", item.ncm), ("CFOP", item.cfop), ("uCom", unidade),
            ("qCom", f"{item.quantidade:.4f}"), ("vUnCom", f"{item.valor_unitario:.4f}"),
            ("vProd", _d2(item.valor_produto)), ("cEANTrib", "SEM GTIN"), ("uTrib", unidade),
            ("qTrib", f"{item.quantidade:.4f}"), ("vUnTrib", f"{item.valor_unitario:.4f}"),
        ]:
            _sub(prod, tag, valor)
        if item.valor_desconto:
            _sub(prod, "vDesc", _d2(item.valor_desconto))
        _sub(prod, "indTot", "1")

        imposto = _sub(det, "imposto")
        icms = _sub(imposto, "ICMS")
        cst = item.icms_cst
        grupo = _sub(icms, "ICMSSN102" if cst == "102" else f"ICMS{cst}")
        _sub(grupo, "orig", item.icms_origem)
        _sub(grupo, "CSOSN" if cst == "102" else "CST", cst)
        if cst in {"00", "10", "20"}:
            _sub(grupo, "modBC", "3")
            if cst == "20":
                _sub(grupo, "pRedBC", f"{item.icms_reducao_base:.4f}")
            _sub(grupo, "vBC", _d2(item.icms_base))
            _sub(grupo, "pICMS", f"{item.icms_aliquota:.4f}")
            _sub(grupo, "vICMS", _d2(item.icms_valor))
        if cst == "10":
            _sub(grupo, "modBCST", "4")
            _sub(grupo, "pMVAST", f"{MVA_ST:.4f}")
            _sub(grupo, "vBCST", _d2(item.icms_st_base))
            _sub(grupo, "pICMSST", f"{ALIQUOTA_INTERNA_GO:.4f}")
            _sub(grupo, "vICMSST", _d2(item.icms_st_valor))

        if item.ipi_aliquota > 0:
            ipi = _sub(imposto, "IPI")
            _sub(ipi, "cEnq", "999")
            trib = _sub(ipi, "IPITrib")
            _sub(trib, "CST", "50")
            _sub(trib, "vBC", _d2(item.ipi_base))
            _sub(trib, "pIPI", f"{item.ipi_aliquota:.4f}")
            _sub(trib, "vIPI", _d2(item.ipi_valor))

        for nome, cst_pc, base, aliq, valor in (
            ("PIS", item.pis_cst, item.pis_base, item.pis_aliquota, item.pis_valor),
            ("COFINS", item.cofins_cst, item.cofins_base, item.cofins_aliquota,
             item.cofins_valor),
        ):
            g = _sub(imposto, nome)
            sub = _sub(g, f"{nome}Aliq" if cst_pc == "01" else f"{nome}Outr")
            _sub(sub, "CST", cst_pc)
            _sub(sub, "vBC", _d2(base))
            _sub(sub, f"p{nome}", f"{aliq:.4f}")
            _sub(sub, f"v{nome}", _d2(valor))

    t = nota.totais
    tot = _sub(_sub(inf, "total"), "ICMSTot")
    for tag, valor in [
        ("vBC", t.base_icms), ("vICMS", t.valor_icms), ("vICMSDeson", ZERO), ("vFCP", ZERO),
        ("vBCST", t.base_st), ("vST", t.valor_st), ("vFCPST", ZERO), ("vFCPSTRet", ZERO),
        ("vProd", t.valor_produtos), ("vFrete", t.valor_frete), ("vSeg", t.valor_seguro),
        ("vDesc", t.valor_desconto), ("vII", ZERO), ("vIPI", t.valor_ipi), ("vIPIDevol", ZERO),
        ("vPIS", t.valor_pis), ("vCOFINS", t.valor_cofins), ("vOutro", t.valor_outros),
        ("vNF", t.valor_nota),
    ]:
        _sub(tot, tag, _d2(valor))

    _sub(_sub(inf, "transp"), "modFrete", "0")
    det_pag = _sub(_sub(inf, "pag"), "detPag")
    _sub(det_pag, "tPag", "15")
    _sub(det_pag, "vPag", _d2(t.valor_nota))
    _sub(_sub(inf, "infAdic"), "infCpl",
         "Documento fictício gerado para portfólio - sem valor fiscal.")

    prot_nfe = _sub(proc, "protNFe")
    prot_nfe.set("versao", "4.00")
    prot = _sub(prot_nfe, "infProt")
    for tag, valor in [
        ("tpAmb", "2"), ("verAplic", "SVRS-FICTICIO"), ("chNFe", nota.chave),
        ("dhRecbto", f"{nota.data_emissao.isoformat()}T{hora}-03:00"),
        ("nProt", f"{nota.cuf}2{rng.randrange(10**11, 10**12)}"), ("cStat", "100"),
        ("xMotivo", "Autorizado o uso da NF-e"),
    ]:
        _sub(prot, tag, valor)

    ET.indent(proc)
    return ET.tostring(proc, encoding="utf-8", xml_declaration=True)


# ====================================================================== lote


@dataclass
class Lote:
    notas: list[Nota]
    emitentes: dict[str, Empresa]
    destinatario: Empresa
    unidades: dict[str, str]
    horas: dict[str, str]
    gabarito: list[dict] = field(default_factory=list)
    copias: list[Nota] = field(default_factory=list)
    lancamentos: list[dict] = field(default_factory=list)


def _registrar(lote: Lote, codigo: str, nota: Nota, numero: int | None = None) -> None:
    lote.gabarito.append({
        "codigo": codigo,
        "emit_cnpj": nota.emit_cnpj,
        "numero": numero if numero is not None else nota.numero,
        "serie": nota.serie,
    })


def _montar_notas(rng: random.Random, qtd: int) -> Lote:
    tabelas = carregar_tabelas()
    dest = _destinatario()
    fornecedores = _fornecedores()
    for e in [dest, *fornecedores]:
        e.cnpj = gerar_cnpj(rng)
        e.ie = f"{rng.randrange(10**8, 10**9)}"
        e.cep = f"{CEP_POR_MUNICIPIO[e.cmun]}{rng.randrange(100, 1000)}"
        e.numero_inicial = rng.randint(1_000, 90_000)

    unidades = {p.codigo: p.unidade for f in fornecedores for p in f.produtos}
    lote = Lote([], {f.cnpj: f for f in fornecedores}, dest, unidades, {})
    proximo = {f.cnpj: f.numero_inicial for f in fornecedores}

    for i in range(qtd):
        emit = fornecedores[i % len(fornecedores)]
        numero = proximo[emit.cnpj]
        proximo[emit.cnpj] += rng.randint(1, 40)
        emissao = date(2026, 10, rng.randint(1, 28))
        serie = 1
        cuf = tabelas.cuf_por_uf[emit.uf]
        cnf = f"{rng.randrange(10**7, 10**8)}"
        chave = montar_chave(cuf, emissao.strftime("%y%m"), emit.cnpj, "55", serie, numero,
                             "1", cnf)
        nota = Nota(
            arquivo=f"NFe{chave}.xml", chave=chave, numero=numero, serie=serie, modelo="55",
            data_emissao=emissao, cuf=cuf, id_dest="2" if emit.uf != dest.uf else "1",
            natureza_operacao="Venda de mercadoria", tp_emis="1", cnf=cnf,
            emit_cnpj=emit.cnpj, emit_nome=emit.nome, emit_uf=emit.uf, emit_crt=emit.crt,
            dest_cnpj=dest.cnpj, dest_nome=NOME_HOMOLOGACAO, dest_uf=dest.uf,
        )
        qtd_itens = rng.randint(1, min(3, len(emit.produtos)))
        for n_item, produto in enumerate(rng.sample(emit.produtos, qtd_itens), start=1):
            quantidade = Decimal(rng.choice([1, 2, 5, 10, 12, 20, 24, 50, 100, 150]))
            unitario = (produto.preco * Decimal(rng.uniform(0.95, 1.05))).quantize(
                Decimal("0.01"))
            valor = arredondar(quantidade * unitario)
            desconto = arredondar(valor * Decimal("0.03")) if rng.random() < 0.2 else ZERO
            if emit.uf != dest.uf and produto.icms in {"00", "10", "20"}:
                aliquota = tabelas.aliquota_icms_interestadual(emit.uf, dest.uf, produto.origem)
            else:
                aliquota = ALIQUOTA_INTERNA_GO if produto.icms in {"00", "10", "20"} else ZERO
            pis, cofins = (tabelas.pis_cofins[emit.regime_pis_cofins]
                           if emit.regime_pis_cofins else (ZERO, ZERO))
            item = Item(
                n_item=n_item, codigo=produto.codigo, descricao=produto.descricao,
                ncm=produto.ncm, cfop=_cfop(emit, dest, produto), quantidade=quantidade,
                valor_unitario=unitario, valor_produto=valor, valor_desconto=desconto,
                icms_origem=produto.origem, icms_cst=produto.icms,
                icms_reducao_base=produto.reducao_base, icms_aliquota=aliquota,
                ipi_aliquota=produto.ipi if emit.crt == "3" else ZERO,
                pis_cst="01" if emit.regime_pis_cofins else "99", pis_aliquota=pis,
                cofins_cst="01" if emit.regime_pis_cofins else "99", cofins_aliquota=cofins,
            )
            _calcular_item(item, nota)
            nota.itens.append(item)
        _calcular_totais(nota)
        lote.notas.append(nota)
        lote.horas[chave] = f"{rng.randint(7, 18):02d}:{rng.randint(0, 59):02d}:00"
    return lote


def _plantar_divergencias_xml(lote: Lote, rng: random.Random, usadas: set[str]) -> None:
    tabelas = carregar_tabelas()

    def escolher(filtro, qtd: int) -> list[Nota]:
        candidatas = [n for n in lote.notas if n.chave not in usadas and filtro(n)]
        if len(candidatas) < qtd:
            raise RuntimeError("Lote pequeno demais para plantar todas as divergências")
        escolhidas = rng.sample(candidatas, qtd)
        usadas.update(n.chave for n in escolhidas)
        return escolhidas

    def item_com(nota: Nota, cond) -> Item | None:
        return next((i for i in nota.itens if cond(i)), None)

    # 1) Base de ICMS errada (CST 00): base inflada, ICMS coerente com a base errada
    for nota in escolher(lambda n: item_com(n, lambda i: i.icms_cst == "00"), 3):
        item = item_com(nota, lambda i: i.icms_cst == "00")
        item.icms_base = arredondar(item.icms_base * Decimal("1.10"))
        item.icms_valor = arredondar(item.icms_base * item.icms_aliquota / 100)
        _registrar(lote, "ICMS_BASE", nota)

    # 2) Alíquota interestadual incorreta: 7→12 (SP→GO), 4→12 (importado), 12→7 (BA/PE→GO)
    casos = [
        (lambda i, n: n.emit_uf == "SP" and i.icms_origem == "0" and i.icms_cst == "00",
         Decimal("12")),
        (lambda i, n: i.icms_origem in tabelas.origens_aliquota_4 and i.icms_cst == "00",
         Decimal("12")),
        (lambda i, n: n.emit_uf in {"BA", "PE"} and i.icms_cst == "00", Decimal("7")),
    ]
    for cond, aliquota_errada in casos:
        nota = escolher(lambda n, c=cond: item_com(n, lambda i: c(i, n)), 1)[0]
        item = item_com(nota, lambda i, c=cond, n=nota: c(i, n))
        item.icms_aliquota = aliquota_errada
        item.icms_valor = arredondar(item.icms_base * aliquota_errada / 100)
        _registrar(lote, "ICMS_ALIQ_INTERESTADUAL", nota)

    # 3) CFOP incompatível: 2 interestaduais com 5xxx e 1 interna com 6xxx
    for nota in escolher(lambda n: n.id_dest == "2", 2) + escolher(lambda n: n.id_dest == "1", 1):
        item = nota.itens[0]
        item.cfop = ("5" if nota.id_dest == "2" else "6") + item.cfop[1:]
        _registrar(lote, "CFOP_OPERACAO", nota)

    # 4) PIS/COFINS fora do regime (pares misturados ou inexistentes)
    pares = [(Decimal("1.65"), Decimal("3.00")), (Decimal("0.65"), Decimal("7.60")),
             (Decimal("1.20"), Decimal("5.00"))]
    for nota, (pis, cofins) in zip(
        escolher(lambda n: n.emit_crt == "3", len(pares)), pares, strict=True
    ):
        item = nota.itens[0]
        item.pis_aliquota, item.cofins_aliquota = pis, cofins
        _calcular_item(item, nota)
        _registrar(lote, "PIS_COFINS_ALIQUOTA", nota)

    # 5) NCM inválido: 7 dígitos e capítulo 77 (reservado na NCM)
    for nota, ncm in zip(escolher(lambda n: True, 2), ["7318150", "77010000"], strict=True):
        nota.itens[0].ncm = ncm
        _registrar(lote, "NCM_INVALIDO", nota)

    # Totais refletem os itens já alterados (o "emissor" somou certo)
    for nota in lote.notas:
        _calcular_totais(nota)

    # 6) Soma dos itens ≠ total da nota (cabeçalho digitado à parte)
    a, b = escolher(lambda n: True, 2)
    a.totais.valor_produtos += Decimal("150.00")
    a.totais.valor_nota += Decimal("150.00")
    b.totais.valor_nota -= Decimal("37.90")
    _registrar(lote, "TOTAL_NOTA", a)
    _registrar(lote, "TOTAL_NOTA", b)

    # 7) Chave de acesso com DV errado
    for nota in escolher(lambda n: True, 2):
        dv_errado = (int(nota.chave[-1]) + 1) % 10
        nota.chave = nota.chave[:-1] + str(dv_errado)
        nota.arquivo = f"NFe{nota.chave}.xml"
        _registrar(lote, "CHAVE_DV", nota)

    # 8) Mesma nota recebida duas vezes (o fornecedor reenviou o e-mail)
    for nota in escolher(lambda n: True, 2):
        copia = copy.deepcopy(nota)
        copia.arquivo = f"NFe{nota.chave}(1).xml"
        lote.copias.append(copia)
        _registrar(lote, "NOTA_DUPLICADA", nota)


def _montar_erp(lote: Lote, rng: random.Random, usadas: set[str]) -> None:
    livres = [n for n in lote.notas if n.chave not in usadas]
    rng.shuffle(livres)
    nao_lancadas = livres[:4]
    duplicadas = livres[4:6]
    valor_errado = livres[6:9]
    icms_errado = [n for n in livres[9:] if n.totais.valor_icms > 0][:1]

    doc = 5100004000
    for nota in lote.notas:
        if nota in nao_lancadas:
            _registrar(lote, "ERP_NAO_LANCADA", nota)
            continue
        valor, icms = nota.totais.valor_nota, nota.totais.valor_icms
        if nota in valor_errado:
            tipo = valor_errado.index(nota)
            if tipo == 0:  # transposição de dígitos nos reais
                reais = str(int(valor))
                trocado = reais[:-2] + reais[-1] + reais[-2] if len(reais) >= 2 else reais
                if trocado == reais:
                    trocado = str(int(reais) + 9)
                valor = Decimal(trocado) + (valor - int(valor))
            elif tipo == 1:  # lançou o valor dos produtos, sem IPI/ST/desconto
                valor = nota.totais.valor_produtos
                if valor == nota.totais.valor_nota:
                    valor += Decimal("0.10")
            else:  # um zero a mais
                valor = valor * 10
            _registrar(lote, "ERP_VALOR_DIVERGENTE", nota)
        if nota in icms_errado:
            icms = arredondar(nota.totais.valor_icms * Decimal("1.5"))
            _registrar(lote, "ERP_ICMS_DIVERGENTE", nota)
        vezes = 2 if nota in duplicadas else 1
        if vezes == 2:
            _registrar(lote, "ERP_DUPLICIDADE", nota)
        for _ in range(vezes):
            doc += rng.randint(1, 9)
            lote.lancamentos.append({
                "numero": nota.numero, "serie": nota.serie, "cnpj": nota.emit_cnpj,
                "valor": valor, "icms": icms,
                "data": nota.data_emissao + timedelta(days=rng.randint(1, 6)), "doc": str(doc),
            })

    # Lançamentos sem XML: números que não existem no lote
    for nota in rng.sample(livres[9:], 2):
        numero = nota.numero + 7
        while any(n.emit_cnpj == nota.emit_cnpj and n.numero == numero for n in lote.notas):
            numero += 1
        doc += rng.randint(1, 9)
        lote.lancamentos.append({
            "numero": numero, "serie": nota.serie, "cnpj": nota.emit_cnpj,
            "valor": arredondar(Decimal(rng.uniform(300, 5000))), "icms": ZERO,
            "data": date(2026, 10, rng.randint(2, 30)), "doc": str(doc),
        })
        _registrar(lote, "ERP_SEM_XML", nota, numero=numero)

    lote.lancamentos.sort(key=lambda x: (x["data"], x["doc"]))


def gerar_lote(qtd_notas: int = 58, seed: int = 2026) -> Lote:
    """Monta o lote em memória (sem tocar o disco)."""
    rng = random.Random(seed)
    lote = _montar_notas(rng, qtd_notas)
    usadas: set[str] = set()
    _plantar_divergencias_xml(lote, rng, usadas)
    _montar_erp(lote, rng, usadas)
    return lote


def salvar_lote(lote: Lote, destino: Path) -> dict[str, Path]:
    destino = Path(destino)
    pasta_xml = destino / "xml"
    pasta_xml.mkdir(parents=True, exist_ok=True)
    for antigo in pasta_xml.glob("*.xml"):
        antigo.unlink()

    for nota in [*lote.notas, *lote.copias]:
        # semente derivada da chave: a cópia de uma nota sai byte a byte igual à original
        conteudo = nota_para_xml(
            nota, lote.emitentes[nota.emit_cnpj], lote.destinatario, lote.unidades,
            hora=lote.horas.get(nota.chave, "10:00:00"), seed_xml=int(nota.chave[25:43]),
        )
        (pasta_xml / nota.arquivo).write_bytes(conteudo)

    caminho_erp = destino / "erp_lancamentos.csv"
    with caminho_erp.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow([COLUNAS[c] for c in ("numero", "serie", "cnpj", "valor", "icms", "data",
                                         "doc")])
        for x in lote.lancamentos:
            w.writerow([x["numero"], x["serie"], formatar_cnpj(x["cnpj"]), formatar_br(x["valor"]),
                        formatar_br(x["icms"]), x["data"].strftime("%d.%m.%Y"), x["doc"]])

    caminho_gabarito = destino / "gabarito.json"
    caminho_gabarito.write_text(
        json.dumps({
            "gerado_em": datetime(2026, 11, 1).isoformat(),
            "observacao": "Divergências plantadas de propósito pelo gerador (dados fictícios).",
            "divergencias": lote.gabarito,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"xml": pasta_xml, "erp": caminho_erp, "gabarito": caminho_gabarito}
