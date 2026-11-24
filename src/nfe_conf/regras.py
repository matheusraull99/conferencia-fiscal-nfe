"""Catálogo declarativo de regras de conferência.

Cada regra tem código, severidade, descrição e "como corrigir" — o mesmo texto vai
para a planilha, para o relatório executivo e para a aba "Regras". Para criar uma
regra nova basta decorar uma função com ``@regra(...)``; o motor descobre sozinho.

Escopos:
- ``item``: roda uma vez por item da nota  -> ``f(item, nota, tabelas)``
- ``nota``: roda uma vez por nota          -> ``f(nota, tabelas)``
- ``lote``: enxerga todas as notas do lote -> ``f(notas, tabelas)`` devolvendo (nota, achado)
- ``erp`` : cruzamento XML × ERP, executado em SQL (arquivo em ``nfe_conf/sql``)
- ``arquivo``: problema de leitura do arquivo, registrado pelo próprio motor
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from .dv import calcular_dv_chave, chave_valida, cnpj_valido, decompor_chave
from .modelo import ZERO, Item, Nota, arredondar
from .tabelas import Tabelas

TOLERANCIA = Decimal("0.01")


class Severidade(StrEnum):
    ALTA = "ALTA"
    MEDIA = "MÉDIA"
    BAIXA = "BAIXA"


ORDEM_SEVERIDADE = {Severidade.ALTA: 0, Severidade.MEDIA: 1, Severidade.BAIXA: 2}


@dataclass(frozen=True)
class Achado:
    mensagem: str
    esperado: str = ""
    encontrado: str = ""
    item: int | None = None


@dataclass(frozen=True)
class Regra:
    codigo: str
    severidade: Severidade
    descricao: str
    como_corrigir: str
    escopo: str
    funcao: Callable[..., Iterable] | None = None
    consulta_sql: str | None = None


@dataclass
class Divergencia:
    codigo: str
    severidade: str
    descricao: str
    como_corrigir: str
    arquivo: str
    chave: str
    numero: int | None
    serie: int | None
    emit_cnpj: str
    emit_nome: str
    item: int | None
    mensagem: str
    esperado: str = ""
    encontrado: str = ""


CATALOGO: dict[str, Regra] = {}


def regra(
    codigo: str,
    severidade: Severidade,
    descricao: str,
    como_corrigir: str,
    escopo: str,
    consulta_sql: str | None = None,
):
    """Registra uma regra no catálogo. Funciona como decorador ou chamada direta."""

    def registrar(funcao: Callable[..., Iterable] | None) -> Callable[..., Iterable] | None:
        if codigo in CATALOGO:
            raise ValueError(f"Regra duplicada: {codigo}")
        CATALOGO[codigo] = Regra(
            codigo, severidade, descricao, como_corrigir, escopo, funcao, consulta_sql
        )
        return funcao

    return registrar


def nova_divergencia(regra_: Regra, nota: Nota | None, achado: Achado, **extra) -> Divergencia:
    return Divergencia(
        codigo=regra_.codigo,
        severidade=str(regra_.severidade),
        descricao=regra_.descricao,
        como_corrigir=regra_.como_corrigir,
        arquivo=extra.get("arquivo", nota.arquivo if nota else ""),
        chave=extra.get("chave", nota.chave if nota else ""),
        numero=extra.get("numero", nota.numero if nota else None),
        serie=extra.get("serie", nota.serie if nota else None),
        emit_cnpj=extra.get("emit_cnpj", nota.emit_cnpj if nota else ""),
        emit_nome=extra.get("emit_nome", nota.emit_nome if nota else ""),
        item=achado.item,
        mensagem=achado.mensagem,
        esperado=achado.esperado,
        encontrado=achado.encontrado,
    )


def _fmt(valor: Decimal) -> str:
    return f"{valor:.2f}"


def _diferente(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) > TOLERANCIA


CSTS_COM_ICMS_PROPRIO = {"00", "10", "20"}
CSTS_PIS_COFINS_ALIQUOTA = {"01", "02"}


# ================================================================ chave e cadastro


@regra(
    "CHAVE_DV",
    Severidade.ALTA,
    "Chave de acesso com dígito verificador inválido",
    "Recusar o XML e pedir ao fornecedor o arquivo correto; conferir a chave no portal da "
    "NF-e antes de escriturar.",
    "nota",
)
def chave_dv(nota: Nota, tabelas: Tabelas) -> Iterator[Achado]:
    if not chave_valida(nota.chave):
        formato_ok = re.fullmatch(r"\d{44}", nota.chave or "") is not None
        yield Achado(
            f"Chave {nota.chave} não passa no módulo 11"
            if formato_ok else f"Chave {nota.chave!r} não tem 44 dígitos",
            esperado=f"DV {calcular_dv_chave(nota.chave[:43])}" if formato_ok else "44 dígitos",
            encontrado=f"DV {nota.chave[-1]}" if formato_ok else nota.chave,
        )


@regra(
    "CHAVE_CAMPOS",
    Severidade.MEDIA,
    "Chave de acesso não confere com os dados da nota (UF, CNPJ, modelo, série, número)",
    "Verificar se o XML foi editado depois de autorizado; usar o XML baixado do portal.",
    "nota",
)
def chave_campos(nota: Nota, tabelas: Tabelas) -> Iterator[Achado]:
    if not re.fullmatch(r"\d{44}", nota.chave or ""):
        return
    partes = decompor_chave(nota.chave)
    comparacoes = {
        "cUF": (partes["cuf"], nota.cuf),
        "CNPJ": (partes["cnpj"], nota.emit_cnpj),
        "modelo": (partes["modelo"], nota.modelo),
        "série": (int(partes["serie"]), nota.serie),
        "número": (int(partes["numero"]), nota.numero),
    }
    for campo, (na_chave, na_nota) in comparacoes.items():
        if str(na_chave) != str(na_nota):
            yield Achado(
                f"{campo} da chave diferente do XML",
                esperado=str(na_nota),
                encontrado=str(na_chave),
            )


@regra(
    "CNPJ_EMITENTE_DV",
    Severidade.ALTA,
    "CNPJ do emitente com dígito verificador inválido",
    "Conferir o cadastro do fornecedor na Receita (consulta CNPJ) antes de lançar.",
    "nota",
)
def cnpj_emitente(nota: Nota, tabelas: Tabelas) -> Iterator[Achado]:
    if not cnpj_valido(nota.emit_cnpj):
        yield Achado(f"CNPJ {nota.emit_cnpj} inválido", encontrado=nota.emit_cnpj)


@regra(
    "NCM_INVALIDO",
    Severidade.MEDIA,
    "NCM fora do formato (8 dígitos, capítulo 01–97, exceto 77)",
    "Pedir carta de correção ao fornecedor ou ajustar o cadastro do material com o NCM "
    "correto da TIPI.",
    "item",
)
def ncm_invalido(item: Item, nota: Nota, tabelas: Tabelas) -> Iterator[Achado]:
    ncm = item.ncm
    valido = re.fullmatch(r"\d{8}", ncm) is not None and 1 <= int(ncm[:2]) <= 97
    if not valido or ncm[:2] == "77":
        yield Achado(f"NCM {ncm!r} inválido", "8 dígitos, capítulo 01–97", ncm, item.n_item)


# ================================================================ operação / CFOP


@regra(
    "CFOP_OPERACAO",
    Severidade.MEDIA,
    "CFOP incompatível com a operação (5xxx dentro do estado, 6xxx para outro estado)",
    "Pedir carta de correção do CFOP; na escrituração usar o CFOP de entrada equivalente "
    "(1xxx/2xxx).",
    "item",
)
def cfop_operacao(item: Item, nota: Nota, tabelas: Tabelas) -> Iterator[Achado]:
    digito = item.cfop[:1]
    grupo = tabelas.cfop_grupos.get(digito)
    esperado = "6" if nota.interestadual else "5"
    if grupo is None or grupo["fluxo"] != "saida":
        yield Achado(
            f"CFOP {item.cfop} não é de saída do fornecedor",
            f"{esperado}xxx",
            item.cfop,
            item.n_item,
        )
    elif digito in {"5", "6"} and digito != esperado:
        operacao = "interestadual" if nota.interestadual else "interna"
        yield Achado(
            f"Operação {operacao} ({nota.emit_uf}→{nota.dest_uf}) com CFOP {item.cfop}",
            f"{esperado}xxx",
            item.cfop,
            item.n_item,
        )


# ================================================================ ICMS


@regra(
    "ICMS_ALIQ_INTERESTADUAL",
    Severidade.ALTA,
    "Alíquota interestadual de ICMS incorreta para o par de UFs (4%, 7% ou 12%)",
    "Creditar só a alíquota correta e pedir NF complementar/estorno ao fornecedor; crédito "
    "a maior gera glosa e multa.",
    "item",
)
def icms_aliquota_interestadual(item: Item, nota: Nota, tabelas: Tabelas) -> Iterator[Achado]:
    if not nota.interestadual or item.icms_cst not in CSTS_COM_ICMS_PROPRIO:
        return
    esperada = tabelas.aliquota_icms_interestadual(nota.emit_uf, nota.dest_uf, item.icms_origem)
    if item.icms_aliquota != esperada:
        yield Achado(
            f"{nota.emit_uf}→{nota.dest_uf}, origem {item.icms_origem}: alíquota "
            f"{_fmt(item.icms_aliquota)}%",
            f"{_fmt(esperada)}%",
            f"{_fmt(item.icms_aliquota)}%",
            item.n_item,
        )


def base_icms_esperada(item: Item) -> Decimal:
    """vProd − vDesc, com redução de base no CST 20 (frete/seguro/outros por item: fora)."""
    base = item.valor_produto - item.valor_desconto
    if item.icms_cst == "20":
        base = base * (1 - item.icms_reducao_base / 100)
    return arredondar(base)


@regra(
    "ICMS_BASE",
    Severidade.ALTA,
    "Base de cálculo do ICMS diferente da recalculada",
    "Recalcular a base (valor do produto − desconto, aplicando redução quando houver) e "
    "creditar sobre a base correta.",
    "item",
)
def icms_base(item: Item, nota: Nota, tabelas: Tabelas) -> Iterator[Achado]:
    if item.icms_cst not in CSTS_COM_ICMS_PROPRIO:
        return
    esperada = base_icms_esperada(item)
    if _diferente(item.icms_base, esperada):
        yield Achado(
            "Base de ICMS não confere com o valor do item",
            _fmt(esperada),
            _fmt(item.icms_base),
            item.n_item,
        )


@regra(
    "ICMS_VALOR",
    Severidade.ALTA,
    "Valor do ICMS diferente de base × alíquota",
    "Creditar o valor recalculado; se o destaque estiver a maior, solicitar ajuste ao "
    "fornecedor.",
    "item",
)
def icms_valor(item: Item, nota: Nota, tabelas: Tabelas) -> Iterator[Achado]:
    if item.icms_cst not in CSTS_COM_ICMS_PROPRIO:
        return
    esperado = arredondar(item.icms_base * item.icms_aliquota / 100)
    if _diferente(item.icms_valor, esperado):
        yield Achado("vICMS ≠ vBC × pICMS", _fmt(esperado), _fmt(item.icms_valor), item.n_item)


@regra(
    "ICMS_REGIME",
    Severidade.MEDIA,
    "Tributação de ICMS incompatível com o regime do emitente (CRT × CST/CSOSN)",
    "Simples Nacional (CRT 1) usa CSOSN e não destaca ICMS em CSOSN 102; regime normal "
    "(CRT 3) usa CST. Pedir correção ao fornecedor.",
    "item",
)
def icms_regime(item: Item, nota: Nota, tabelas: Tabelas) -> Iterator[Achado]:
    simples = nota.emit_crt in {"1", "2"}
    usa_csosn = len(item.icms_cst) == 3
    if simples != usa_csosn:
        esperado = "CSOSN" if simples else "CST"
        yield Achado(
            f"CRT {nota.emit_crt} com código {item.icms_cst}", esperado, item.icms_cst, item.n_item
        )
    elif item.icms_cst == "102" and item.icms_valor != ZERO:
        yield Achado("CSOSN 102 com ICMS destacado", "0.00", _fmt(item.icms_valor), item.n_item)


# ================================================================ IPI, PIS, COFINS


@regra(
    "IPI_VALOR",
    Severidade.MEDIA,
    "Valor do IPI diferente de base × alíquota",
    "Conferir a alíquota da TIPI para o NCM e o valor destacado; ajustar o custo do item.",
    "item",
)
def ipi_valor(item: Item, nota: Nota, tabelas: Tabelas) -> Iterator[Achado]:
    esperado = arredondar(item.ipi_base * item.ipi_aliquota / 100)
    if _diferente(item.ipi_valor, esperado):
        yield Achado("vIPI ≠ vBC × pIPI", _fmt(esperado), _fmt(item.ipi_valor), item.n_item)


@regra(
    "PIS_COFINS_ALIQUOTA",
    Severidade.MEDIA,
    "Par de alíquotas PIS/COFINS fora dos regimes (0,65/3,00 cumulativo; 1,65/7,60 não "
    "cumulativo)",
    "Confirmar o regime do fornecedor; o crédito do adquirente segue a regra do próprio "
    "regime, não o destaque da nota.",
    "item",
)
def pis_cofins_aliquota(item: Item, nota: Nota, tabelas: Tabelas) -> Iterator[Achado]:
    if item.pis_cst not in CSTS_PIS_COFINS_ALIQUOTA:
        return
    if tabelas.regime_pis_cofins(item.pis_aliquota, item.cofins_aliquota) is None:
        validos = " ou ".join(f"{p}/{c}" for p, c in tabelas.pis_cofins.values())
        yield Achado(
            f"PIS {item.pis_aliquota}% / COFINS {item.cofins_aliquota}% não pertence a nenhum "
            "regime",
            validos,
            f"{item.pis_aliquota}/{item.cofins_aliquota}",
            item.n_item,
        )


@regra(
    "PIS_COFINS_VALOR",
    Severidade.MEDIA,
    "Valor de PIS ou COFINS diferente de base × alíquota",
    "Recalcular PIS/COFINS sobre a base informada e ajustar o crédito.",
    "item",
)
def pis_cofins_valor(item: Item, nota: Nota, tabelas: Tabelas) -> Iterator[Achado]:
    for nome, base, aliq, valor in (
        ("PIS", item.pis_base, item.pis_aliquota, item.pis_valor),
        ("COFINS", item.cofins_base, item.cofins_aliquota, item.cofins_valor),
    ):
        esperado = arredondar(base * aliq / 100)
        if _diferente(valor, esperado):
            yield Achado(f"v{nome} ≠ vBC × p{nome}", _fmt(esperado), _fmt(valor), item.n_item)


# ================================================================ totais


@regra(
    "TOTAL_NOTA",
    Severidade.ALTA,
    "Soma dos itens diferente do total da nota (ICMSTot)",
    "Não lançar pelo total do cabeçalho: conferir item a item e pedir NF substituta ou "
    "complementar ao fornecedor.",
    "nota",
)
def total_nota(nota: Nota, tabelas: Tabelas) -> Iterator[Achado]:
    t = nota.totais
    soma = {
        "vProd": sum((i.valor_produto for i in nota.itens), ZERO),
        "vDesc": sum((i.valor_desconto for i in nota.itens), ZERO),
        "vBC": sum((i.icms_base for i in nota.itens), ZERO),
        "vICMS": sum((i.icms_valor for i in nota.itens), ZERO),
        "vST": sum((i.icms_st_valor for i in nota.itens), ZERO),
        "vIPI": sum((i.ipi_valor for i in nota.itens), ZERO),
        "vPIS": sum((i.pis_valor for i in nota.itens), ZERO),
        "vCOFINS": sum((i.cofins_valor for i in nota.itens), ZERO),
    }
    soma["vNF"] = (
        soma["vProd"] - soma["vDesc"] + soma["vST"] + soma["vIPI"]
        + t.valor_frete + t.valor_seguro + t.valor_outros
    )
    informado = {
        "vProd": t.valor_produtos,
        "vDesc": t.valor_desconto,
        "vBC": t.base_icms,
        "vICMS": t.valor_icms,
        "vST": t.valor_st,
        "vIPI": t.valor_ipi,
        "vPIS": t.valor_pis,
        "vCOFINS": t.valor_cofins,
        "vNF": t.valor_nota,
    }
    campos = [c for c in soma if _diferente(soma[c], informado[c])]
    if campos:
        yield Achado(
            "Total divergente em " + ", ".join(campos),
            "; ".join(f"{c}={_fmt(soma[c])}" for c in campos),
            "; ".join(f"{c}={_fmt(informado[c])}" for c in campos),
        )


# ================================================================ lote


@regra(
    "NOTA_DUPLICADA",
    Severidade.ALTA,
    "Mesma nota (mesma chave) recebida em mais de um arquivo",
    "Escriturar uma única vez; arquivar a cópia. Risco de crédito e pagamento em dobro.",
    "lote",
)
def nota_duplicada(notas: list[Nota], tabelas: Tabelas) -> Iterator[tuple[Nota, Achado]]:
    primeira: dict[str, Nota] = {}
    for nota in notas:
        if nota.chave in primeira:
            original = primeira[nota.chave]
            yield nota, Achado(
                f"Cópia de {original.arquivo}", esperado="1 arquivo", encontrado=nota.arquivo
            )
        else:
            primeira[nota.chave] = nota


# ================================================================ leitura do arquivo

regra(
    "XML_ILEGIVEL",
    Severidade.ALTA,
    "Arquivo que não pôde ser lido como NF-e",
    "Baixar novamente o XML no portal da NF-e ou pedir ao fornecedor.",
    "arquivo",
)(None)


# ================================================================ cruzamento com o ERP (SQL)

regra(
    "ERP_NAO_LANCADA",
    Severidade.ALTA,
    "Nota com XML recebido e sem lançamento no ERP",
    "Lançar a nota no período correto (atenção a prazo de crédito e a pagamento sem título).",
    "erp",
    "notas_sem_lancamento.sql",
)(None)
regra(
    "ERP_SEM_XML",
    Severidade.ALTA,
    "Lançamento no ERP sem XML correspondente",
    "Localizar o XML (portal/manifestação do destinatário) ou estornar o lançamento.",
    "erp",
    "lancamentos_sem_nota.sql",
)(None)
regra(
    "ERP_DUPLICIDADE",
    Severidade.ALTA,
    "Mesma nota lançada mais de uma vez no ERP",
    "Estornar o lançamento excedente antes do pagamento e da apuração.",
    "erp",
    "lancamentos_duplicados.sql",
)(None)
regra(
    "ERP_VALOR_DIVERGENTE",
    Severidade.ALTA,
    "Valor lançado no ERP diferente do vNF do XML",
    "Corrigir o lançamento pelo XML (o XML autorizado é o documento fiscal válido).",
    "erp",
    "valor_divergente.sql",
)(None)
regra(
    "ERP_ICMS_DIVERGENTE",
    Severidade.MEDIA,
    "ICMS lançado no ERP diferente do ICMS destacado no XML",
    "Ajustar o crédito de ICMS no ERP antes do fechamento da apuração.",
    "erp",
    "icms_divergente.sql",
)(None)


def regras_por_escopo(escopo: str) -> list[Regra]:
    return [r for r in CATALOGO.values() if r.escopo == escopo]
