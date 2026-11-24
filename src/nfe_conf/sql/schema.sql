-- Esquema da base de conferência (SQLite).
-- Dinheiro em CENTAVOS (INTEGER): comparação exata, sem erro de ponto flutuante.

CREATE TABLE IF NOT EXISTS notas (
    chave                 TEXT PRIMARY KEY,
    arquivo               TEXT NOT NULL,
    numero                INTEGER NOT NULL,
    serie                 INTEGER NOT NULL,
    emit_cnpj             TEXT NOT NULL,
    emit_nome             TEXT,
    emit_uf               TEXT,
    dest_uf               TEXT,
    data_emissao          TEXT NOT NULL,          -- ISO 8601 (AAAA-MM-DD)
    valor_total_centavos  INTEGER NOT NULL,       -- ICMSTot/vNF
    icms_centavos         INTEGER NOT NULL        -- ICMSTot/vICMS
);

-- Todos os arquivos lidos, inclusive cópias da mesma nota.
CREATE TABLE IF NOT EXISTS arquivos (
    arquivo  TEXT PRIMARY KEY,
    chave    TEXT
);

CREATE TABLE IF NOT EXISTS itens (
    chave                 TEXT NOT NULL REFERENCES notas(chave),
    n_item                INTEGER NOT NULL,
    codigo                TEXT,
    descricao             TEXT,
    ncm                   TEXT,
    cfop                  TEXT,
    cst_icms              TEXT,
    aliquota_icms         REAL,
    valor_produto_centavos INTEGER,
    icms_centavos         INTEGER,
    PRIMARY KEY (chave, n_item)
);

CREATE TABLE IF NOT EXISTS erp_lancamentos (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    linha             INTEGER NOT NULL,           -- linha no CSV exportado
    doc_contabil      TEXT,
    numero            INTEGER NOT NULL,
    serie             INTEGER NOT NULL,
    emit_cnpj         TEXT NOT NULL,
    valor_centavos    INTEGER NOT NULL,
    icms_centavos     INTEGER NOT NULL,
    data_lancamento   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS divergencias (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo        TEXT NOT NULL,
    severidade    TEXT NOT NULL,
    arquivo       TEXT,
    chave         TEXT,
    numero        INTEGER,
    serie         INTEGER,
    emit_cnpj     TEXT,
    emit_nome     TEXT,
    item          INTEGER,
    mensagem      TEXT,
    esperado      TEXT,
    encontrado    TEXT
);

CREATE TABLE IF NOT EXISTS regras (
    codigo        TEXT PRIMARY KEY,
    severidade    TEXT NOT NULL,
    escopo        TEXT NOT NULL,
    descricao     TEXT NOT NULL,
    como_corrigir TEXT NOT NULL
);

-- A chave de negócio do cruzamento é (CNPJ do emitente, número, série):
-- é o que o ERP guarda; a chave de acesso nem sempre é digitada no lançamento.
CREATE INDEX IF NOT EXISTS ix_notas_negocio ON notas (emit_cnpj, numero, serie);
CREATE INDEX IF NOT EXISTS ix_erp_negocio   ON erp_lancamentos (emit_cnpj, numero, serie);
