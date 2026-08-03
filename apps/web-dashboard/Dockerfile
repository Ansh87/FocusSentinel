FROM node:20-alpine AS builder
WORKDIR /app

# Next.js inlines NEXT_PUBLIC_* variables at build time, not at container
# start time, so this has to be a build ARG rather than a runtime ENV var on
# the platform. Railway (and most other platforms) automatically pass a
# service's configured variables through as build args of the same name when
# building from a Dockerfile — see docs/DEPLOYMENT.md.
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL

COPY apps/web-dashboard/package.json ./package.json
RUN npm install
COPY apps/web-dashboard ./
RUN npm run build

FROM node:20-alpine
WORKDIR /app
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
COPY --from=builder /app ./
EXPOSE 3000
# Shell form so ${PORT} expands — Railway assigns a dynamic port at runtime.
CMD npm start -- -p ${PORT:-3000}
