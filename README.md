# ValeZap Flask Clone

Aplicação web em Flask que replica o chat ValeZap do projeto original React/Supabase, agora utilizando Python, Flask, Gunicorn e Postgres.

## Requisitos

- Python 3.11+
- Postgres 14+

## Instalação

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Atualize `DATABASE_URL` no `.env` com as credenciais do seu Postgres e execute as migrações iniciais via script simples:

```bash
python -c "from app.database import init_engine, init_db; from app.config import Config; init_engine(Config.DATABASE_URL); init_db()"
```

## Execução em desenvolvimento

```bash
python main.py
```

A aplicação ficará disponível em `http://localhost:5000`.

## Execução com Gunicorn

```bash
gunicorn -c gunicorn.conf.py 'main:app'
```

## Endpoints principais

- `GET /` – Interface web do chat.
- `POST /functions/v1/webhook-valezap` – Endpoint compatível com o webhook original para registrar mensagens.
- `GET /api/messages` – Retorna histórico por sessão e player.
- `GET /api/messages/stream` – Stream SSE para mensagens em tempo real.
- `GET /health` – Healthcheck simples.

## Estrutura

- `app/` – Código fonte Flask.
- `static/` – CSS e JavaScript do frontend.
- `templates/` – Templates Jinja HTML.
- `migrations/` – Espaço reservado para scripts SQL adicionais.
