-- Ranking de fornecedores por quantidade de divergências.
SELECT n.emit_cnpj,
       n.emit_nome,
       n.emit_uf,
       COUNT(DISTINCT n.chave)                           AS notas,
       SUM(n.valor_total_centavos) / 100.0               AS valor_notas,
       (SELECT COUNT(*) FROM divergencias AS d
         WHERE d.emit_cnpj = n.emit_cnpj)                AS divergencias
FROM notas AS n
GROUP BY n.emit_cnpj, n.emit_nome, n.emit_uf
ORDER BY divergencias DESC, valor_notas DESC;
