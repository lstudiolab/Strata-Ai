FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends g++ cmake ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY . .
RUN cmake -S strata11 -B strata11/build -DCMAKE_BUILD_TYPE=Release && cmake --build strata11/build --config Release
RUN mkdir -p data
ENV PORT=8000
CMD ["sh","-c","./strata11/build/strata --model data/strata.model --port ${PORT:-8000}"]
