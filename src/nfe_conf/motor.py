"""Orquestra a conferência: lê XMLs, aplica as regras, carrega o SQLite e cruza com o ERP."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import banco
from .erp import ler_erp
from .modelo import Lancamento, Nota
from .parser import ErroLeituraXML, ler_arquivo
from .regras import (
    CATALOGO,
    ORDEM_SEVERIDADE,
    Achado,
    Divergencia,
    Severidade,
    nova_divergencia,
    regras_por_escopo,
)
from .tabelas import Tabelas, carregar_tabelas


@dataclass
class Resultado:
    arquivos_lidos: int
    notas: list[Nota]  # notas únicas (cópias fora)
    lancamentos: list[Lancamento]
    divergencias: list[Divergencia]
    notas_sem_lancamento: list[dict]
    lancamentos_sem_nota: list[dict]
    resumo_por_regra: list[dict]
    resumo_por_emitente: list[dict]
    gerado_em: datetime = field(default_factory=datetime.now)

    def contagem_por_regra(self) -> dict[str, int]:
        return {r["codigo"]: r["ocorrencias"] for r in self.resumo_por_regra}

    def contagem_por_severidade(self) -> dict[str, int]:
        contagem = {str(s): 0 for s in Severidade}
        for d in self.divergencias:
            contagem[d.severidade] += 1
        return contagem


def aplicar_regras(notas: list[Nota], tabelas: Tabelas | None = None) -> list[Divergencia]:
    """Roda as regras de lote em todas as notas e as de nota/item nas notas únicas."""
    tabelas = tabelas or carregar_tabelas()
    divergencias: list[Divergencia] = []

    for r in regras_por_escopo("lote"):
        for nota, achado in r.funcao(notas, tabelas):
            divergencias.append(nova_divergencia(r, nota, achado))

    vistas: set[str] = set()
    for nota in notas:
        if nota.chave in vistas:
            continue  # a cópia já foi apontada por NOTA_DUPLICADA; não conta em dobro
        vistas.add(nota.chave)
        for r in regras_por_escopo("nota"):
            divergencias.extend(nova_divergencia(r, nota, a) for a in r.funcao(nota, tabelas))
        for item in nota.itens:
            for r in regras_por_escopo("item"):
                divergencias.extend(
                    nova_divergencia(r, nota, a) for a in r.funcao(item, nota, tabelas)
                )
    return divergencias


def _data_br(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%d/%m/%Y")


def _divergencias_erp(con: sqlite3.Connection, nomes: dict[str, str]) -> list[Divergencia]:
    def div(codigo: str, linha: dict, achado: Achado) -> Divergencia:
        return nova_divergencia(
            CATALOGO[codigo],
            None,
            achado,
            arquivo=linha.get("arquivo") or "",
            chave=linha.get("chave") or "",
            numero=linha["numero"],
            serie=linha["serie"],
            emit_cnpj=linha["emit_cnpj"],
            emit_nome=linha.get("emit_nome") or nomes.get(linha["emit_cnpj"], ""),
        )

    saida = []
    for linha in banco.consultar(con, "notas_sem_lancamento.sql"):
        saida.append(div("ERP_NAO_LANCADA", linha, Achado(
            f"Emitida em {_data_br(linha['data_emissao'])}, sem lançamento",
            esperado="1 lançamento", encontrado="nenhum",
        )))
    for linha in banco.consultar(con, "lancamentos_sem_nota.sql"):
        saida.append(div("ERP_SEM_XML", linha, Achado(
            f"Doc. {linha['doc_contabil']} (linha {linha['linha']} do ERP) sem XML no lote",
            esperado="XML da nota", encontrado=f"{linha['valor_lancado']:.2f} lançado",
        )))
    for linha in banco.consultar(con, "lancamentos_duplicados.sql"):
        saida.append(div("ERP_DUPLICIDADE", linha, Achado(
            f"{linha['qtd_lancamentos']} lançamentos: docs {linha['documentos']}",
            esperado="1", encontrado=str(linha["qtd_lancamentos"]),
        )))
    for linha in banco.consultar(con, "valor_divergente.sql"):
        saida.append(div("ERP_VALOR_DIVERGENTE", linha, Achado(
            f"Doc. {linha['doc_contabil']}: diferença de {linha['diferenca']:.2f}",
            esperado=f"{linha['valor_xml']:.2f}", encontrado=f"{linha['valor_erp']:.2f}",
        )))
    for linha in banco.consultar(con, "icms_divergente.sql"):
        saida.append(div("ERP_ICMS_DIVERGENTE", linha, Achado(
            f"Doc. {linha['doc_contabil']}: diferença de {linha['diferenca']:.2f}",
            esperado=f"{linha['icms_xml']:.2f}", encontrado=f"{linha['icms_erp']:.2f}",
        )))
    return saida


def _ordenar(d: Divergencia) -> tuple:
    return (ORDEM_SEVERIDADE[Severidade(d.severidade)], d.codigo, d.emit_cnpj, d.numero or 0,
            d.item or 0)


def conferir(pasta_xml: Path, caminho_erp: Path, caminho_db: str | Path = ":memory:") -> Resultado:
    pasta_xml, caminho_erp = Path(pasta_xml), Path(caminho_erp)
    if str(caminho_db) != ":memory:":
        Path(caminho_db).parent.mkdir(parents=True, exist_ok=True)
        Path(caminho_db).unlink(missing_ok=True)

    arquivos = sorted(pasta_xml.glob("*.xml"))
    notas: list[Nota] = []
    divergencias: list[Divergencia] = []
    for caminho in arquivos:
        try:
            notas.append(ler_arquivo(caminho))
        except ErroLeituraXML as exc:
            divergencias.append(nova_divergencia(
                CATALOGO["XML_ILEGIVEL"], None, Achado(str(exc)),
                arquivo=caminho.name, chave="", numero=None, serie=None,
                emit_cnpj="", emit_nome="",
            ))

    divergencias.extend(aplicar_regras(notas))
    lancamentos = ler_erp(caminho_erp)

    con = banco.criar_banco(str(caminho_db))
    try:
        banco.carregar_notas(con, notas)
        banco.carregar_lancamentos(con, lancamentos)
        nomes = {n.emit_cnpj: n.emit_nome for n in notas}
        divergencias.extend(_divergencias_erp(con, nomes))
        divergencias.sort(key=_ordenar)
        banco.gravar_divergencias(con, divergencias)
        con.commit()
        unicas = {n.chave: n for n in reversed(notas)}  # primeira ocorrência vence
        return Resultado(
            arquivos_lidos=len(arquivos),
            notas=[n for n in notas if unicas[n.chave] is n],
            lancamentos=lancamentos,
            divergencias=divergencias,
            notas_sem_lancamento=banco.consultar(con, "notas_sem_lancamento.sql"),
            lancamentos_sem_nota=banco.consultar(con, "lancamentos_sem_nota.sql"),
            resumo_por_regra=banco.consultar(con, "resumo_por_regra.sql"),
            resumo_por_emitente=banco.consultar(con, "resumo_por_emitente.sql"),
        )
    finally:
        con.close()
