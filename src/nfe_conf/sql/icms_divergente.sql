-- ERP_ICMS_DIVERGENTE: ICMS lançado diferente do ICMS destacado no XML.
-- Só compara lançamentos cujo valor total bate (senão o problema é outro).
SELECT n.chave,
       n.arquivo,
       n.numero,
       n.serie,
       n.emit_cnpj,
       n.emit_nome,
       e.doc_contabil,
       n.icms_centavos / 100.0                       AS icms_xml,
       e.icms_centavos / 100.0                       AS icms_erp,
       (e.icms_centavos - n.icms_centavos) / 100.0   AS diferenca
FROM notas AS n
JOIN erp_lancamentos AS e
  ON e.emit_cnpj = n.emit_cnpj
 AND e.numero    = n.numero
 AND e.serie     = n.serie
WHERE e.valor_centavos = n.valor_total_centavos
  AND e.icms_centavos <> n.icms_centavos
ORDER BY ABS(e.icms_centavos - n.icms_centavos) DESC;
