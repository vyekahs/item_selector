# syntax=docker/dockerfile:1.6
# ---- Stage 1: deps ----
FROM node:20-alpine AS deps
RUN apk add --no-cache libc6-compat \
    && corepack enable \
    && corepack prepare pnpm@9.12.0 --activate
WORKDIR /app

# Copy only manifests (lockfile will be generated if missing)
COPY package.json ./
COPY pnpm-lock.yaml* ./

RUN if [ -f pnpm-lock.yaml ]; then \
        pnpm install --frozen-lockfile; \
    else \
        pnpm install --no-frozen-lockfile; \
    fi

# ---- Stage 2: builder ----
FROM node:20-alpine AS builder
RUN corepack enable && corepack prepare pnpm@9.12.0 --activate
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm build

# ---- Stage 3: runtime (standalone) ----
FROM node:20-alpine AS runtime

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

WORKDIR /app

RUN apk add --no-cache curl \
    && addgroup --system --gid 1001 nodejs \
    && adduser  --system --uid 1001 nextjs

# Next.js standalone output
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static  ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public         ./public

USER nextjs
EXPOSE 3000

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
    CMD curl -fsS http://localhost:3000/ || exit 1

CMD ["node", "server.js"]
