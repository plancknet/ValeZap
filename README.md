# ValeZap Flask Clone

Aplica��o web em Flask que replica o chat ValeZap do projeto original React/Supabase, agora utilizando Python, Flask, Gunicorn e Postgres.

## Requisitos

- Python 3.11+
- Postgres 14+

## Instala��o

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Atualize `DATABASE_URL` no `.env` com as credenciais do seu Postgres e execute as migra��es iniciais via script simples:

```bash
python -c "from app.database import init_engine, init_db; from app.config import Config; init_engine(Config.DATABASE_URL); init_db()"
```

## Execu��o em desenvolvimento

```bash
python main.py
```

A aplica��o ficar� dispon�vel em `http://localhost:5000`.

## Execu��o com Gunicorn

```bash
gunicorn -c gunicorn.conf.py 'main:app'
```

## Endpoints principais

- `GET /` � Interface web do chat.
- `POST /functions/v1/webhook-valezap` � Endpoint compat�vel com o webhook original para registrar mensagens.
- `GET /api/messages` � Retorna hist�rico por sess�o e player.
- `GET /api/messages/stream` � Stream SSE para mensagens em tempo real.
- `GET /health` � Healthcheck simples.

## Estrutura

- `app/` � C�digo fonte Flask.
- `static/` � CSS e JavaScript do frontend.
- `templates/` � Templates Jinja HTML.
- `migrations/` � Espa�o reservado para scripts SQL adicionais.
