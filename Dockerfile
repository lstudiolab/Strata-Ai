FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends g++ cmake ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY . .
RUN cmake -S strata11 -B strata11/build -DCMAKE_BUILD_TYPE=Release && cmake --build strata11/build --config Release
RUN mkdir -p data
RUN ./strata11/build/strata --mode train --dataset data/train.txt --checkpoint data/strata.model --epochs 5 --learning-rate 0.0005
ENV PORT=8000
ENV STRATA_MEMORY_FILE=data/strata.memory
CMD ["sh","-c","./strata11/build/strata --model data/strata.model --memory data/strata.memory --port ${PORT:-8000}"]
