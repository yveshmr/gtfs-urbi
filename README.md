# URBI — Operação em tempo real

Plataforma operacional para acompanhamento da frota, visualização de posição e
rota, consulta de ETA e apoio à decisão do Centro de Controle Operacional (CCO).

O sistema combina a programação de transporte com os dados operacionais da
frota para apresentar uma visão única da operação. A interface foi desenhada
para permitir que o operador identifique rapidamente atrasos, veículos que
exigem atenção e oportunidades de troca no mesmo terminal.

## O que o sistema oferece

- visão gerencial da operação atual;
- mapa da frota com posição projetada, rota e situação do veículo;
- tabela detalhada e filtrável de todos os veículos;
- ETA até a próxima parada e até o fim da viagem;
- comparação entre chegada planejada e prevista;
- alertas de falta de atualização e baixa velocidade prolongada;
- recomendações de troca de veículos organizadas por terminal;
- acompanhamento do prazo disponível para cada decisão;
- registro de análise, assunção, execução ou recusa de um grupo de trocas;
- histórico local das decisões e dos motivos de recusa.

## Requisitos para execução local

Antes de iniciar, instale:

- [Git](https://git-scm.com/downloads);
- [Docker Desktop](https://www.docker.com/products/docker-desktop/);
- [Visual Studio Code](https://code.visualstudio.com/).

O Docker Desktop precisa estar aberto e com o mecanismo de contêineres em
execução.

## Primeira execução no Git Bash

Abra o Git Bash e entre na pasta do projeto:

```bash
cd /d/Projetos/gtfs-on-time
```

Crie o arquivo local de configuração a partir do modelo:

```bash
cp .env.example .env
code .env
```

Preencha no VS Code os dados locais do PostgreSQL e as credenciais fornecidas
para a integração Cittati. Salve e feche o arquivo.

> O `.env` contém informações confidenciais, é ignorado pelo Git e nunca deve
> ser enviado ao repositório, copiado para o README ou compartilhado em logs.

Construa e inicie a aplicação:

```bash
docker compose up -d --build
```

Na primeira execução, o Docker baixa as imagens necessárias, cria o banco,
aplica as migrações e constrói o frontend. Por isso, ela pode demorar mais que
as próximas inicializações.

Confira o estado dos serviços:

```bash
docker compose ps
```

Os serviços `database`, `api` e `frontend` devem aparecer como `healthy`.
O `worker` deve aparecer como ativo. O serviço `migrate` encerra com código
zero depois de atualizar o banco; esse comportamento é normal.

## Acessar a plataforma

Com os serviços ativos, abra:

- interface operacional: [http://127.0.0.1:5173](http://127.0.0.1:5173);
- documentação interativa da API: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs);
- estado da API: [http://127.0.0.1:8000/health/ready](http://127.0.0.1:8000/health/ready).

O menu lateral pode ser aberto ou recolhido pelo botão de menu no canto
superior esquerdo. A seleção do veículo e o tipo de mapa escolhido permanecem
ao longo das atualizações da tela.

## Como utilizar a interface

### Visão geral

É a tela inicial do CCO e apresenta o estado consolidado da operação no
momento. Os cartões funcionam também como atalhos para as telas detalhadas.

Principais indicadores:

- **Frota monitorada:** veículos com posição operacional disponível;
- **Pontualidade ETA:** proporção dos veículos comparáveis que estão no horário;
- **Atenção:** veículos com atraso previsto de até 10 minutos;
- **Atrasos críticos:** veículos com atraso previsto superior a 10 minutos;
- **Sem ETA comparável:** veículos que ainda não possuem referência suficiente;
- **Viagens ameaçadas:** próximas viagens que podem começar atrasadas;
- **Grupos pendentes:** grupos de troca que aguardam decisão do operador;
- **Tempo recuperável:** redução potencial de atraso com as recomendações atuais.

Os filtros de linha, terminal de destino e situação alteram os indicadores da
visão gerencial. A tela também mostra:

- prioridades da frota, ordenadas por criticidade;
- terminais e linhas com maior concentração de atraso;
- impacto potencial das prescrições;
- fila das próximas decisões operacionais.

### Mapa

O mapa mostra somente a posição operacional atual; ele não é um reprodutor do
histórico de posições.

As cores principais são:

- **azul:** veículo no horário ou sem atraso crítico;
- **laranja:** veículo em atenção;
- **vermelho:** veículo atrasado;
- **aro cinza:** veículo sem atualização há mais de 5 minutos;
- **aro laranja:** veículo abaixo de 1 km/h há mais de 5 minutos.

É possível alternar entre os mapas **Neutro**, **Escuro** e **Satélite** sem
chave de API no frontend.

Ao selecionar um veículo, o sistema apresenta sua rota e destaca:

- trecho já percorrido;
- trecho restante;
- subtrecho atual;
- paradas e terminais;
- posição projetada do veículo.

O painel do veículo mostra linha, destino, velocidade, qualidade da posição,
próxima parada, chegada prevista, atraso e ETA até o terminal. Quando existir
um alerta operacional, ele também aparece nesse painel.

### Frota

Esta tela concentra a visão veículo a veículo. A linha inteira recebe uma cor
leve de fundo de acordo com a situação operacional, facilitando a varredura
visual.

Cada coluna pode ser:

- filtrada individualmente;
- ordenada em ordem crescente ou decrescente;
- combinada com filtros das demais colunas.

Use o filtro da própria coluna **Status** para localizar, por exemplo,
`Sem atualização` ou `Abaixo de 1 km/h`. A seleção de uma linha abre o
veículo no mapa com os detalhes correspondentes.

Interpretação dos estados da frota:

- **No horário / adiantado:** chegada prevista dentro da referência atual;
- **Até 10 minutos:** exige acompanhamento, mas ainda não é atraso crítico;
- **Atraso crítico:** atraso previsto superior a 10 minutos;
- **Sem referência:** não existe comparação operacional suficiente naquele
  momento.

### Prescrições

A tela de prescrições possui duas visões complementares:

1. **Plano de trocas:** apresenta os grupos fechados de forma visual e orientada
   à decisão;
2. **Tabela completa:** permite consultar, filtrar e ordenar todas as ações de
   cada grupo.

Cada grupo apresenta:

- terminal e veículos envolvidos;
- sequência completa das trocas;
- veículo recomendado para cada próxima viagem;
- linha, destino e posição programada;
- chegada planejada e chegada prevista;
- saída planejada e folga disponível;
- atraso original, atraso residual e tempo recuperável;
- confiança operacional disponível;
- prazo restante para a decisão.

O **prazo para decisão** indica quanto tempo resta até a saída planejada da
viagem que exige intervenção. Um prazo vencido aparece destacado e o grupo
passa a ser mostrado como expirado quando não existe mais tempo operacional
para a ação.

## Fluxo de decisão por grupo

Uma recomendação de troca é sempre confirmada para o grupo completo. Não é
possível executar ou recusar apenas uma das linhas de um ciclo, pois as ações
dependem umas das outras.

Estados disponíveis:

- **Nova:** recomendação disponível e ainda não analisada;
- **Em análise:** alguém iniciou a avaliação do grupo;
- **Assumida:** um operador assumiu a responsabilidade pela decisão;
- **Executada:** todas as orientações do grupo foram confirmadas;
- **Recusada:** o grupo completo não será aplicado;
- **Expirada:** o prazo operacional terminou antes de uma decisão final.

Fluxo recomendado para o operador:

1. confira o terminal, o prazo e o impacto esperado;
2. revise toda a sequência de veículos do grupo;
3. selecione **Colocar em análise** ou **Assumir grupo**;
4. comunique todas as trocas envolvidas;
5. selecione **Confirmar execução conjunta** somente após concluir as
   orientações;
6. se o grupo não puder ser aplicado, selecione **Recusar grupo** e registre um
   motivo objetivo.

Todas as mudanças de estado exigem o nome ou a matrícula do responsável. Uma
recusa exige também o motivo. Grupos executados aparecem em verde no fim da
lista; grupos recusados permanecem identificados em vermelho para consulta e
auditoria.

## Alertas operacionais

### Sem atualização por mais de 5 minutos

Indica que a posição recebida do veículo está antiga. Antes de tomar uma ação
baseada em ETA, o operador deve verificar a comunicação ou confirmar a posição
por outro meio operacional.

### Abaixo de 1 km/h por mais de 5 minutos

Indica permanência em velocidade muito baixa. Pode representar parada,
retenção, congestionamento, embarque prolongado ou outra condição da operação.
O alerta não determina sozinho a causa; ele sinaliza que o veículo precisa ser
avaliado.

Um veículo pode apresentar os dois alertas simultaneamente. A visão geral
mostra a quantidade de veículos afetados e oferece atalhos para a tabela já
filtrada.

## Atualização das informações

- as posições operacionais são consultadas continuamente;
- a tela de frota recebe atualizações automáticas;
- os indicadores e as recomendações são renovados periodicamente;
- o horário da última atualização aparece no cabeçalho;
- o botão **Atualizar agora** força uma nova leitura da interface.

A atualização automática não remove a seleção atual do veículo nem altera o
mapa-base escolhido pelo usuário.

## Rotina sugerida para o CCO

1. abra a **Visão geral** e confira atrasos críticos, alertas e grupos pendentes;
2. abra as prioridades mais críticas no **Mapa**;
3. use a **Frota** para investigar veículos, linhas ou terminais específicos;
4. acesse **Prescrições** e trate primeiro os grupos com menor prazo;
5. registre o responsável e o estado de cada decisão;
6. confirme a execução apenas depois de orientar o grupo completo;
7. reavalie a visão geral após cada ciclo de decisões.

## Comandos do dia a dia

Iniciar novamente sem reconstruir as imagens:

```bash
docker compose up -d
```

Reconstruir após atualizar o código:

```bash
docker compose up -d --build
```

Verificar o estado dos serviços:

```bash
docker compose ps
```

Observar a ingestão da Cittati:

```bash
docker compose logs -f worker
```

Observar a API:

```bash
docker compose logs -f api
```

Pressione `Ctrl+C` para sair da visualização dos logs. Isso não desliga os
serviços.

Parar a aplicação preservando banco, contêineres e volume:

```bash
docker compose stop
```

> Não use `docker compose down -v` na rotina operacional. A opção `-v` remove
> o volume do PostgreSQL e pode apagar os dados locais.

## Solução de problemas

### A página não abre

Confira o Docker Desktop e execute:

```bash
docker compose ps
docker compose up -d
```

### A API não está pronta

```bash
curl http://127.0.0.1:8000/health/ready
docker compose logs --tail=100 api
```

### A frota não atualiza

```bash
docker compose logs --tail=100 worker
```

Verifique se o `worker` está ativo e se o `.env` contém os valores corretos
da integração. Nunca envie o conteúdo desse arquivo em chamados ou commits.

### O banco ou uma migração falhou

```bash
docker compose logs --tail=100 database migrate
```

Não apague o volume para tentar corrigir uma falha. Preserve os logs sem
credenciais e encaminhe o erro para análise técnica.

## Serviços utilizados

- **frontend:** React, TypeScript, Vite, Nginx e MapLibre;
- **api:** FastAPI;
- **worker:** ingestão e atualização operacional contínua;
- **database:** PostgreSQL com PostGIS;
- **migrate:** aplicação automática das migrações Alembic.

As credenciais da Cittati permanecem somente no backend. O navegador não recebe
senha, token ou conteúdo do `.env`.
