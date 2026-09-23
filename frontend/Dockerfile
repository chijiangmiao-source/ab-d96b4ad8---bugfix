FROM node:20-alpine AS build

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci || npm install
COPY . .
# Optional build-time override of the API origin; default uses same-origin
# requests which nginx proxies to the api service.
ARG VITE_API_BASE=""
ENV VITE_API_BASE=$VITE_API_BASE
RUN npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=10s --timeout=3s --start-period=3s --retries=5 \
  CMD wget -qO- http://127.0.0.1:80/ >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
