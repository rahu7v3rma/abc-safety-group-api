# ABCSafetyGroup API
A server written in [python](https://www.python.org/) language and based on [FastAPI](https://fastapi.tiangolo.com/) framework.

## Local Development

### Setup Packages

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r src/requirements.txt
```

### Install Databases

- [PostgreSQL](https://www.postgresql.org/)
- [Redis](https://redis.io/)
- [MongoDB](https://www.mongodb.com/)

### Update Environment Variables

Copy `example.env` to `.env` file and set the variables with following info:
- Databases credentials
- JWT secret for auth services
- SMTP credentials for email services
- Company information
- Training connect credentials
- Paypal credentials
- 8x8 app credentials for sms services
- Toggle features

### Starting App

```bash
uvicorn src.api.app:app --host 0.0.0.0 --port 8080 --reload --env-file .env
```

### Linter / Formatter

#### [ruff](https://github.com/astral-sh/ruff)

```bash
ruff format src
ruff check src --fix
```