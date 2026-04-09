# GTFS Live • Monitoramento Operacional

Sistema de monitoramento operacional para transporte coletivo baseado em **GTFS estático** e **GTFS Realtime**, com backend em **FastAPI** e frontend em **React + Vite + Leaflet**.

O projeto foi estruturado para acompanhar a operação em tempo real, exibindo:

- veículos ativos no mapa;
- progresso dos veículos ao longo do shape;
- subtrechos com velocidades médias;
- comparação entre comportamento **realtime** e **histórico**;
- visão em tabela com enriquecimento operacional, incluindo ETA e dados auxiliares da viagem.

O foco é uma visão de **controle operacional**, e não uma interface para passageiro final.

---

## Sumário

- [Visão geral](#visão-geral)
- [Principais recursos](#principais-recursos)
- [Arquitetura do projeto](#arquitetura-do-projeto)
- [Estrutura de pastas](#estrutura-de-pastas)
- [Tecnologias utilizadas](#tecnologias-utilizadas)
- [Fontes de dados](#fontes-de-dados)
- [Pré-requisitos](#pré-requisitos)
- [Configuração do ambiente](#configuração-do-ambiente)
- [Como executar](#como-executar)
- [Variáveis de ambiente](#variáveis-de-ambiente)
- [Fluxo de funcionamento](#fluxo-de-funcionamento)
- [Endpoints principais](#endpoints-principais)
- [Tela e camadas do frontend](#tela-e-camadas-do-frontend)
- [Histórico e cache](#histórico-e-cache)
- [Integração com Cittati](#integração-com-cittati)
- [Testes e scripts auxiliares](#testes-e-scripts-auxiliares)
- [Empacotamento desktop](#empacotamento-desktop)
- [Boas práticas para publicar no GitHub](#boas-práticas-para-publicar-no-github)
- [Problemas conhecidos](#problemas-conhecidos)
- [Próximos passos](#próximos-passos)
- [Licença](#licença)

---

## Visão geral

Este repositório implementa uma plataforma de monitoramento em tempo real para a operação de ônibus da URBI, a partir de dados GTFS e GTFS-RT. O backend baixa, normaliza e mantém em memória os dados operacionais, enquanto o frontend exibe essas informações de forma visual em mapa e tabela.

A aplicação também constrói uma base de **subtrechos canônicos** entre paradas consecutivas e calcula métricas operacionais como:

- velocidade média por subtrecho;
- progresso do veículo ao longo do shape;
- ETA estimado com múltiplas fontes;
- comparação entre velocidade atual e referência histórica.

---

## Principais recursos

### Backend

- Download e atualização automática do **GTFS estático**.
- Leitura do feed **GTFS Realtime Vehicle Positions**.
- Normalização de shapes, paradas, rotas, viagens e stop times.
- Cálculo de progresso e posição do veículo ao longo do shape.
- Construção da base de **subtrechos ALL**.
- Geração de comparação **histórico × realtime**.
- API REST com endpoints de mapa, tabela, debug e saúde.
- Enriquecimento opcional com dados da **Cittati**.

### Frontend

- Mapa interativo com **React Leaflet**.
- Camada de veículos em tempo real.
- Camadas de subtrechos por pares, all speed e comparação histórica.
- Legendas visuais por faixa de velocidade e criticidade.
- Tela de lista com ordenação, filtros e colunas colapsáveis.
- Atualização periódica dos dados consumidos da API.

---

## Arquitetura do projeto

A arquitetura é dividida em dois blocos principais:

### 1. Backend (`app/`)
Responsável por:

- baixar e armazenar GTFS estático;
- carregar arquivos GTFS em memória;
- atualizar periodicamente os veículos do GTFS-RT;
- montar índices auxiliares como `shape_stop_sequence` e `route_shapes`;
- calcular subtrechos, estatísticas e ETA;
- servir os dados para o frontend via FastAPI.

### 2. Frontend (`frontend/`)
Responsável por:

- renderizar mapa e lista;
- buscar os dados do backend via HTTP;
- exibir camadas operacionais com cores, popups e filtros;
- alternar entre visão cartográfica e tabular.

---

## Estrutura de pastas

```text
.
├── app/
│   ├── api/                  # Rotas FastAPI
│   ├── core/                 # Configuração central e estado global
│   ├── geometry/             # Funções geométricas
│   ├── integrations/         # Integrações externas (ex.: Cittati)
│   ├── services/             # Regras de negócio, loaders e cálculos
│   └── static/               # Estruturas derivadas do GTFS
├── frontend/
│   ├── public/               # Arquivos públicos
│   └── src/                  # Código React
├── gtfs_core/                # Núcleo de pipelines e lógica de subtrechos
├── legacy/                   # Código legado/monolítico
├── tests/                    # Scripts de teste e demonstração
├── scripts/                  # Scripts auxiliares
├── run_app.py                # Inicializador conjunto backend + frontend
├── requirements.txt          # Dependências Python
├── package.json              # Dependências raiz do ambiente Node
└── GTFS-URBI.spec            # Especificação para empacotamento
```

---

## Tecnologias utilizadas

### Backend

- Python 3
- FastAPI
- Uvicorn
- Pandas
- NumPy
- Shapely
- Geopy
- Requests / HTTPX
- `gtfs-realtime-bindings`

### Frontend

- React 18
- Vite
- React Leaflet
- Leaflet
- ESLint

---

## Fontes de dados

O projeto consome dados públicos e integrações auxiliares.

### GTFS estático
Usado para carregar:

- shapes;
- stops;
- routes;
- trips;
- stop_times.

### GTFS Realtime Vehicle Positions
Usado para atualizar periodicamente:

- posição do veículo;
- trip atual;
- route_id;
- direction_id;
- velocidade e metadados de operação.

### Base histórica local
Arquivos CSV em `data/subtrechos/` podem ser usados para montar a referência histórica de subtrechos.

### Integração Cittati
Quando configurada, a API também enriquece a visão tabular com dados de viagem ativa por prefixo, como:

- início programado;
- início realizado;
- fim programado;
- atendimento;
- atividade;
- tabela;
- ponto de início e fim.

---

## Pré-requisitos

Antes de executar o projeto, tenha instalado:

### Backend
- Python 3.10 ou superior
- `pip`

### Frontend
- Node.js 18+ recomendado
- `npm`

### Opcional
- Git
- ambiente virtual Python (`venv`)

---

## Configuração do ambiente

### 1. Clone o repositório

```bash
git clone https://github.com/yveshmr/gtfs-urbi
cd gtfs-urbi
```

### 2. Crie e ative um ambiente virtual Python

No Windows:

```bash
py -m venv .venv
.venv\Scripts\activate
```

No Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Instale as dependências do backend

```bash
pip install -r requirements.txt
```

### 4. Instale as dependências do frontend

```bash
cd frontend
npm install
cd ..
```

---

## Como executar

Há duas formas principais de subir o sistema.

### Opção A — executar backend e frontend separadamente

#### Backend
Na raiz do projeto:

```bash
uvicorn app.main:app --reload
```

O backend ficará disponível em:

```text
http://127.0.0.1:8000
```

#### Frontend
Em outro terminal:

```bash
cd frontend
npm run dev
```

O frontend normalmente ficará disponível em:

```text
http://localhost:5173
```

---

### Opção B — executar pelo inicializador `run_app.py`

Esse script sobe:

- o backend FastAPI;
- o frontend Vite;
- e abre o navegador automaticamente.

```bash
py run_app.py
```

> Observação: o `run_app.py` foi escrito com foco em ambiente Windows e usa um caminho fixo para o `npm.cmd`. Pode ser necessário adaptar esse arquivo se o Node estiver instalado em outro local.

---

## Variáveis de ambiente

O projeto reconhece as seguintes variáveis:

### `DATA_DIR`
Permite sobrescrever o diretório base de dados locais.

Exemplo:

```bash
set DATA_DIR=D:\dados\gtfs-urbi
```

ou em Linux/macOS:

```bash
export DATA_DIR=/opt/gtfs-urbi/data
```

Se não for definida, o projeto usa:

```text
<data_do_projeto>/data
```

### `CITTATI_USER`
Usuário para integração com Cittati.

### `CITTATI_PASS`
Senha para integração com Cittati.

Sem essas variáveis, a aplicação continua funcionando, mas sem enriquecimento da visão tabular pela Cittati.

---

## Fluxo de funcionamento

### Startup do backend
Na inicialização, o backend executa o seguinte fluxo:

1. garante que o GTFS estático esteja disponível localmente;
2. carrega shapes e normaliza distância acumulada ao longo do shape;
3. carrega `stop_times`, `stops`, `routes` e `trips`;
4. constrói o índice `route_shapes`;
5. constrói `shape_stop_sequence`;
6. monta a base de `subtrechos_all`;
7. monta a base histórica de comparação;
8. executa a primeira atualização de veículos;
9. inicia loops assíncronos de atualização de veículos e persistência de subtrechos.

### Atualização contínua
Após o startup:

- os veículos são atualizados em loop a cada ~10 segundos;
- o frontend consulta os dados do mapa periodicamente;
- a tabela consulta endpoint próprio com campos enriquecidos.

---

## Endpoints principais

Abaixo estão os endpoints mais importantes já identificados no projeto.

### Saúde

#### `GET /health`
Retorna o estado básico da aplicação.

Exemplo de resposta:

```json
{
  "status": "ok",
  "vehicles": 123,
  "subtrechos_all": 456
}
```

---

### Mapa e tabela

#### `GET /map/vehicles`
Retorna a lista de veículos ativos para uso no mapa.

Campos típicos:

- `vehicle_id`
- `vehicle_label`
- `route_id`
- `route_short_name`
- `trip_id`
- `direction_id`
- `stop_id`
- `lat`
- `lon`
- `shape_id`
- `shape_pos_m`
- `progress`
- `speed_kmh`
- `last_update_ts`
- `status`
- `heading_deg`

#### `GET /map/vehicles/table`
Retorna a visão de tabela com enriquecimento adicional.

Campos extras relevantes:

- `current_subtrecho_index`
- `remaining_subtrechos_count`
- `eta_seconds`
- `eta_ts_iso`
- `eta_sources`
- `origin_stop_name`
- `destination_stop_name`
- `origin_stop_desc`
- `destination_stop_desc`
- campos opcionais da integração Cittati

---

### Subtrechos

#### `GET /map/subtrechos/stop`
Subtrechos calculados pelo modelo discreto com base em `stop_id`.

#### `GET /map/subtrechos/shape`
Subtrechos associados a shapes específicos.

#### `GET /map/subtrechos/pairs`
Retorna subtrechos apenas para os corredores definidos em `gtfs_core/pairs.py`.

#### `GET /map/subtrechos/all/speed`
Retorna a base canônica de subtrechos com estatísticas de velocidade média.

#### `GET /map/subtrechos/comparison`
Retorna `FeatureCollection` GeoJSON com comparação entre histórico e realtime.

Campos relevantes na comparação:

- `speed_realtime_kmh`
- `speed_hist_kmh`
- `time_hist_sec`
- `n_realtime`
- `n_hist`
- `confidence`
- `ratio`
- `delta_speed_kmh`
- `delta_time_sec`
- `color`

---

### Debug

#### `GET /debug/state`
Resumo do estado em memória.

#### `GET /debug/vehicles`
Lista todos os veículos em memória.

#### `GET /debug/sample/vehicle`
Retorna um veículo aleatório para inspeção.

#### `GET /debug/vehicle/{vehicle_id}`
Retorna um veículo específico.

#### `GET /debug/vehicle_progress/{vehicle_id}`
Retorna o progresso calculado de um veículo específico.

#### `GET /debug/shapes/sample`
Amostra de shape carregado.

#### `GET /debug/trip/stop_times/{trip_id}`
Exibe `stop_times` de uma viagem.

#### `GET /debug/route/{route_id}/shapes/{direction_id}`
Inspeção do mapeamento rota → shapes.

#### `GET /debug/subtrechos`
Lista subtrechos carregados em memória.

#### `GET /debug/subtrechos/times`
Retorna medições brutas por subtrecho.

#### `GET /debug/subtrechos/stats`
Retorna agregações por subtrecho.

---

## Tela e camadas do frontend

O frontend possui duas visões principais:

### 1. Mapa (`MapView.jsx`)
Camadas identificadas no código:

- veículos;
- subtrechos por pares;
- subtrechos all speed;
- subtrechos comparison.

Também há:

- legenda por faixa de velocidade;
- legenda por criticidade da comparação histórica;
- destaque visual por seleção de trechos;
- atualização periódica dos dados do backend.

### 2. Lista (`ListView.jsx`)
Tela tabular com:

- ordenação por coluna;
- filtros por campos operacionais;
- colunas recolhíveis;
- parse flexível de datas;
- enriquecimento com terminal e atendimento a partir de CSV local em `frontend/public/base_terminais_atendimentos.csv`.

---

## Histórico e cache

A base histórica é construída em `app/services/historical_subtrechos_builder.py`.

### Diretórios utilizados

- `data/subtrechos/` → arquivos CSV de origem
- `data/cache/historical_subtrechos/` → cache diário em pickle

### Lógica resumida

- normaliza timestamps históricos;
- filtra registros válidos;
- classifica por slot de 15 minutos;
- calcula tempo médio ponderado;
- converte tempo médio em velocidade média canônica;
- classifica confiança em `low`, `medium` ou `high`.

### Observação importante
O cache histórico diário só é salvo se o build gerar dados válidos, evitando “congelar” um cache vazio para o restante do dia.

---

## Integração com Cittati

A integração está implementada em `app/integrations/cittati/` e é usada principalmente no endpoint:

- `GET /map/vehicles/table`

Quando habilitada por variável de ambiente, a aplicação:

1. autentica no serviço Cittati;
2. consulta viagens do dia;
3. escolhe a viagem ativa mais provável por prefixo;
4. injeta informações operacionais adicionais na visão tabular.

### Campos que podem ser enriquecidos

- `inicioProgramado`
- `inicioRealizado`
- `fimProgramado`
- `nomePontoInicio`
- `nomePontoFim`
- `codAtendimento`
- `atividade`
- `tabela`

---

## Testes e scripts auxiliares

### `tests/run_pipeline_demo.py`
Demonstra o pipeline de construção de subtrechos a partir do GTFS estático.

```bash
py tests/run_pipeline_demo.py
```

### `tests/test_pipeline.py`
Script simples de inspeção dos trechos gerados a partir dos pares definidos.

```bash
py tests/test_pipeline.py
```

### `scripts/test_cittati_viagens.py`
Script auxiliar para validar a integração com Cittati.


