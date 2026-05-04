"""
Nanochat-style post-training for the fixed local NanoChat model.

This is a starter method, not the benchmark itself. It implements masked chat
SFT over a task mixture, with an optional lightweight reward-training phase.
The required benchmark artifact is final_model/.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import shutil
import time
from contextlib import nullcontext
from pathlib import Path

import torch

from model import load_model, save_model
from prepare import (
    ASSISTANT_END_ID,
    BASE_MODEL_DIR,
    MAX_SEQ_LEN,
    PAD_ID,
    TIME_BUDGET,
    TRAIN_CHOICE_EXAMPLES,
    TRAIN_GENERATIVE_EXAMPLES,
    ByteChatTokenizer,
    SyntheticChoiceTask,
    SyntheticGenerativeTask,
    SyntheticToolTask,
    Task,
    TaskMixture,
    ensure_prepared,
    score_model,
    sft_data_generator_bos_bestfit,
)


# ---------------------------------------------------------------------------
# Editable post-training hyperparameters
# ---------------------------------------------------------------------------

SEED = 42
BATCH_SIZE = 48
MAX_STEPS = 1000
LEARNING_RATE = 4e-4
INIT_LR_FRAC = 0.8
FINAL_LR_FRAC = 0.05
WEIGHT_DECAY = 0.05
WARMUP_RATIO = 0.03
WARMDOWN_RATIO = 0.5
GRAD_CLIP = 1.0
EVAL_EVERY = 100
EVAL_LIMIT = 64
FINAL_EVAL_LIMIT = None
RL_STEPS = 0
RL_EXAMPLES_PER_STEP = 4
RL_SAMPLES_PER_EXAMPLE = 4
RL_MAX_NEW_TOKENS = 32
RL_TEMPERATURE = 1.0
RL_TOP_K = 50
FINAL_MODEL_DIR = Path("final_model")
METHOD_NAME = "concise_final_answer_sft"


class FinalAnswerFormatTask(Task):
    """Rewrite assistant targets to a concise evaluator-aligned final-answer template."""

    def __init__(self, base_task: Task):
        self.base_task = base_task
        self.eval_type = getattr(base_task, "eval_type", "generative")

    def __len__(self) -> int:
        return len(self.base_task)

    def __getitem__(self, index: int) -> dict:
        conversation = copy.deepcopy(self.base_task[index])
        answer = str(conversation["answer"])
        if self.eval_type == "categorical":
            content: str | list[dict[str, str]] = answer
            suffix = "direct_choice"
        else:
            content = [{"type": "text", "text": f"The answer is:\n\n#### {answer}"}]
            suffix = "final_answer"
        conversation["messages"][-1] = {"role": "assistant", "content": content}
        conversation["task"] = f"{conversation.get('task', 'task')}_{suffix}"
        return conversation


def build_concise_final_answer_train_mixture() -> TaskMixture:
    """Shorten targets while keeping a stable final-answer format for generation."""
    return TaskMixture(
        [
            FinalAnswerFormatTask(SyntheticGenerativeTask("train", TRAIN_GENERATIVE_EXAMPLES, seed=13)),
            FinalAnswerFormatTask(SyntheticGenerativeTask("train", TRAIN_GENERATIVE_EXAMPLES, seed=19)),
            FinalAnswerFormatTask(SyntheticToolTask("train", TRAIN_GENERATIVE_EXAMPLES // 2, seed=31)),
            FinalAnswerFormatTask(SyntheticToolTask("train", TRAIN_GENERATIVE_EXAMPLES // 2, seed=37)),
            FinalAnswerFormatTask(SyntheticChoiceTask("train", TRAIN_CHOICE_EXAMPLES, seed=47)),
            FinalAnswerFormatTask(SyntheticChoiceTask("train", TRAIN_CHOICE_EXAMPLES, seed=53)),
        ],
        seed=SEED,
    )


def pick_device(name: str) -> torch.device:
    if name != "auto":
        return torch.device(name)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def configure_optimizer(model: torch.nn.Module, learning_rate: float) -> torch.optim.Optimizer:
    decay, no_decay = [], []
    for name, param in model.named_parameters():
        if not param.requires_grad:
            continue
        if param.ndim >= 2 and not name.endswith("wte.weight"):
            decay.append(param)
        else:
            no_decay.append(param)
    params_are_cuda = next(model.parameters()).is_cuda
    return torch.optim.AdamW(
        [
            {"params": decay, "weight_decay": WEIGHT_DECAY},
            {"params": no_decay, "weight_decay": 0.0},
        ],
        lr=learning_rate,
        betas=(0.9, 0.95),
        fused=params_are_cuda,
    )


def progress_lr_multiplier(progress: float) -> float:
    if progress < WARMUP_RATIO:
        return max(1e-6, progress / max(WARMUP_RATIO, 1e-8))
    if progress <= 1.0 - WARMDOWN_RATIO:
        return 1.0
    decay = (progress - (1.0 - WARMDOWN_RATIO)) / max(WARMDOWN_RATIO, 1e-8)
    return (1.0 - decay) + decay * FINAL_LR_FRAC


def save_training_config(path: Path, args: argparse.Namespace, method: str) -> None:
    payload = {
        "method": method,
        "seed": SEED,
        "batch_size": args.batch_size,
        "max_steps": args.max_steps,
        "time_budget": args.time_budget,
        "learning_rate": args.learning_rate,
        "init_lr_frac": INIT_LR_FRAC,
        "final_lr_frac": FINAL_LR_FRAC,
        "weight_decay": WEIGHT_DECAY,
        "warmup_ratio": WARMUP_RATIO,
        "warmdown_ratio": WARMDOWN_RATIO,
        "grad_clip": GRAD_CLIP,
        "rl_steps": args.rl_steps,
    }
    with open(path / "training_config.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def maybe_save_best(
    model: torch.nn.Module,
    args: argparse.Namespace,
    score: float,
    state: dict[str, float | int | str],
    method: str,
) -> None:
    if score >= float(state["best_score"]):
        state["best_score"] = score
        state["best_step"] = int(state["step"])
        state["best_phase"] = method
        save_model(model, FINAL_MODEL_DIR)
        save_training_config(FINAL_MODEL_DIR, args, method)


def run_sft(
    model: torch.nn.Module,
    train_model: torch.nn.Module,
    optimizer: torch.optim.Optimizer,
    args: argparse.Namespace,
    device: torch.device,
    autocast_ctx,
    state: dict[str, float | int | str],
) -> float:
    tokenizer = ByteChatTokenizer()
    train_task = build_concise_final_answer_train_mixture()
    train_loader = sft_data_generator_bos_bestfit(
        train_task,
        tokenizer,
        batch_size=args.batch_size,
        max_seq_len=MAX_SEQ_LEN,
        seed=SEED,
    )
    last_loss = float("nan")

    print(f"training_method: {METHOD_NAME}")
    print(f"training_mixture_rows: {len(train_task):,}")
    print(
        "training_task_balance: "
        f"generative={2 * TRAIN_GENERATIVE_EXAMPLES:,} "
        f"tool={TRAIN_GENERATIVE_EXAMPLES:,} "
        f"choice={2 * TRAIN_CHOICE_EXAMPLES:,}"
    )
    for step in range(1, args.max_steps + 1):
        x, y, data_progress, epoch = next(train_loader)
        x = x.to(device)
        y = y.to(device)
        step_progress = step / max(1, args.max_steps)
        progress = max(data_progress, step_progress)
        lrm = progress_lr_multiplier(progress)
        for group in optimizer.param_groups:
            group["lr"] = args.learning_rate * INIT_LR_FRAC * lrm

        optimizer.zero_grad(set_to_none=True)
        with autocast_ctx:
            loss, _ = train_model(x, y)
        assert loss is not None
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), GRAD_CLIP)
        optimizer.step()
        last_loss = float(loss.detach().cpu())

        state["step"] = step
        if step == 1 or step % 20 == 0:
            elapsed = time.time() - float(state["t0"])
            print(
                f"sft step {step:04d} ({100 * progress:.1f}%) | loss {last_loss:.4f} "
                f"| lrm {lrm:.3f} | epoch {epoch} | elapsed {elapsed:.1f}s"
            )

        should_eval = step == 1 or step % args.eval_every == 0 or step == args.max_steps
        if should_eval:
            metrics = score_model(model, limit=args.eval_limit, device=device)
            score = float(metrics["eval_score"])
            print(
                f"eval sft step {step:04d} | eval_score {score:.4f} "
                f"| raw_accuracy {float(metrics['raw_accuracy']):.4f} "
                f"({metrics['num_correct']}/{metrics['num_examples']})"
            )
            maybe_save_best(model, args, score, state, METHOD_NAME)

        if time.time() - float(state["t0"]) >= args.time_budget:
            break

    return last_loss


def build_rollout_batch(
    model: torch.nn.Module,
    tokenizer: ByteChatTokenizer,
    task: SyntheticGenerativeTask,
    step: int,
    args: argparse.Namespace,
    device: torch.device,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, float]:
    sequences: list[list[int]] = []
    masks: list[list[int]] = []
    advantages: list[float] = []
    reward_means: list[float] = []

    for example_idx in range(args.rl_examples_per_step):
        conversation = task[(step * args.rl_examples_per_step + example_idx) % len(task)]
        prompt_ids = tokenizer.render_for_completion(conversation)
        prompt_len = len(prompt_ids)
        group_sequences: list[list[int]] = []
        group_masks: list[list[int]] = []
        group_rewards: list[float] = []
        for sample_idx in range(args.rl_samples_per_example):
            torch.manual_seed(SEED + step * 1009 + example_idx * 97 + sample_idx)
            idx = torch.tensor([prompt_ids], dtype=torch.long, device=device)
            out = model.generate(
                idx,
                max_new_tokens=args.rl_max_new_tokens,
                eos_id=ASSISTANT_END_ID,
                temperature=args.rl_temperature,
                top_k=args.rl_top_k,
            )
            seq = out[0].detach().cpu().tolist()
            if len(seq) > MAX_SEQ_LEN + 1:
                seq = seq[: MAX_SEQ_LEN + 1]
            generated = seq[prompt_len:]
            if ASSISTANT_END_ID in generated:
                generated = generated[: generated.index(ASSISTANT_END_ID)]
            completion = tokenizer.decode(generated)
            reward = task.reward(conversation, completion)
            group_sequences.append(seq)
            group_masks.append([0] * prompt_len + [1] * max(0, len(seq) - prompt_len))
            group_rewards.append(reward)
        reward_mean = sum(group_rewards) / len(group_rewards)
        reward_means.append(reward_mean)
        for seq, mask, reward in zip(group_sequences, group_masks, group_rewards):
            sequences.append(seq)
            masks.append(mask[: len(seq)])
            advantages.append(reward - reward_mean)

    max_len = min(MAX_SEQ_LEN + 1, max(len(seq) for seq in sequences))
    ids = torch.full((len(sequences), max_len), PAD_ID, dtype=torch.long)
    mask_tensor = torch.zeros((len(sequences), max_len), dtype=torch.bool)
    for row_idx, (seq, mask) in enumerate(zip(sequences, masks)):
        n = min(max_len, len(seq))
        ids[row_idx, :n] = torch.tensor(seq[:n], dtype=torch.long)
        mask_tensor[row_idx, :n] = torch.tensor(mask[:n], dtype=torch.bool)
    inputs = ids[:, :-1].to(device)
    targets = ids[:, 1:].clone().to(device)
    target_mask = mask_tensor[:, 1:].to(device)
    targets[target_mask == 0] = -1
    adv = torch.tensor(advantages, dtype=torch.float32, device=device)
    return inputs, targets, adv, sum(reward_means) / len(reward_means)


def run_reward_training(
    model: torch.nn.Module,
    train_model: torch.nn.Module,
    optimizer: torch.optim.Optimizer,
    args: argparse.Namespace,
    device: torch.device,
    state: dict[str, float | int | str],
) -> None:
    if args.rl_steps <= 0:
        return
    tokenizer = ByteChatTokenizer()
    task = SyntheticGenerativeTask("train", size=TRAIN_SIZE_FOR_RL, seed=109)
    print(f"rl_examples: {len(task):,}")

    for rl_step in range(1, args.rl_steps + 1):
        inputs, targets, advantages, mean_reward = build_rollout_batch(
            model,
            tokenizer,
            task,
            rl_step,
            args,
            device,
        )
        lrm = max(0.0, 1.0 - (rl_step - 1) / max(1, args.rl_steps))
        for group in optimizer.param_groups:
            group["lr"] = args.learning_rate * INIT_LR_FRAC * 0.25 * lrm

        optimizer.zero_grad(set_to_none=True)
        loss_flat, _ = train_model(inputs, targets, reduction="none")
        assert loss_flat is not None
        logp = -loss_flat.view_as(targets)
        valid = (targets >= 0).sum().clamp(min=1)
        objective = (logp * advantages[:, None]).sum() / valid
        loss = -objective
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), GRAD_CLIP)
        optimizer.step()

        state["step"] = int(state["step"]) + 1
        if rl_step == 1 or rl_step % 10 == 0 or rl_step == args.rl_steps:
            print(
                f"rl step {rl_step:04d}/{args.rl_steps} | loss {float(loss.detach().cpu()):.5f} "
                f"| mean_reward {mean_reward:.3f} | lrm {lrm:.3f}"
            )
        if rl_step % args.eval_every == 0 or rl_step == args.rl_steps:
            metrics = score_model(model, limit=args.eval_limit, device=device)
            score = float(metrics["eval_score"])
            print(
                f"eval rl step {rl_step:04d} | eval_score {score:.4f} "
                f"| raw_accuracy {float(metrics['raw_accuracy']):.4f} "
                f"({metrics['num_correct']}/{metrics['num_examples']})"
            )
            maybe_save_best(model, args, score, state, "sft_rl")
        if time.time() - float(state["t0"]) >= args.time_budget:
            break


TRAIN_SIZE_FOR_RL = 512


def main() -> None:
    parser = argparse.ArgumentParser(description="Post-train NanoChat and write final_model/.")
    parser.add_argument("--max-steps", type=int, default=MAX_STEPS)
    parser.add_argument("--time-budget", type=float, default=TIME_BUDGET)
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--learning-rate", type=float, default=LEARNING_RATE)
    parser.add_argument("--eval-every", type=int, default=EVAL_EVERY)
    parser.add_argument("--eval-limit", type=int, default=EVAL_LIMIT)
    parser.add_argument("--final-eval-limit", type=int, default=FINAL_EVAL_LIMIT)
    parser.add_argument("--rl-steps", type=int, default=RL_STEPS)
    parser.add_argument("--rl-examples-per-step", type=int, default=RL_EXAMPLES_PER_STEP)
    parser.add_argument("--rl-samples-per-example", type=int, default=RL_SAMPLES_PER_EXAMPLE)
    parser.add_argument("--rl-max-new-tokens", type=int, default=RL_MAX_NEW_TOKENS)
    parser.add_argument("--rl-temperature", type=float, default=RL_TEMPERATURE)
    parser.add_argument("--rl-top-k", type=int, default=RL_TOP_K)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--compile", action="store_true", help="Compile the model when supported.")
    args = parser.parse_args()

    ensure_prepared()
    if FINAL_MODEL_DIR.exists():
        shutil.rmtree(FINAL_MODEL_DIR)

    torch.manual_seed(SEED)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(SEED)
        torch.set_float32_matmul_precision("high")

    device = pick_device(args.device)
    model = load_model(BASE_MODEL_DIR, device=device)
    train_model = torch.compile(model) if args.compile and device.type == "cuda" else model
    optimizer = configure_optimizer(model, args.learning_rate)
    autocast_ctx = (
        torch.amp.autocast(device_type="cuda", dtype=torch.bfloat16)
        if device.type == "cuda"
        else nullcontext()
    )
    state: dict[str, float | int | str] = {
        "best_score": -float("inf"),
        "best_step": 0,
        "best_phase": "none",
        "step": 0,
        "t0": time.time(),
    }

    print(f"device: {device}")
    print(f"base_model: {BASE_MODEL_DIR}")
    print(f"time_budget: {args.time_budget}s")
    print(f"sft_max_steps: {args.max_steps}")
    print(f"rl_steps: {args.rl_steps}")

    last_loss = run_sft(model, train_model, optimizer, args, device, autocast_ctx, state)
    run_reward_training(model, train_model, optimizer, args, device, state)

    if not FINAL_MODEL_DIR.exists():
        save_model(model, FINAL_MODEL_DIR)
        save_training_config(FINAL_MODEL_DIR, args, METHOD_NAME)

    final_model = load_model(FINAL_MODEL_DIR, device=device)
    final_metrics = score_model(final_model, limit=args.final_eval_limit, device=device)
    elapsed = time.time() - float(state["t0"])

    print("---")
    print(f"eval_score:         {float(final_metrics['eval_score']):.6f}")
    print(f"raw_accuracy:       {float(final_metrics['raw_accuracy']):.6f}")
    print(f"num_correct:        {final_metrics['num_correct']}")
    print(f"num_examples:       {final_metrics['num_examples']}")
    print(f"train_loss:         {last_loss:.6f}")
    print(f"training_seconds:   {elapsed:.1f}")
    print(f"best_step:          {state['best_step']}")
    print(f"best_phase:         {state['best_phase']}")
    print(f"best_limited_score: {float(state['best_score']):.6f}")
    print(f"final_model:        {FINAL_MODEL_DIR.resolve()}")
    print("task_scores:")
    for task_name, metrics in final_metrics["tasks"].items():
        print(f"  {task_name:12s}: {float(metrics['accuracy']):.6f} ({metrics['num_correct']}/{metrics['num_examples']})")


if __name__ == "__main__":
    main()
