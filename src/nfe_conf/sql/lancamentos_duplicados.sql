-- ERP_DUPLICIDADE: a mesma nota (CNPJ + número + série) lançada mais de uma vez.
SELECT e.emit_cnpj,
       e.numero,
       e.serie,
       COUNT(*)                                   AS qtd_lancamentos,
       GROUP_CONCAT(e.doc_contabil, ', ')         AS documentos,
       SUM(e.valor_centavos) / 100.0              AS valor_total_lancado,
       n.chave,
       n.arquivo,
       n.emit_nome
FROM erp_lancamentos AS e
LEFT JOIN notas AS n
       ON n.emit_cnpj = e.emit_cnpj
      AND n.numero    = e.numero
      AND n.serie     = e.serie
GROUP BY e.emit_cnpj, e.numero, e.serie
HAVING COUNT(*) > 1
ORDER BY qtd_lancamentos DESC, e.emit_cnpj, e.numero;
