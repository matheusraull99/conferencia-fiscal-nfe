"""Tabelas de referência fiscais (CSV versionados em ``nfe_conf/referencias``).

São SIMPLIFICAÇÕES DIDÁTICAS — veja a seção "Limites" do README. A ideia é que a
regra de negócio fique em dado legível (que o fiscal consegue revisar) e não
enterrada em ``if`` no meio do código.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal
from functools import cache
from importlib import resources


def _ler_csv(nome: str) -> list[dict[str, str]]:
    arquivo = resources.files("nfe_conf").joinpath("referencias", nome)
    with arquivo.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


@dataclass(frozen=True)
class Tabelas:
    uf_por_cuf: dict[str, str]
    cuf_por_uf: dict[str, str]
    aliquota_interestadual: dict[tuple[str, str], Decimal]
    origens_aliquota_4: frozenset[str]
    cfop_grupos: dict[str, dict[str, str]]
    pis_cofins: dict[str, tuple[Decimal, Decimal]]

    def aliquota_icms_interestadual(self, uf_origem: str, uf_destino: str, origem: str) -> Decimal:
        """Alíquota esperada numa operação interestadual (Res. SF 22/1989 e 13/2012)."""
        if uf_origem == uf_destino:
            raise ValueError("Operação interna não tem alíquota interestadual")
        if origem in self.origens_aliquota_4:
            return Decimal("4")
        return self.aliquota_interestadual[(uf_origem, uf_destino)]

    def regime_pis_cofins(self, aliq_pis: Decimal, aliq_cofins: Decimal) -> str | None:
        """Nome do regime cujo par de alíquotas bate, ou None se nenhum bate."""
        for regime, (pis, cofins) in self.pis_cofins.items():
            if aliq_pis == pis and aliq_cofins == cofins:
                return regime
        return None


@cache
def carregar_tabelas() -> Tabelas:
    ufs = _ler_csv("ufs.csv")
    matriz: dict[tuple[str, str], Decimal] = {}
    for linha in _ler_csv("aliquotas_interestaduais.csv"):
        origem = linha.pop("uf_origem")
        for destino, valor in linha.items():
            if valor != "-":
                matriz[(origem, destino)] = Decimal(valor)
    return Tabelas(
        uf_por_cuf={u["cuf"]: u["uf"] for u in ufs},
        cuf_por_uf={u["uf"]: u["cuf"] for u in ufs},
        aliquota_interestadual=matriz,
        origens_aliquota_4=frozenset(
            o["origem"] for o in _ler_csv("origem_mercadoria.csv")
            if o["aliquota_4_res_sf_13_2012"] == "S"
        ),
        cfop_grupos={c["primeiro_digito"]: c for c in _ler_csv("cfop_grupos.csv")},
        pis_cofins={
            p["regime"]: (Decimal(p["aliquota_pis"]), Decimal(p["aliquota_cofins"]))
            for p in _ler_csv("pis_cofins.csv")
        },
    )
