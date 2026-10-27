FROM node:20-bookworm-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1 BACKEND_INTERNAL_URL=http://backend:8000
RUN npm run build
FROM node:20-bookworm-slim
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 BACKEND_INTERNAL_URL=http://backend:8000
COPY --from=build --chown=node:node /app/.next ./.next
COPY --from=build --chown=node:node /app/node_modules ./node_modules
COPY --from=build --chown=node:node /app/public ./public
COPY --from=build --chown=node:node /app/package.json /app/next.config.js ./
USER node
CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0", "--port", "3000"]
