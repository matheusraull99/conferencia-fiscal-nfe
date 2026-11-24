"""Dígitos verificadores de CNPJ e da chave de acesso da NF-e (módulo 11).

O CNPJ aceita também o formato alfanumérico (IN RFB 2.229/2024, vigente desde
julho/2026): cada caractere vale ``ord(c) - 48``, de modo que dígitos continuam
valendo 0–9 e letras A–Z passam a valer 17–42. Os dois DVs continuam numéricos.
"""

from __future__ import annotations

import random
import re

_PESOS_CNPJ_DV1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
_PESOS_CNPJ_DV2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]


def _valor(caractere: str) -> int:
    return ord(caractere) - 48


def _dv_mod11(texto: str, pesos: list[int]) -> int:
    soma = sum(_valor(c) * p for c, p in zip(texto, pesos, strict=True))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def limpar_cnpj(cnpj: str) -> str:
    """Remove máscara (pontos, barra, hífen) e padroniza em maiúsculas."""
    return re.sub(r"[^0-9A-Za-z]", "", cnpj or "").upper()


def calcular_dv_cnpj(base12: str) -> str:
    """Recebe as 12 primeiras posições (raiz + filial) e devolve os 2 DVs."""
    base12 = limpar_cnpj(base12)
    if not re.fullmatch(r"[0-9A-Z]{12}", base12):
        raise ValueError(f"Base de CNPJ inválida: {base12!r}")
    dv1 = _dv_mod11(base12, _PESOS_CNPJ_DV1)
    dv2 = _dv_mod11(base12 + str(dv1), _PESOS_CNPJ_DV2)
    return f"{dv1}{dv2}"


def cnpj_valido(cnpj: str) -> bool:
    """True se o CNPJ (numérico ou alfanumérico) tem formato e DVs corretos."""
    c = limpar_cnpj(cnpj)
    if not re.fullmatch(r"[0-9A-Z]{12}[0-9]{2}", c):
        return False
    if len(set(c)) == 1:  # 00000000000000, 11111111111111... passam no DV mas não existem
        return False
    return calcular_dv_cnpj(c[:12]) == c[12:]


def formatar_cnpj(cnpj: str) -> str:
    c = limpar_cnpj(cnpj)
    if len(c) != 14:
        return cnpj
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"


def gerar_cnpj(rng: random.Random, filial: int = 1) -> str:
    """Gera um CNPJ numérico FICTÍCIO com DV válido (raiz aleatória)."""
    base = f"{rng.randrange(10**7, 10**8):08d}{filial:04d}"
    return base + calcular_dv_cnpj(base)


# ---------------------------------------------------------------- chave de acesso


def calcular_dv_chave(chave43: str) -> int:
    """DV da chave de acesso: módulo 11 com pesos 2..9 da direita para a esquerda."""
    if not re.fullmatch(r"\d{43}", chave43):
        raise ValueError(f"A base da chave precisa de 43 dígitos: {chave43!r}")
    soma = 0
    peso = 2
    for digito in reversed(chave43):
        soma += int(digito) * peso
        peso = 2 if peso == 9 else peso + 1
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def chave_valida(chave: str) -> bool:
    if not re.fullmatch(r"\d{44}", chave or ""):
        return False
    return calcular_dv_chave(chave[:43]) == int(chave[43])


def montar_chave(
    cuf: str, aamm: str, cnpj: str, modelo: str, serie: int, numero: int, tp_emis: str, cnf: str
) -> str:
    """Monta a chave de 44 dígitos: cUF+AAMM+CNPJ+mod+série+nNF+tpEmis+cNF+cDV."""
    base = f"{int(cuf):02d}{aamm}{limpar_cnpj(cnpj)}{int(modelo):02d}{serie:03d}{numero:09d}"
    base += f"{tp_emis}{int(cnf):08d}"
    return base + str(calcular_dv_chave(base))


def decompor_chave(chave: str) -> dict[str, str]:
    """Quebra a chave nos campos que ela carrega (útil para conferir contra o <ide>)."""
    return {
        "cuf": chave[0:2],
        "aamm": chave[2:6],
        "cnpj": chave[6:20],
        "modelo": chave[20:22],
        "serie": chave[22:25],
        "numero": chave[25:34],
        "tp_emis": chave[34],
        "cnf": chave[35:43],
        "dv": chave[43],
    }
