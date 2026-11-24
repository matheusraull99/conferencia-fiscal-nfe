-- ERP_SEM_XML: lançamento no ERP sem XML correspondente no lote.
SELECT e.linha,
       e.doc_contabil,
       e.numero,
       e.serie,
       e.emit_cnpj,
       e.valor_centavos / 100.0 AS valor_lancado,
       e.data_lancamento
FROM erp_lancamentos AS e
LEFT JOIN notas AS n
       ON n.emit_cnpj = e.emit_cnpj
      AND n.numero    = e.numero
      AND n.serie     = e.serie
WHERE n.chave IS NULL
ORDER BY e.data_lancamento, e.linha;
