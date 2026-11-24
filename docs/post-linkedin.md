# Post do LinkedIn

## Post (sem link no corpo)

Conferir nota fiscal de entrada no olho é o custo do fechamento que ninguém vê.

Trabalho com automação e RPA, e a rotina que mais escuto do time fiscal é sempre a mesma: abrir o XML, conferir CFOP, alíquota, base do ICMS, PIS/COFINS, depois ir ao ERP ver se a nota foi lançada e pelo valor certo. Nota a nota, no fim do mês.

Então montei um robô de conferência fiscal de entrada como projeto de portfólio:

→ lê os XMLs de NF-e (layout 4.00)
→ recalcula ICMS, IPI, PIS e COFINS item a item
→ confere alíquota interestadual (4/7/12%), CFOP 5xxx × 6xxx, NCM, chave de acesso e soma dos itens
→ cruza com o relatório do ERP em SQL: nota sem lançamento, lançamento sem nota, duplicidade e valor divergente
→ entrega uma planilha com cor por severidade e um resumo executivo

Para testar de verdade, gerei 60 notas fictícias e plantei 32 erros de propósito. O robô achou os 32, sem nenhum falso positivo, e essa conferência virou teste automatizado.

Cada regra tem código, severidade e "como corrigir", escritos de um jeito que o fiscal revisa sem precisar ler Python.

É didático: ST completa, DIFAL e benefícios fiscais ficaram de fora, e o README diz isso com todas as letras.

Se você trabalha no fiscal: qual conferência ainda toma mais o seu tempo?

O link do repositório está no primeiro comentário.

#AutomaçãoFiscal #RPA #Python #SQL #NFe

## Primeiro comentário

Repositório com o código, os XMLs fictícios e o relatório de exemplo (roda em 2 comandos): https://github.com/matheusraull99/conferencia-fiscal-nfe
