-- Quantas divergências cada regra encontrou (inclui regras com zero ocorrências).
SELECT r.codigo,
       r.severidade,
       r.escopo,
       r.descricao,
       COUNT(d.id) AS ocorrencias
FROM regras AS r
LEFT JOIN divergencias AS d ON d.codigo = r.codigo
GROUP BY r.codigo, r.severidade, r.escopo, r.descricao
ORDER BY ocorrencias DESC,
         CASE r.severidade WHEN 'ALTA' THEN 0 WHEN 'MÉDIA' THEN 1 ELSE 2 END,
         r.codigo;
