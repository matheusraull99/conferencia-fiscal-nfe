"""Estruturas de dados da conferência. Valores monetários sempre em ``Decimal``."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal("0")
CENTAVO = Decimal("0.01")


def arredondar(valor: Decimal) -> Decimal:
    """Arredondamento comercial em 2 casas (o mesmo que o emissor usa)."""
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def centavos(valor: Decimal) -> int:
    return int(arredondar(valor) * 100)


@dataclass
class Item:
    n_item: int
    codigo: str
    descricao: str
    ncm: str
    cfop: str
    quantidade: Decimal
    valor_unitario: Decimal
    valor_produto: Decimal
    valor_desconto: Decimal = ZERO
    # ICMS — ``icms_cst`` guarda o CST (2 dígitos) ou o CSOSN (3 dígitos, Simples)
    icms_origem: str = "0"
    icms_cst: str = ""
    icms_base: Decimal = ZERO
    icms_reducao_base: Decimal = ZERO
    icms_aliquota: Decimal = ZERO
    icms_valor: Decimal = ZERO
    icms_st_base: Decimal = ZERO
    icms_st_valor: Decimal = ZERO
    ipi_base: Decimal = ZERO
    ipi_aliquota: Decimal = ZERO
    ipi_valor: Decimal = ZERO
    pis_cst: str = ""
    pis_base: Decimal = ZERO
    pis_aliquota: Decimal = ZERO
    pis_valor: Decimal = ZERO
    cofins_cst: str = ""
    cofins_base: Decimal = ZERO
    cofins_aliquota: Decimal = ZERO
    cofins_valor: Decimal = ZERO


@dataclass
class Totais:
    base_icms: Decimal = ZERO
    valor_icms: Decimal = ZERO
    base_st: Decimal = ZERO
    valor_st: Decimal = ZERO
    valor_produtos: Decimal = ZERO
    valor_frete: Decimal = ZERO
    valor_seguro: Decimal = ZERO
    valor_desconto: Decimal = ZERO
    valor_ipi: Decimal = ZERO
    valor_pis: Decimal = ZERO
    valor_cofins: Decimal = ZERO
    valor_outros: Decimal = ZERO
    valor_nota: Decimal = ZERO


@dataclass
class Nota:
    arquivo: str
    chave: str
    numero: int
    serie: int
    modelo: str
    data_emissao: date
    cuf: str
    id_dest: str
    natureza_operacao: str
    tp_emis: str
    cnf: str
    emit_cnpj: str
    emit_nome: str
    emit_uf: str
    emit_crt: str
    dest_cnpj: str
    dest_nome: str
    dest_uf: str
    itens: list[Item] = field(default_factory=list)
    totais: Totais = field(default_factory=Totais)

    @property
    def interestadual(self) -> bool:
        return self.emit_uf != self.dest_uf


@dataclass
class Lancamento:
    """Uma linha do relatório de notas lançadas exportado do ERP."""

    linha: int
    doc_contabil: str
    numero: int
    serie: int
    emit_cnpj: str
    valor: Decimal
    icms: Decimal
    data_lancamento: date
