"""Continuous teacher -> Strata 1.0 learning worker.

The teacher uses the configured Groq model to create a large, structured lesson.
The resulting lesson is stored as training data and passed to the local C++
Strata 1.0 learner. This worker never changes model weights itself; it builds the
corpus that can later be used for supervised/fine-tuning jobs.
"""

import asyncio
import base64
import json
import logging
import os
import subprocess
import time
import uuid
from pathlib import Path

from app.engine import client

logger = logging.getLogger("strata.training")

BASE_DIR = Path(__file__).resolve().parent.parent
STRATA_BINARY = Path(
    os.environ.get(
        "STRATA11_BINARY",
        BASE_DIR / "strata11" / "build" / "strata11",
    )
)
LEARNING_DB = Path(
    os.environ.get(
        "STRATA11_LEARNING_DB",
        BASE_DIR / "strata11" / "data" / "learning.tsv",
    )
)
TRAINING_DATASET = Path(
    os.environ.get(
        "STRATA_TRAINING_DATASET",
        BASE_DIR / "strata11" / "data" / "training.jsonl",
    )
)

# Curriculum deliberately starts with English and general reasoning before
# moving into broad factual domains. The worker advances one lesson per cycle.
CURRICULUM = [
    ("english", "English vocabulary, word meaning, spelling, and context"),
    ("english", "English sentence structure, subjects, verbs, objects, and agreement"),
    ("english", "English grammar: tense, aspect, articles, prepositions, and conjunctions"),
    ("english", "English questions, answers, negation, commands, and conversational intent"),
    ("english", "English reading comprehension and extracting facts from prose"),
    ("english", "English paraphrasing, summarization, and preserving meaning"),
    ("english", "English natural conversation, references, pronouns, and follow-up questions"),
    ("reasoning", "basic logic, classification, comparison, and cause and effect"),
    ("reasoning", "multi-step reasoning, decomposition, constraints, and verification"),
    ("math", "arithmetic, percentages, ratios, algebra fundamentals, and word problems"),
    ("science", "basic physics, chemistry, biology, and scientific reasoning"),
    ("history", "world history and how to distinguish established facts from uncertainty"),
    ("geography", "countries, geography, maps, climate, and geographic reasoning"),
    ("computing", "computer architecture, operating systems, networking, and files"),
    ("programming", "programming fundamentals, algorithms, data structures, and debugging"),
    ("programming", "C++, Python, Rust, Swift, compiler concepts, and software architecture"),
    ("writing", "clear writing, structure, tone, editing, and technical explanation"),
    ("knowledge", "how to evaluate sources, conflicting claims, and unreliable information"),
]

SYSTEM_PROMPT = """You are the teacher for Strata 1.0, a continuously learning AI.
Create a large, high-quality lesson for a student model. The lesson must teach
reusable language or reasoning ability, not merely answer one trivia question.

Use authoritative information and distinguish facts from uncertainty. Prefer
primary sources and well-established references. Do not invent citations.
Produce a dense lesson with definitions, examples, counterexamples, explanations,
questions with answers, and reusable patterns. Include natural English whenever
the lesson concerns language.

The output is training material, not a user-facing answer. Do not discuss this
training system. Do not include hidden chain-of-thought or private reasoning.
Instead provide concise explanations of conclusions and the evidence supporting
them.
"""


def _append_dataset(record: dict) -> None:
    TRAINING_DATASET.parent.mkdir(parents=True, exist_ok=True)
    with TRAINING_DATASET.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _teach_cpp(topic: str, question: str, lesson: str) -> None:
    if not STRATA_BINARY.exists() or not lesson.strip():
        return
    LEARNING_DB.parent.mkdir(parents=True, exist_ok=True)
    values = [
        "strata-teacher",
        question,
        lesson,
    ]
    encoded = "\n".join(
        base64.b64encode(value.encode("utf-8")).decode("ascii")
        for value in values
    )
    try:
        subprocess.run(
            [str(STRATA_BINARY), "--mode", "learn", "--db", str(LEARNING_DB)],
            input=encoded,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except Exception:
        logger.exception("Strata 1.0 C++ training ingestion failed")


async def run_training_cycle() -> bool:
    if client is None:
        return False

    index_file = TRAINING_DATASET.with_suffix(".cursor")
    try:
        index = int(index_file.read_text(encoding="utf-8").strip())
    except Exception:
        index = 0

    category, topic = CURRICULUM[index % len(CURRICULUM)]
    question = (
        f"Create a comprehensive training lesson for Strata 1.0 about: {topic}. "
        "Use current web research where useful, synthesize information from multiple "
        "reliable sources, and include at least 20 concrete examples or practice items. "
        "Make the material useful for learning English and general AI behavior rather "
        "than only memorizing isolated facts."
    )

    try:
        # deep_research performs live source retrieval through the teacher model.
        lesson = await client.deep_research(topic, question)
        if not lesson.strip():
            return False

        record = {
            "id": uuid.uuid4().hex,
            "timestamp": time.time(),
            "category": category,
            "topic": topic,
            "teacher": "groq",
            "prompt": question,
            "lesson": lesson,
            "quality": 0.75,
        }
        await asyncio.to_thread(_append_dataset, record)
        await asyncio.to_thread(_teach_cpp, topic, question, lesson)

        index_file.parent.mkdir(parents=True, exist_ok=True)
        index_file.write_text(str((index + 1) % len(CURRICULUM)), encoding="utf-8")
        logger.info("Strata 1.0 training lesson completed: %s", topic)
        return True
    except Exception:
        logger.exception("Strata 1.0 training cycle failed")
        return False


async def training_loop() -> None:
    """Run one teacher lesson every minute without blocking chat requests."""
    await asyncio.sleep(15)
    while True:
        try:
            await run_training_cycle()
        except Exception:
            logger.exception("Strata 1.0 training loop crashed")
        await asyncio.sleep(60)
