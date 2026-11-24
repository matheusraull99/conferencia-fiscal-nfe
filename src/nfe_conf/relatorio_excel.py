"""Planilha de conferência (openpyxl): Resumo, Divergências, Notas sem lançamento,
Lançamentos sem nota e Regras."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from .dv import formatar_cnpj
from .motor import Resultado
from .regras import CATALOGO

COR_CABECALHO = PatternFill("solid", fgColor="1F3864")
FONTE_CABECALHO = Font(bold=True, color="FFFFFF")
CORES_SEVERIDADE = {
    "ALTA": PatternFill("solid", fgColor="F8CBAD"),
    "MÉDIA": PatternFill("solid", fgColor="FFE699"),
    "BAIXA": PatternFill("solid", fgColor="C6EFCE"),
}
FORMATO_MOEDA = "#,##0.00"


def _tabela(ws: Worksheet, cabecalho: list[str], linhas: list[list], larguras: list[int],
            linha_inicial: int = 1, colunas_moeda: tuple[int, ...] = ()) -> None:
    for col, titulo in enumerate(cabecalho, start=1):
        celula = ws.cell(row=linha_inicial, column=col, value=titulo)
        celula.fill = COR_CABECALHO
        celula.font = FONTE_CABECALHO
        celula.alignment = Alignment(vertical="center", wrap_text=True)
    for i, linha in enumerate(linhas, start=linha_inicial + 1):
        for col, valor in enumerate(linha, start=1):
            celula = ws.cell(row=i, column=col, value=valor)
            if col in colunas_moeda:
                celula.number_format = FORMATO_MOEDA
    for col, largura in enumerate(larguras, start=1):
        ws.column_dimensions[get_column_letter(col)].width = largura
    ultima = linha_inicial + max(len(linhas), 1)
    ws.auto_filter.ref = f"A{linha_inicial}:{get_column_letter(len(cabecalho))}{ultima}"
    ws.freeze_panes = ws.cell(row=linha_inicial + 1, column=1)


def _aba_resumo(ws: Worksheet, r: Resultado) -> None:
    ws.title = "Resumo"
    ws["A1"] = "Conferência fiscal de entrada — NF-e × ERP"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = f"Gerado em {r.gerado_em:%d/%m/%Y %H:%M}"
    valor_total = sum(float(n.totais.valor_nota) for n in r.notas)
    sev = r.contagem_por_severidade()
    indicadores = [
        ("Arquivos XML lidos", r.arquivos_lidos),
        ("Notas únicas", len(r.notas)),
        ("Valor total das notas (R$)", valor_total),
        ("Lançamentos no ERP", len(r.lancamentos)),
        ("Divergências", len(r.divergencias)),
        ("  severidade ALTA", sev["ALTA"]),
        ("  severidade MÉDIA", sev["MÉDIA"]),
        ("Notas sem lançamento", len(r.notas_sem_lancamento)),
        ("Lançamentos sem nota", len(r.lancamentos_sem_nota)),
    ]
    for i, (rotulo, valor) in enumerate(indicadores, start=4):
        ws.cell(row=i, column=1, value=rotulo).font = Font(bold=not rotulo.startswith(" "))
        celula = ws.cell(row=i, column=2, value=valor)
        if isinstance(valor, float):
            celula.number_format = FORMATO_MOEDA
    inicio = 4 + len(indicadores) + 2
    linhas = [
        [x["codigo"], x["severidade"], x["descricao"], x["ocorrencias"]]
        for x in r.resumo_por_regra
    ]
    _tabela(ws, ["Regra", "Severidade", "Descrição", "Ocorrências"], linhas,
            [30, 12, 80, 12], linha_inicial=inicio)
    for i, linha in enumerate(linhas, start=inicio + 1):
        if linha[3]:
            ws.cell(row=i, column=2).fill = CORES_SEVERIDADE[linha[1]]


def _aba_divergencias(ws: Worksheet, r: Resultado) -> None:
    cabecalho = ["Severidade", "Regra", "Descrição", "Arquivo", "Nº NF", "Série",
                 "CNPJ emitente", "Emitente", "Item", "Mensagem", "Esperado", "Encontrado",
                 "Como corrigir"]
    linhas = [
        [d.severidade, d.codigo, d.descricao, d.arquivo, d.numero, d.serie,
         formatar_cnpj(d.emit_cnpj), d.emit_nome, d.item, d.mensagem, d.esperado,
         d.encontrado, d.como_corrigir]
        for d in r.divergencias
    ]
    _tabela(ws, cabecalho, linhas, [11, 24, 45, 52, 9, 7, 20, 34, 6, 50, 22, 22, 60])
    for i, d in enumerate(r.divergencias, start=2):
        cor = CORES_SEVERIDADE[d.severidade]
        for col in range(1, len(cabecalho) + 1):
            ws.cell(row=i, column=col).fill = cor


def _aba_sem_lancamento(ws: Worksheet, r: Resultado) -> None:
    linhas = [
        [x["numero"], x["serie"], formatar_cnpj(x["emit_cnpj"]), x["emit_nome"],
         x["data_emissao"], x["valor_nota"], x["chave"], x["arquivo"]]
        for x in r.notas_sem_lancamento
    ]
    _tabela(ws, ["Nº NF", "Série", "CNPJ emitente", "Emitente", "Emissão", "Valor (R$)",
                 "Chave de acesso", "Arquivo"], linhas, [9, 7, 20, 34, 12, 14, 48, 52],
            colunas_moeda=(6,))


def _aba_sem_nota(ws: Worksheet, r: Resultado) -> None:
    linhas = [
        [x["doc_contabil"], x["linha"], x["numero"], x["serie"], formatar_cnpj(x["emit_cnpj"]),
         x["valor_lancado"], x["data_lancamento"]]
        for x in r.lancamentos_sem_nota
    ]
    _tabela(ws, ["Doc. contábil", "Linha ERP", "Nº NF", "Série", "CNPJ emitente",
                 "Valor lançado (R$)", "Data lançamento"], linhas,
            [14, 10, 9, 7, 20, 18, 16], colunas_moeda=(6,))


def _aba_regras(ws: Worksheet) -> None:
    linhas = [
        [r.codigo, str(r.severidade), r.escopo, r.descricao, r.como_corrigir]
        for r in CATALOGO.values()
    ]
    _tabela(ws, ["Regra", "Severidade", "Escopo", "Descrição", "Como corrigir"], linhas,
            [26, 11, 9, 70, 90])


def gerar_excel(resultado: Resultado, caminho: Path) -> Path:
    wb = Workbook()
    _aba_resumo(wb.active, resultado)
    _aba_divergencias(wb.create_sheet("Divergências"), resultado)
    _aba_sem_lancamento(wb.create_sheet("Notas sem lançamento"), resultado)
    _aba_sem_nota(wb.create_sheet("Lançamentos sem nota"), resultado)
    _aba_regras(wb.create_sheet("Regras"))
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    wb.save(caminho)
    return caminho
