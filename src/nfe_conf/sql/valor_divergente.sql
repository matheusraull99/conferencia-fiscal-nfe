-- ERP_VALOR_DIVERGENTE: valor lançado diferente do vNF do XML.
SELECT n.chave,
       n.arquivo,
       n.numero,
       n.serie,
       n.emit_cnpj,
       n.emit_nome,
       e.doc_contabil,
       n.valor_total_centavos / 100.0                       AS valor_xml,
       e.valor_centavos / 100.0                             AS valor_erp,
       (e.valor_centavos - n.valor_total_centavos) / 100.0  AS diferenca
FROM notas AS n
JOIN erp_lancamentos AS e
  ON e.emit_cnpj = n.emit_cnpj
 AND e.numero    = n.numero
 AND e.serie     = n.serie
WHERE e.valor_centavos <> n.valor_total_centavos
ORDER BY ABS(e.valor_centavos - n.valor_total_centavos) DESC;
