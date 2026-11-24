"""Relatório executivo em Markdown — o que o gestor lê em 1 minuto."""

from __future__ import annotations

from pathlib import Path

from .dv import formatar_cnpj
from .motor import Resultado


def _moeda(valor: float) -> str:
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def gerar_markdown(r: Resultado) -> str:
    sev = r.contagem_por_severidade()
    valor_total = sum(float(n.totais.valor_nota) for n in r.notas)
    valor_sem_lanc = sum(x["valor_nota"] for x in r.notas_sem_lancamento)
    notas_com_problema = {
        (d.emit_cnpj, d.numero, d.serie) for d in r.divergencias if d.numero is not None
    }

    linhas = [
        "# Conferência fiscal de entrada — relatório executivo",
        "",
        f"_Gerado em {r.gerado_em:%d/%m/%Y %H:%M}_",
        "",
        "## Em números",
        "",
        f"- **{r.arquivos_lidos}** arquivos XML lidos → **{len(r.notas)}** notas únicas "
        f"({_moeda(valor_total)})",
        f"- **{len(r.lancamentos)}** lançamentos no export do ERP",
        f"- **{len(r.divergencias)}** divergências: **{sev['ALTA']}** de severidade ALTA e "
        f"**{sev['MÉDIA']}** MÉDIA",
        f"- **{len(notas_com_problema)}** notas/lançamentos distintos com pelo menos uma "
        "divergência",
        f"- **{len(r.notas_sem_lancamento)}** notas sem lançamento ({_moeda(valor_sem_lanc)}) "
        f"e **{len(r.lancamentos_sem_nota)}** lançamentos sem XML",
        "",
        "## Divergências por regra",
        "",
        "| Regra | Severidade | Ocorrências | O que é |",
        "|---|---|---:|---|",
    ]
    for x in r.resumo_por_regra:
        if x["ocorrencias"]:
            linhas.append(
                f"| `{x['codigo']}` | {x['severidade']} | {x['ocorrencias']} | {x['descricao']} |"
            )
    zeradas = [x["codigo"] for x in r.resumo_por_regra if not x["ocorrencias"]]
    if zeradas:
        linhas += ["", "Regras sem ocorrência neste lote: " + ", ".join(f"`{c}`" for c in zeradas)]

    linhas += ["", "## Fornecedores com mais divergências", "",
               "| Fornecedor | CNPJ | UF | Notas | Divergências |", "|---|---|---|---:|---:|"]
    for x in [e for e in r.resumo_por_emitente if e["divergencias"]][:5]:
        linhas.append(
            f"| {x['emit_nome']} | {formatar_cnpj(x['emit_cnpj'])} | {x['emit_uf']} | "
            f"{x['notas']} | {x['divergencias']} |"
        )

    linhas += [
        "",
        "## Próximos passos sugeridos",
        "",
        "1. Tratar primeiro as divergências **ALTA** (crédito indevido, duplicidade, nota sem "
        "lançamento).",
        "2. Pedir carta de correção/NF complementar aos fornecedores do ranking acima.",
        "3. Ajustar no ERP os lançamentos com valor ou ICMS divergente antes do fechamento.",
        "",
        "_Detalhe linha a linha na planilha Excel gerada junto com este relatório._",
        "",
    ]
    return "\n".join(linhas)


def salvar_markdown(r: Resultado, caminho: Path) -> Path:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(gerar_markdown(r), encoding="utf-8")
    return caminho
