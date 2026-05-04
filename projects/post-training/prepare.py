"""Nanochat-style post-training utilities with a fixed local benchmark."""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import random
import re
from pathlib import Path
from typing import Iterable

import torch

from model import NanoChat, NanoChatConfig, save_model


CACHE_DIR = Path(os.environ.get("POSTTRAIN_CACHE_DIR", "~/.cache/autoresearch-posttraining")).expanduser()
DATA_DIR = CACHE_DIR / "data"
BASE_MODEL_DIR = CACHE_DIR / "base_model"
BENCHMARK_NAME = "NanoChat Synthetic ChatCORE"

MAX_SEQ_LEN = 192
TIME_BUDGET = 120
TRAIN_GENERATIVE_EXAMPLES = 4096
TRAIN_CHOICE_EXAMPLES = 1024
EVAL_GENERATIVE_EXAMPLES = 256
EVAL_CHOICE_EXAMPLES = 128

SPECIAL_TOKENS = [
    "<|bos|>",
    "<|user_start|>",
    "<|user_end|>",
    "<|assistant_start|>",
    "<|assistant_end|>",
    "<|python_start|>",
    "<|python_end|>",
    "<|output_start|>",
    "<|output_end|>",
    "<|pad|>",
]
SPECIAL_TOKEN_TO_ID = {token: 256 + i for i, token in enumerate(SPECIAL_TOKENS)}
BOS_ID = SPECIAL_TOKEN_TO_ID["<|bos|>"]
USER_START_ID = SPECIAL_TOKEN_TO_ID["<|user_start|>"]
USER_END_ID = SPECIAL_TOKEN_TO_ID["<|user_end|>"]
ASSISTANT_START_ID = SPECIAL_TOKEN_TO_ID["<|assistant_start|>"]
ASSISTANT_END_ID = SPECIAL_TOKEN_TO_ID["<|assistant_end|>"]
PYTHON_START_ID = SPECIAL_TOKEN_TO_ID["<|python_start|>"]
PYTHON_END_ID = SPECIAL_TOKEN_TO_ID["<|python_end|>"]
OUTPUT_START_ID = SPECIAL_TOKEN_TO_ID["<|output_start|>"]
OUTPUT_END_ID = SPECIAL_TOKEN_TO_ID["<|output_end|>"]
PAD_ID = SPECIAL_TOKEN_TO_ID["<|pad|>"]
VOCAB_SIZE = 256 + len(SPECIAL_TOKENS)

ANSWER_RE = re.compile(r"####\s*([^\n<]+)")


WORDS = [
    "apple",
    "bravo",
    "cabin",
    "delta",
    "eagle",
    "fable",
    "grape",
    "hotel",
    "ivory",
    "joker",
    "karma",
    "lemon",
    "mango",
    "nylon",
    "olive",
    "piano",
    "quilt",
    "river",
    "solar",
    "tango",
    "umbra",
    "vivid",
    "waltz",
    "xenon",
    "yacht",
    "zebra",
]


class ByteChatTokenizer:
    """Byte tokenizer with nanochat-style chat special tokens."""

    vocab_size = VOCAB_SIZE

    def encode(self, text: str, prepend: int | str | None = None, append: int | str | None = None) -> list[int]:
        ids: list[int] = []
        if prepend is not None:
            ids.append(prepend if isinstance(prepend, int) else self.encode_special(prepend))
        ids.extend(text.encode("utf-8", errors="replace"))
        if append is not None:
            ids.append(append if isinstance(append, int) else self.encode_special(append))
        return ids

    def __call__(self, *args, **kwargs) -> list[int]:
        return self.encode(*args, **kwargs)

    def encode_special(self, text: str) -> int:
        return SPECIAL_TOKEN_TO_ID[text]

    def get_bos_token_id(self) -> int:
        return BOS_ID

    def get_vocab_size(self) -> int:
        return VOCAB_SIZE

    def decode(self, ids: Iterable[int], skip_special: bool = True) -> str:
        out = bytearray()
        chunks: list[str] = []
        id_to_special = {v: k for k, v in SPECIAL_TOKEN_TO_ID.items()}
        for token in ids:
            token_id = int(token)
            if 0 <= token_id < 256:
                out.append(token_id)
            elif not skip_special:
                if out:
                    chunks.append(bytes(out).decode("utf-8", errors="replace"))
                    out.clear()
                chunks.append(id_to_special.get(token_id, f"<|unknown_{token_id}|>"))
        if out:
            chunks.append(bytes(out).decode("utf-8", errors="replace"))
        return "".join(chunks)

    def render_conversation(self, conversation: dict, max_tokens: int = MAX_SEQ_LEN + 1) -> tuple[list[int], list[int]]:
        ids: list[int] = []
        mask: list[int] = []

        def add_tokens(token_ids: int | list[int], mask_val: int) -> None:
            if isinstance(token_ids, int):
                token_ids = [token_ids]
            ids.extend(token_ids)
            mask.extend([mask_val] * len(token_ids))

        messages = conversation["messages"]
        if messages and messages[0]["role"] == "system":
            conversation = copy.deepcopy(conversation)
            messages = conversation["messages"]
            assert len(messages) > 1 and messages[1]["role"] == "user"
            messages[1]["content"] = messages[0]["content"] + "\n\n" + messages[1]["content"]
            messages = messages[1:]

        add_tokens(BOS_ID, 0)
        for i, message in enumerate(messages):
            expected_role = "user" if i % 2 == 0 else "assistant"
            assert message["role"] == expected_role, f"message {i} should be {expected_role}"
            content = message["content"]

            if message["role"] == "user":
                assert isinstance(content, str)
                add_tokens(USER_START_ID, 0)
                add_tokens(self.encode(content), 0)
                add_tokens(USER_END_ID, 0)
            else:
                add_tokens(ASSISTANT_START_ID, 0)
                if isinstance(content, str):
                    add_tokens(self.encode(content), 1)
                else:
                    for part in content:
                        part_ids = self.encode(part["text"])
                        if part["type"] == "text":
                            add_tokens(part_ids, 1)
                        elif part["type"] == "python":
                            add_tokens(PYTHON_START_ID, 1)
                            add_tokens(part_ids, 1)
                            add_tokens(PYTHON_END_ID, 1)
                        elif part["type"] == "python_output":
                            add_tokens(OUTPUT_START_ID, 0)
                            add_tokens(part_ids, 0)
                            add_tokens(OUTPUT_END_ID, 0)
                        else:
                            raise ValueError(f"unknown content part type {part['type']!r}")
                add_tokens(ASSISTANT_END_ID, 1)

        return ids[:max_tokens], mask[:max_tokens]

    def render_for_completion(self, conversation: dict, max_tokens: int = MAX_SEQ_LEN) -> list[int]:
        conversation = copy.deepcopy(conversation)
        messages = conversation["messages"]
        assert messages[-1]["role"] == "assistant"
        messages.pop()
        ids, _ = self.render_conversation(conversation, max_tokens=max_tokens - 1)
        ids.append(ASSISTANT_START_ID)
        return ids[-max_tokens:]


def normalize_answer(text: str) -> str:
    text = text.split("<|assistant_end|>", 1)[0]
    text = text.splitlines()[0] if text.splitlines() else text
    text = text.strip().strip(" .,:;")
    text = re.sub(r"\s+", " ", text)
    return text.lower()


def extract_answer(text: str) -> str | None:
    match = ANSWER_RE.search(text)
    if match:
        return normalize_answer(match.group(1))
    return normalize_answer(text)


class Task:
    """Nanochat-style task: conversations plus task-specific evaluation."""

    eval_type = "generative"

    def __init__(self, split: str, size: int, seed: int, start: int = 0, stop: int | None = None, step: int = 1):
        assert split in {"train", "eval"}
        self.split = split
        self.size = size
        self.seed = seed
        self.start = start
        self.stop = stop
        self.step = step

    def num_examples(self) -> int:
        return self.size

    def __len__(self) -> int:
        stop = self.num_examples() if self.stop is None else self.stop
        return max(0, math.ceil((stop - self.start) / self.step))

    def __getitem__(self, index: int) -> dict:
        return self.get_example(self.start + index * self.step)

    def get_example(self, index: int) -> dict:
        raise NotImplementedError

    def evaluate(self, conversation: dict, assistant_response: str) -> int:
        raise NotImplementedError

    def reward(self, conversation: dict, assistant_response: str) -> float:
        return float(self.evaluate(conversation, assistant_response))


class TaskMixture(Task):
    """Deterministic shuffled mixture. Repeating a task oversamples it."""

    def __init__(self, tasks: list[Task], seed: int = 42):
        self.tasks = tasks
        self.lengths = [len(task) for task in tasks]
        self.index_map: list[tuple[int, int]] = []
        for task_idx, length in enumerate(self.lengths):
            for local_idx in range(length):
                self.index_map.append((task_idx, local_idx))
        rng = random.Random(seed)
        rng.shuffle(self.index_map)
        self.eval_type = "mixture"

    def __len__(self) -> int:
        return len(self.index_map)

    def __getitem__(self, index: int) -> dict:
        task_idx, local_idx = self.index_map[index % len(self.index_map)]
        return self.tasks[task_idx][local_idx]


def final_text(answer: str) -> list[dict[str, str]]:
    return [{"type": "text", "text": f"The answer is:\n\n#### {answer}"}]


def render_mc(question: str, letters: list[str], choices: list[str]) -> str:
    lines = [f"Multiple Choice question: {question}"]
    lines.extend(f"- {choice}={letter}" for letter, choice in zip(letters, choices))
    lines.append("")
    lines.append("Respond only with the letter of the correct answer.")
    return "\n".join(lines)


class SyntheticGenerativeTask(Task):
    eval_type = "generative"

    def get_example(self, index: int) -> dict:
        rng = random.Random(self.seed + index * 9973)
        kind = index % 7
        if kind == 0:
            a, b = rng.randint(0, 99), rng.randint(0, 99)
            question = rng.choice([f"What is {a} plus {b}?", f"Add {a} and {b}.", f"Compute {a}+{b}."])
            answer = str(a + b)
        elif kind == 1:
            a, b = rng.randint(0, 99), rng.randint(0, 99)
            question = rng.choice([f"What is {a} minus {b}?", f"Subtract {b} from {a}.", f"Compute {a}-{b}."])
            answer = str(a - b)
        elif kind == 2:
            a, b = rng.randint(0, 12), rng.randint(0, 12)
            question = rng.choice([f"What is {a} times {b}?", f"Multiply {a} by {b}.", f"Compute {a}*{b}."])
            answer = str(a * b)
        elif kind == 3:
            a, b = rng.randint(0, 999), rng.randint(0, 999)
            question = f"Return the larger number: {a}, {b}."
            answer = str(max(a, b))
        elif kind == 4:
            n = rng.randint(0, 999)
            question = f"Answer yes or no: is {n} even?"
            answer = "yes" if n % 2 == 0 else "no"
        elif kind == 5:
            word = rng.choice(WORDS)
            question = f"Spell {word} backwards."
            answer = word[::-1]
        else:
            word = rng.choice(WORDS)
            question = f"How many letters are in {word}?"
            answer = str(len(word))
        return {
            "messages": [
                {"role": "user", "content": question},
                {"role": "assistant", "content": final_text(answer)},
            ],
            "answer": answer,
            "task": "synthetic_generative",
        }

    def evaluate(self, conversation: dict, assistant_response: str) -> int:
        pred = extract_answer(assistant_response)
        ref = normalize_answer(conversation["answer"])
        return int(pred == ref)


class SyntheticToolTask(Task):
    """Small tool-use-flavored SFT task. Python outputs are masked in SFT."""

    eval_type = "generative"

    def get_example(self, index: int) -> dict:
        rng = random.Random(self.seed + index * 7919)
        word = rng.choice(WORDS)
        letter = rng.choice(word)
        count = word.count(letter)
        question = f"How many {letter} are in the word {word}?"
        assistant_parts = [
            {"type": "text", "text": f"I will count and verify the word {word}.\n"},
            {"type": "python", "text": f"'{word}'.count('{letter}')"},
            {"type": "python_output", "text": str(count)},
            {"type": "text", "text": f"\nThe answer is:\n\n#### {count}"},
        ]
        return {
            "messages": [
                {"role": "user", "content": question},
                {"role": "assistant", "content": assistant_parts},
            ],
            "answer": str(count),
            "task": "synthetic_tool",
        }

    def evaluate(self, conversation: dict, assistant_response: str) -> int:
        return int(extract_answer(assistant_response) == normalize_answer(conversation["answer"]))


class SyntheticChoiceTask(Task):
    eval_type = "categorical"

    def get_example(self, index: int) -> dict:
        rng = random.Random(self.seed + index * 6151)
        a, b = rng.randint(0, 30), rng.randint(0, 30)
        correct = a + b
        choices = {correct}
        while len(choices) < 4:
            distractor = correct + rng.choice([-1, 1]) * rng.randint(1, 12)
            choices.add(distractor)
        choices = list(choices)
        rng.shuffle(choices)
        letters = ["A", "B", "C", "D"]
        answer = letters[choices.index(correct)]
        question = render_mc(f"What is {a} + {b}?", letters, [str(c) for c in choices])
        return {
            "messages": [
                {"role": "user", "content": question},
                {"role": "assistant", "content": answer},
            ],
            "letters": letters,
            "answer": answer,
            "task": "synthetic_choice",
        }

    def evaluate(self, conversation: dict, assistant_response: str) -> int:
        return int(normalize_answer(assistant_response).upper() == conversation["answer"])


def build_train_task_mixture() -> TaskMixture:
    return TaskMixture(
        [
            SyntheticGenerativeTask("train", TRAIN_GENERATIVE_EXAMPLES, seed=13),
            SyntheticToolTask("train", TRAIN_GENERATIVE_EXAMPLES // 2, seed=31),
            SyntheticChoiceTask("train", TRAIN_CHOICE_EXAMPLES, seed=47),
            SyntheticChoiceTask("train", TRAIN_CHOICE_EXAMPLES, seed=53),
        ],
        seed=42,
    )


def build_eval_tasks() -> dict[str, Task]:
    return {
        "Generative": SyntheticGenerativeTask("eval", EVAL_GENERATIVE_EXAMPLES, seed=2026),
        "ToolCounting": SyntheticToolTask("eval", EVAL_GENERATIVE_EXAMPLES // 2, seed=2027),
        "Choice": SyntheticChoiceTask("eval", EVAL_CHOICE_EXAMPLES, seed=2028),
    }


def sft_data_generator_bos_bestfit(
    dataset: TaskMixture | Task,
    tokenizer: ByteChatTokenizer,
    batch_size: int,
    max_seq_len: int = MAX_SEQ_LEN,
    buffer_size: int = 100,
    seed: int = 42,
) -> Iterable[tuple[torch.Tensor, torch.Tensor, float, int]]:
    """Pack full conversations into rows, padding rather than cropping."""
    row_capacity = max_seq_len + 1
    conv_buffer: list[tuple[list[int], list[int]]] = []
    rng = random.Random(seed)
    order = list(range(len(dataset)))
    rng.shuffle(order)
    cursor = 0
    epoch = 1
    consumed = 0

    def refill_buffer() -> None:
        nonlocal cursor, epoch
        while len(conv_buffer) < buffer_size:
            conversation = dataset[order[cursor]]
            ids, mask = tokenizer.render_conversation(conversation, max_tokens=row_capacity)
            conv_buffer.append((ids, mask))
            cursor += 1
            if cursor >= len(order):
                cursor = 0
                epoch += 1
                rng.shuffle(order)

    while True:
        rows: list[list[int]] = []
        mask_rows: list[list[int]] = []
        row_lengths: list[int] = []
        for _ in range(batch_size):
            row: list[int] = []
            mask_row: list[int] = []
            content_len = row_capacity
            while len(row) < row_capacity:
                refill_buffer()
                remaining = row_capacity - len(row)
                best_idx = -1
                best_len = 0
                for i, (conv, _) in enumerate(conv_buffer):
                    if len(conv) <= remaining and len(conv) > best_len:
                        best_idx = i
                        best_len = len(conv)
                if best_idx >= 0:
                    conv, conv_mask = conv_buffer.pop(best_idx)
                    row.extend(conv)
                    mask_row.extend(conv_mask)
                    consumed += 1
                else:
                    content_len = len(row)
                    row.extend([PAD_ID] * remaining)
                    mask_row.extend([0] * remaining)
                    break
            rows.append(row[:row_capacity])
            mask_rows.append(mask_row[:row_capacity])
            row_lengths.append(content_len)

        batch_tensor = torch.tensor(rows, dtype=torch.long)
        inputs = batch_tensor[:, :-1].contiguous()
        targets = batch_tensor[:, 1:].clone().contiguous()
        mask_tensor = torch.tensor(mask_rows, dtype=torch.int8)[:, 1:]
        targets[mask_tensor == 0] = -1
        for row_idx, content_len in enumerate(row_lengths):
            if content_len < row_capacity:
                targets[row_idx, max(0, content_len - 1) :] = -1
        progress = min(consumed / max(1, len(dataset)), 1.0)
        yield inputs, targets, progress, epoch


@torch.no_grad()
def run_generative_eval(
    task: Task,
    model: torch.nn.Module,
    tokenizer: ByteChatTokenizer,
    max_problems: int | None,
    max_new_tokens: int,
    device: torch.device,
    temperature: float = 0.0,
    top_k: int | None = None,
    return_examples: bool = False,
) -> dict[str, object]:
    total = len(task) if max_problems is None else min(len(task), max_problems)
    correct = 0
    examples = []
    for i in range(total):
        conversation = task[i]
        prompt_ids = tokenizer.render_for_completion(conversation)
        idx = torch.tensor([prompt_ids], dtype=torch.long, device=device)
        out = model.generate(
            idx,
            max_new_tokens=max_new_tokens,
            eos_id=ASSISTANT_END_ID,
            temperature=temperature,
            top_k=top_k,
        )
        new_ids = out[0, len(prompt_ids) :].detach().cpu().tolist()
        if ASSISTANT_END_ID in new_ids:
            new_ids = new_ids[: new_ids.index(ASSISTANT_END_ID)]
        completion = tokenizer.decode(new_ids)
        passed = bool(task.evaluate(conversation, completion))
        correct += int(passed)
        if return_examples:
            examples.append(
                {
                    "task": conversation.get("task", type(task).__name__),
                    "prompt": conversation["messages"][0]["content"],
                    "answer": conversation.get("answer"),
                    "prediction": completion.strip(),
                    "correct": passed,
                }
            )
    result: dict[str, object] = {
        "accuracy": correct / total if total else 0.0,
        "num_correct": correct,
        "num_examples": total,
    }
    if return_examples:
        result["examples"] = examples
    return result


@torch.no_grad()
def run_categorical_eval(
    task: Task,
    model: torch.nn.Module,
    tokenizer: ByteChatTokenizer,
    max_problems: int | None,
    batch_size: int,
    device: torch.device,
    return_examples: bool = False,
) -> dict[str, object]:
    total = len(task) if max_problems is None else min(len(task), max_problems)
    correct = 0
    examples = []
    for start in range(0, total, batch_size):
        conversations = [task[i] for i in range(start, min(total, start + batch_size))]
        prompt_ids = [tokenizer.render_for_completion(conversation) for conversation in conversations]
        max_len = max(len(row) for row in prompt_ids)
        padded = [row + [PAD_ID] * (max_len - len(row)) for row in prompt_ids]
        idx = torch.tensor(padded, dtype=torch.long, device=device)
        _, logits = model(idx)
        for row_idx, conversation in enumerate(conversations):
            answer_pos = len(prompt_ids[row_idx]) - 1
            letters = conversation["letters"]
            letter_ids = [tokenizer.encode(letter)[0] for letter in letters]
            focus_logits = logits[row_idx, answer_pos, letter_ids]
            prediction = letters[int(focus_logits.argmax().item())]
            passed = bool(task.evaluate(conversation, prediction))
            correct += int(passed)
            if return_examples:
                examples.append(
                    {
                        "task": conversation.get("task", type(task).__name__),
                        "prompt": conversation["messages"][0]["content"],
                        "answer": conversation["answer"],
                        "prediction": prediction,
                        "correct": passed,
                    }
                )
    result: dict[str, object] = {
        "accuracy": correct / total if total else 0.0,
        "num_correct": correct,
        "num_examples": total,
    }
    if return_examples:
        result["examples"] = examples
    return result


@torch.no_grad()
def score_model(
    model: torch.nn.Module,
    split: str = "eval",
    limit: int | None = None,
    max_new_tokens: int = 32,
    batch_size: int = 16,
    device: str | torch.device | None = None,
    return_examples: bool = False,
) -> dict[str, object]:
    if split != "eval":
        raise ValueError("score_model uses the fixed eval tasks; use SFT loss for train monitoring")
    tokenizer = ByteChatTokenizer()
    if device is None:
        device = next(model.parameters()).device
    device = torch.device(device)
    was_training = model.training
    model.eval()

    task_metrics: dict[str, dict[str, object]] = {}
    baselines = {"Generative": 0.0, "ToolCounting": 0.0, "Choice": 0.25}
    for task_name, task in build_eval_tasks().items():
        max_problems = limit if limit is not None and limit >= 0 else None
        if task.eval_type == "generative":
            metrics = run_generative_eval(
                task,
                model,
                tokenizer,
                max_problems=max_problems,
                max_new_tokens=max_new_tokens,
                device=device,
                return_examples=return_examples,
            )
        elif task.eval_type == "categorical":
            metrics = run_categorical_eval(
                task,
                model,
                tokenizer,
                max_problems=max_problems,
                batch_size=batch_size,
                device=device,
                return_examples=return_examples,
            )
        else:
            raise ValueError(task.eval_type)
        task_metrics[task_name] = metrics

    centered_scores = []
    total_correct = 0
    total_examples = 0
    for task_name, metrics in task_metrics.items():
        accuracy = float(metrics["accuracy"])
        baseline = baselines[task_name]
        centered_scores.append((accuracy - baseline) / (1.0 - baseline))
        total_correct += int(metrics["num_correct"])
        total_examples += int(metrics["num_examples"])

    if was_training:
        model.train()
    return {
        "eval_score": sum(centered_scores) / len(centered_scores),
        "raw_accuracy": total_correct / total_examples if total_examples else 0.0,
        "num_correct": total_correct,
        "num_examples": total_examples,
        "tasks": task_metrics,
    }


def export_task_preview(force: bool = False) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    paths = {
        "train_preview.jsonl": [build_train_task_mixture()[i] for i in range(128)],
        "eval_generative_preview.jsonl": [build_eval_tasks()["Generative"][i] for i in range(64)],
        "eval_choice_preview.jsonl": [build_eval_tasks()["Choice"][i] for i in range(64)],
    }
    for filename, rows in paths.items():
        path = DATA_DIR / filename
        if path.exists() and not force:
            continue
        with open(path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=True) + "\n")


def expected_base_config() -> dict[str, int | float]:
    return {
        "vocab_size": VOCAB_SIZE,
        "block_size": MAX_SEQ_LEN,
        "n_layer": 4,
        "n_head": 4,
        "n_embd": 256,
        "dropout": 0.0,
    }


def ensure_base_model(force: bool = False) -> None:
    config_path = BASE_MODEL_DIR / "config.json"
    weights_path = BASE_MODEL_DIR / "model.pt"
    if not force and config_path.exists() and weights_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            if json.load(f) == expected_base_config():
                return
    BASE_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(1234)
    model = NanoChat(NanoChatConfig(**expected_base_config()))
    save_model(model, BASE_MODEL_DIR)


def validate_model_directory(model_path: str | Path) -> None:
    """Reject architecture/model substitution while allowing weight updates."""
    ensure_base_model()
    model_path = Path(model_path)
    config_path = model_path / "config.json"
    weights_path = model_path / "model.pt"
    if not config_path.exists() or not weights_path.exists():
        raise FileNotFoundError(f"{model_path} must contain config.json and model.pt")

    with open(BASE_MODEL_DIR / "config.json", "r", encoding="utf-8") as f:
        base_config = json.load(f)
    with open(config_path, "r", encoding="utf-8") as f:
        candidate_config = json.load(f)
    if candidate_config != base_config:
        raise ValueError("final_model config does not match the fixed NanoChat base architecture")

    try:
        base_state = torch.load(BASE_MODEL_DIR / "model.pt", map_location="cpu", weights_only=True)
        candidate_state = torch.load(weights_path, map_location="cpu", weights_only=True)
    except TypeError:
        base_state = torch.load(BASE_MODEL_DIR / "model.pt", map_location="cpu")
        candidate_state = torch.load(weights_path, map_location="cpu")

    if set(candidate_state) != set(base_state):
        raise ValueError("final_model state dict keys do not match the fixed NanoChat base model")
    for key, base_tensor in base_state.items():
        if candidate_state[key].shape != base_tensor.shape:
            raise ValueError(f"final_model tensor shape mismatch for {key}")


def ensure_prepared(force: bool = False) -> None:
    export_task_preview(force=force)
    ensure_base_model(force=force)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare fixed task previews and base checkpoint for post-training.")
    parser.add_argument("--force", action="store_true", help="Regenerate previews and base checkpoint.")
    args = parser.parse_args()

    ensure_prepared(force=args.force)
    print(f"cache_dir:       {CACHE_DIR}")
    print(f"benchmark:       {BENCHMARK_NAME}")
    print(f"vocab_size:      {VOCAB_SIZE}")
    print(f"max_seq_len:     {MAX_SEQ_LEN}")
    print(f"base_model:      {BASE_MODEL_DIR}")
    print(f"task_previews:   {DATA_DIR}")
    print("Done. Ready to post-train.")


if __name__ == "__main__":
    main()
