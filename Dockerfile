FROM python:3.12-slim AS backend-builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM node:20-alpine AS frontend-builder
WORKDIR /app
COPY frontend/package*.json ./
RUN npm install
COPY frontend .
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

# Instalar NGINX e Supervisor para rodar ambos no mesmo lugar
RUN apt-get update && apt-get install -y nginx supervisor && rm -rf /var/lib/apt/lists/*

COPY --from=backend-builder /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=backend-builder /usr/local/bin/ /usr/local/bin/

# Copiar projeto Python
COPY . /app/
RUN mkdir -p /app/.tmp

# Configurar Frontend
COPY --from=frontend-builder /app/dist /var/www/html
RUN rm /etc/nginx/sites-enabled/default
COPY deployment/nginx.conf /etc/nginx/sites-enabled/default

# Configurar Supervisor
COPY deployment/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

EXPOSE 80 8000
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
