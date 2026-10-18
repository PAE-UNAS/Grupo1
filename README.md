# UNAS: Pesquisa sobre Estresse Térmico em Heliópolis
## Requisitos
RF
- Extrair dados das APIs públicas via REST
- Limpar as bases (valores ausentes, outliers, padronização de unidades e timestamps)
- Cruzar variáveis
- Calcular índices de estresse térmico a partir de variáveis brutas
- Gerar análises exploratórias (correlações, séries temporais, distribuições)
- Disponibilizar dashboards interativos com filtros por período e recorte territorial
- Permitir exportação dos resultados (relatórios/gráficos) para uso comunitário
  
RNF
- Compartilhamento de conhecimento com a ONG
- Acessibilidade (resultados apresentados em linguagem clara e visual)
- Reprodutibilidade (ambiente virtualizado em Docker e versionamento em Git)
- Manutenibilidade(código comentado e documentado)
- Confiabilidade dos dados (rastreabilidade da origem e validação de qualidade das bases)
- Escalabilidade (arquitetura que comporte novos sensores e novas fontes de dados)
- Sustentabilidade (documentação de operação e garantia de continuidade sem
dependência da equipe original)
