# ===== 第一阶段：Builder =====
FROM node:18-alpine AS builder
RUN npm config set registry https://registry.npmmirror.com
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

# ===== 第二阶段：Runtime =====
FROM nginx:alpine
RUN sed -i 's/dl-cdn.alpinelinux.org/mirrors.aliyun.com/g' /etc/apk/repositories && \
    apk add --no-cache curl
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
HEALTHCHECK --interval=30s CMD curl -f http://localhost/ || exit 1
CMD ["nginx", "-g", "daemon off;"]
