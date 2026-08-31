# GTFS On Time

Plataforma operacional para correlacionar o GTFS estático com o Modelo 4 da
Cittati, calcular tempos realizados por trecho e expor ETAs para o CCO e o
frontend operacional e demais integrações.

## Execução local com Docker

Configure as variáveis locais usando `.env.example` como referência. O arquivo
`.env` não participa do build da imagem e é ignorado pelo Git.

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f worker
```

O Compose executa cinco serviços:

- `database`: PostgreSQL/PostGIS;
- `migrate`: aplica as migrações Alembic e encerra;
- `api`: disponibiliza a API na interface local;
- `worker`: consulta a Cittati continuamente, sem sobrepor ciclos.
- `frontend`: interface React/MapLibre disponível em `http://127.0.0.1:5173`.

O worker inicia um ciclo a cada 10 segundos. Se o ciclo anterior ultrapassar
esse intervalo, o próximo começa logo após o término. Falhas temporárias usam
backoff exponencial limitado. Os snapshots de ETA da frota são atualizados no
máximo uma vez por janela de cinco minutos.

## Endpoints operacionais

- `GET /health`: processo da API;
- `GET /health/ready`: conexão com o banco;
- `GET /health/operational`: última ingestão válida da Cittati;
- `GET /api/v1/vehicles/eta-snapshots`: snapshot materializado da frota;
- `GET /api/v1/vehicles/{vehicle_prefix}/eta`: ETA calculado sob demanda;
- `GET /api/v1/map/vehicles`: posições projetadas com map matching resolvido;
- `GET /api/v1/map/trips/{trip_id}/geometry`: shape e paradas de uma viagem;
- `GET /api/v1/prescriptions/vehicle-swaps`: realocação global por terminal;
- `GET /api/v1/segments/estimate`: estimativa de um trecho.

## Frontend operacional

O frontend usa React, TypeScript, Vite e MapLibre. A visão de mapa consulta as
posições projetadas a cada dez segundos. A geometria da viagem e o ETA completo
são carregados somente quando um veículo é selecionado. O Nginx encaminha as
rotas `/api` e `/health` ao FastAPI, portanto nenhuma credencial da Cittati é
enviada ao navegador.

Para desenvolvimento com hot reload:

```bash
cd frontend
npm install
npm run dev
```

O mapa permite alternar entre OpenStreetMap claro, OpenFreeMap Dark baseado em
dados OSM e imagens de satélite Esri. As atribuições de cada provedor
permanecem visíveis no mapa; nenhuma dessas camadas exige chave no frontend.

O endpoint prescritivo usa o ETA futuro até o terminal e a próxima viagem
informada pela Cittati. Para cada terminal, ele minimiza a soma dos atrasos por
meio de uma alocação global, permitindo cadeias com mais de dois veículos.
Viagens com atraso original estritamente superior a dez minutos acionam a
análise. Um compromisso viável cuja partida esteja nos próximos dez minutos
permanece protegido. As recomendações usam o snapshot mais recente e não são
armazenadas como histórico.

O worker realiza chamadas externas à Cittati. Para validar somente a construção
das imagens, sem iniciar a ingestão, use:

```bash
docker compose build api worker migrate frontend
```

## Desenvolvimento

```bash
export PYTHONPATH=backend
.venv/Scripts/pytest.exe -q backend/tests
.venv/Scripts/ruff.exe check backend
.venv/Scripts/python.exe -m alembic -c backend/alembic.ini check
```
