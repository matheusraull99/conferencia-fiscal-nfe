"""Leitura do relatório de notas lançadas exportado do ERP (estilo ALV do SAP).

Formato esperado: CSV separado por ``;``, números no padrão brasileiro
(``1.234,56``), datas ``dd.mm.aaaa`` e CNPJ com ou sem máscara. Cabeçalho:

    Nº NF-e;Série;CNPJ Emitente;Valor NF;ICMS;Dt.Lçto;Nº Doc.
"""

from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .dv import limpar_cnpj
from .modelo import Lancamento

COLUNAS = {
    "numero": "Nº NF-e",
    "serie": "Série",
    "cnpj": "CNPJ Emitente",
    "valor": "Valor NF",
    "icms": "ICMS",
    "data": "Dt.Lçto",
    "doc": "Nº Doc.",
}


class ErroLeituraERP(Exception):
    pass


def valor_br(texto: str) -> Decimal:
    """'1.234,56' -> Decimal('1234.56'). Aceita sinal e espaços."""
    limpo = (texto or "").strip().replace(".", "").replace(",", ".")
    try:
        return Decimal(limpo or "0")
    except InvalidOperation as exc:
        raise ErroLeituraERP(f"Valor inválido: {texto!r}") from exc


def formatar_br(valor: Decimal) -> str:
    """Decimal('1234.56') -> '1.234,56' (como o SAP exporta)."""
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def ler_erp(caminho: Path) -> list[Lancamento]:
    with Path(caminho).open(encoding="utf-8-sig", newline="") as f:
        leitor = csv.DictReader(f, delimiter=";")
        faltando = [c for c in COLUNAS.values() if c not in (leitor.fieldnames or [])]
        if faltando:
            raise ErroLeituraERP(f"Colunas ausentes no export do ERP: {', '.join(faltando)}")
        lancamentos = []
        for linha, registro in enumerate(leitor, start=2):  # linha 1 é o cabeçalho
            try:
                lancamentos.append(
                    Lancamento(
                        linha=linha,
                        doc_contabil=registro[COLUNAS["doc"]].strip(),
                        numero=int(registro[COLUNAS["numero"]]),
                        serie=int(registro[COLUNAS["serie"]]),
                        emit_cnpj=limpar_cnpj(registro[COLUNAS["cnpj"]]),
                        valor=valor_br(registro[COLUNAS["valor"]]),
                        icms=valor_br(registro[COLUNAS["icms"]]),
                        data_lancamento=datetime.strptime(
                            registro[COLUNAS["data"]].strip(), "%d.%m.%Y"
                        ).date(),
                    )
                )
            except (ValueError, ErroLeituraERP) as exc:
                raise ErroLeituraERP(f"Linha {linha} do ERP: {exc}") from exc
    return lancamentos
