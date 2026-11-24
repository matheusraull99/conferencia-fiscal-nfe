-- ERP_NAO_LANCADA: XML recebido que não tem nenhum lançamento no ERP.
SELECT n.chave,
       n.arquivo,
       n.numero,
       n.serie,
       n.emit_cnpj,
       n.emit_nome,
       n.data_emissao,
       n.valor_total_centavos / 100.0 AS valor_nota
FROM notas AS n
LEFT JOIN erp_lancamentos AS e
       ON e.emit_cnpj = n.emit_cnpj
      AND e.numero    = n.numero
      AND e.serie     = n.serie
WHERE e.id IS NULL
ORDER BY n.data_emissao, n.emit_cnpj, n.numero;
