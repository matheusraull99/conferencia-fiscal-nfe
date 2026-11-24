"""Linha de comando ``nfe-conf``.

    nfe-conf conferir --xml exemplos/xml --erp exemplos/erp_lancamentos.csv --saida relatorio.xlsx
    nfe-conf gerar-exemplo --destino exemplos
    nfe-conf regras
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .erp import ErroLeituraERP
from .regras import CATALOGO


def _conferir(args: argparse.Namespace) -> int:
    from .motor import conferir
    from .relatorio_excel import gerar_excel
    from .relatorio_md import salvar_markdown

    pasta = Path(args.xml)
    if not pasta.is_dir():
        print(f"Pasta de XML não encontrada: {pasta}", file=sys.stderr)
        return 2
    try:
        resultado = conferir(pasta, Path(args.erp), args.db or ":memory:")
    except (FileNotFoundError, ErroLeituraERP) as exc:
        print(f"Erro ao ler o export do ERP: {exc}", file=sys.stderr)
        return 2

    saida = gerar_excel(resultado, Path(args.saida))
    md = salvar_markdown(resultado, Path(args.md) if args.md else saida.with_suffix(".md"))

    sev = resultado.contagem_por_severidade()
    print(f"{resultado.arquivos_lidos} XMLs lidos | {len(resultado.notas)} notas únicas | "
          f"{len(resultado.lancamentos)} lançamentos no ERP")
    print(f"{len(resultado.divergencias)} divergências "
          f"(ALTA: {sev['ALTA']}, MÉDIA: {sev['MÉDIA']})")
    for linha in resultado.resumo_por_regra:
        if linha["ocorrencias"]:
            print(f"  {linha['codigo']:<26} {linha['ocorrencias']:>3}")
    print(f"Planilha: {saida}")
    print(f"Relatório executivo: {md}")
    if args.db:
        print(f"Base SQLite: {args.db}")
    return 1 if args.falhar_se_alta and sev["ALTA"] else 0


def _gerar_exemplo(args: argparse.Namespace) -> int:
    from .gerador import gerar_lote, salvar_lote

    lote = gerar_lote(qtd_notas=args.notas, seed=args.seed)
    caminhos = salvar_lote(lote, Path(args.destino))
    total = len(lote.notas) + len(lote.copias)
    print(f"{total} XMLs em {caminhos['xml']}")
    print(f"{len(lote.lancamentos)} lançamentos em {caminhos['erp']}")
    print(f"{len(lote.gabarito)} divergências plantadas em {caminhos['gabarito']}")
    return 0


def _regras(_: argparse.Namespace) -> int:
    for r in CATALOGO.values():
        print(f"{r.codigo:<26} {r.severidade!s:<6} {r.escopo:<8} {r.descricao}")
    return 0


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nfe-conf", description="Conferência fiscal de entrada: NF-e (XML) × regras × ERP."
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("conferir", help="Confere uma pasta de XMLs contra o export do ERP")
    p.add_argument("--xml", required=True, help="Pasta com os XMLs de NF-e")
    p.add_argument("--erp", required=True, help="CSV exportado do ERP (separador ;)")
    p.add_argument("--saida", default="relatorio.xlsx", help="Planilha de saída (.xlsx)")
    p.add_argument("--md", help="Relatório executivo (.md); padrão: ao lado da planilha")
    p.add_argument("--db", help="Grava a base SQLite neste arquivo (padrão: só em memória)")
    p.add_argument("--falhar-se-alta", action="store_true",
                   help="Sai com código 1 se houver divergência ALTA (útil em agendamento)")
    p.set_defaults(func=_conferir)

    g = sub.add_parser("gerar-exemplo", help="Gera um lote fictício com divergências plantadas")
    g.add_argument("--destino", default="exemplos")
    g.add_argument("--notas", type=int, default=58, help="Notas únicas (mais 2 cópias)")
    g.add_argument("--seed", type=int, default=2026)
    g.set_defaults(func=_gerar_exemplo)

    r = sub.add_parser("regras", help="Lista o catálogo de regras")
    r.set_defaults(func=_regras)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = construir_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
