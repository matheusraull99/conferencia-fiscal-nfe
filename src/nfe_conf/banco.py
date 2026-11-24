"""Carga em SQLite e execução das consultas de conferência (arquivos ``.sql``)."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict
from importlib import resources

from .modelo import Lancamento, Nota, centavos
from .regras import CATALOGO, Divergencia


def ler_sql(nome: str) -> str:
    return resources.files("nfe_conf").joinpath("sql", nome).read_text(encoding="utf-8")


def criar_banco(caminho: str = ":memory:") -> sqlite3.Connection:
    con = sqlite3.connect(caminho)
    con.row_factory = sqlite3.Row
    con.executescript(ler_sql("schema.sql"))
    con.executemany(
        "INSERT OR REPLACE INTO regras VALUES (?, ?, ?, ?, ?)",
        [
            (r.codigo, str(r.severidade), r.escopo, r.descricao, r.como_corrigir)
            for r in CATALOGO.values()
        ],
    )
    return con


def carregar_notas(con: sqlite3.Connection, notas: list[Nota]) -> None:
    """Grava notas únicas (pela chave) e itens. Cópias entram só na tabela ``arquivos``."""
    for nota in notas:
        con.execute("INSERT OR IGNORE INTO arquivos VALUES (?, ?)", (nota.arquivo, nota.chave))
        cursor = con.execute(
            "INSERT OR IGNORE INTO notas VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                nota.chave,
                nota.arquivo,
                nota.numero,
                nota.serie,
                nota.emit_cnpj,
                nota.emit_nome,
                nota.emit_uf,
                nota.dest_uf,
                nota.data_emissao.isoformat(),
                centavos(nota.totais.valor_nota),
                centavos(nota.totais.valor_icms),
            ),
        )
        if cursor.rowcount == 0:  # cópia de nota já carregada
            continue
        con.executemany(
            "INSERT INTO itens VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    nota.chave,
                    i.n_item,
                    i.codigo,
                    i.descricao,
                    i.ncm,
                    i.cfop,
                    i.icms_cst,
                    float(i.icms_aliquota),
                    centavos(i.valor_produto),
                    centavos(i.icms_valor),
                )
                for i in nota.itens
            ],
        )


def carregar_lancamentos(con: sqlite3.Connection, lancamentos: list[Lancamento]) -> None:
    con.executemany(
        "INSERT INTO erp_lancamentos (linha, doc_contabil, numero, serie, emit_cnpj, "
        "valor_centavos, icms_centavos, data_lancamento) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                lanc.linha,
                lanc.doc_contabil,
                lanc.numero,
                lanc.serie,
                lanc.emit_cnpj,
                centavos(lanc.valor),
                centavos(lanc.icms),
                lanc.data_lancamento.isoformat(),
            )
            for lanc in lancamentos
        ],
    )


def gravar_divergencias(con: sqlite3.Connection, divergencias: list[Divergencia]) -> None:
    campos = (
        "codigo", "severidade", "arquivo", "chave", "numero", "serie",
        "emit_cnpj", "emit_nome", "item", "mensagem", "esperado", "encontrado",
    )
    con.executemany(
        f"INSERT INTO divergencias ({', '.join(campos)}) VALUES ({', '.join('?' * len(campos))})",
        [tuple(asdict(d)[c] for c in campos) for d in divergencias],
    )


def consultar(con: sqlite3.Connection, nome_sql: str) -> list[dict]:
    """Executa um arquivo de ``nfe_conf/sql`` e devolve as linhas como dicionários."""
    return [dict(linha) for linha in con.execute(ler_sql(nome_sql))]
