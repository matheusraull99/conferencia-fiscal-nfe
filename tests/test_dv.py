import random

import pytest

from nfe_conf.dv import (
    calcular_dv_chave,
    calcular_dv_cnpj,
    chave_valida,
    cnpj_valido,
    decompor_chave,
    formatar_cnpj,
    gerar_cnpj,
    montar_chave,
)


def test_cnpj_gerado_tem_dv_valido():
    rng = random.Random(1)
    for _ in range(200):
        assert cnpj_valido(gerar_cnpj(rng))


def test_cnpj_com_dv_alterado_e_invalido():
    cnpj = gerar_cnpj(random.Random(2))
    errado = cnpj[:-1] + str((int(cnpj[-1]) + 1) % 10)
    assert not cnpj_valido(errado)


def test_cnpj_aceita_mascara():
    cnpj = gerar_cnpj(random.Random(3))
    assert cnpj_valido(formatar_cnpj(cnpj))
    assert formatar_cnpj(cnpj)[2] == "." and formatar_cnpj(cnpj)[-3] == "-"


@pytest.mark.parametrize("cnpj", ["00000000000000", "11111111111111", "123", "", "ABCDEFGHIJKL12"])
def test_cnpj_invalidos_por_formato(cnpj):
    assert not cnpj_valido(cnpj)


def test_cnpj_alfanumerico_exemplo_da_receita():
    # Exemplo publicado pela Receita Federal para o CNPJ alfanumérico (julho/2026)
    assert calcular_dv_cnpj("12ABC34501DE") == "35"
    assert cnpj_valido("12.ABC.345/01DE-35")
    assert not cnpj_valido("12.ABC.345/01DE-36")


def test_dv_chave_calculado_a_mao():
    # 43 dígitos "1": pesos 2..9 repetidos -> soma 229 -> resto 9 -> DV 2
    assert calcular_dv_chave("1" * 43) == 2


def test_chave_montada_e_valida_e_decompoe():
    cnpj = gerar_cnpj(random.Random(4))
    chave = montar_chave("52", "2610", cnpj, "55", 1, 12345, "1", "87654321")
    assert len(chave) == 44 and chave_valida(chave)
    partes = decompor_chave(chave)
    assert partes["cnpj"] == cnpj
    assert int(partes["numero"]) == 12345
    assert partes["aamm"] == "2610"


def test_chave_com_dv_errado_ou_tamanho_errado():
    chave = montar_chave("35", "2610", gerar_cnpj(random.Random(5)), "55", 1, 1, "1", "1")
    assert not chave_valida(chave[:-1] + str((int(chave[-1]) + 1) % 10))
    assert not chave_valida(chave[:-1])
    assert not chave_valida("A" * 44)
