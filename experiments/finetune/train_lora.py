#!/usr/bin/env python3
"""
train_lora.py — LoRA / QLoRA fine-tuning of a Qwen3 base model on a small
multilingual instruction set, using transformers + peft + trl.

This script sets EVERYTHING up — model, tokenizer, LoRA config, and the TRL
SFTTrainer loop — but only starts training when you actually invoke it on a
machine with a CUDA GPU. There is no auto-run on import.

Typical GPU usage (see README.md):
    python train_lora.py                       # defaults: Qwen3-1.7B-Base, bf16 LoRA
    python train_lora.py --use-4bit            # QLoRA (4-bit) for larger models / less VRAM
    python train_lora.py --model Qwen/Qwen3-4B-Base --use-4bit

Prerequisite: run prepare_data.py first to create data/train.jsonl + data/val.jsonl.
"""

import argparse
import os
from pathlib import Path

HERE = Path(__file__).parent

# ChatML template — Qwen3 *base* models ship without a chat template, so we set
# one explicitly. This matches Qwen's instruct format.
CHATML_TEMPLATE = (
    "{% for message in messages %}"
    "{{ '<|im_start|>' + message['role'] + '\n' + message['content'] + '<|im_end|>' + '\n' }}"
    "{% endfor %}"
    "{% if add_generation_prompt %}{{ '<|im_start|>assistant\n' }}{% endif %}"
)

# Qwen3 attention + MLP projection modules that LoRA adapters attach to.
LORA_TARGET_MODULES = [
    "q_proj",
    "k_proj",
    "v_proj",
    "o_proj",
    "gate_proj",
    "up_proj",
    "down_proj",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="LoRA fine-tune Qwen3 (multilingual).")

    # Model / data
    p.add_argument("--model", default="Qwen/Qwen3-1.7B-Base",
                   help="Base model id (e.g. Qwen/Qwen3-0.6B-Base, Qwen/Qwen3-4B-Base).")
    p.add_argument("--data-dir", default=str(HERE / "data"),
                   help="Directory containing train.jsonl / val.jsonl.")
    p.add_argument("--output-dir", default=str(HERE / "outputs" / "qwen3-lora-multilingual"),
                   help="Where checkpoints + adapter are saved.")

    # Quantization
    p.add_argument("--use-4bit", action="store_true",
                   help="Enable 4-bit QLoRA (bitsandbytes, CUDA only).")

    # LoRA hyperparameters
    p.add_argument("--lora-r", type=int, default=16)
    p.add_argument("--lora-alpha", type=int, default=32)
    p.add_argument("--lora-dropout", type=float, default=0.05)

    # Training hyperparameters
    p.add_argument("--epochs", type=float, default=1.0)
    p.add_argument("--batch-size", type=int, default=2)
    p.add_argument("--grad-accum", type=int, default=8)
    p.add_argument("--lr", type=float, default=2e-4)
    p.add_argument("--max-seq-len", type=int, default=2048)
    p.add_argument("--warmup-ratio", type=float, default=0.03)
    p.add_argument("--logging-steps", type=int, default=10)
    p.add_argument("--save-steps", type=int, default=200)
    p.add_argument("--seed", type=int, default=42)

    # Safety: require an explicit flag OR a real GPU before training starts.
    p.add_argument("--force-cpu", action="store_true",
                   help="Allow running without a CUDA GPU (NOT recommended; very slow).")
    return p.parse_args()


def build_model_and_tokenizer(args):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    quant_config = None
    if args.use_4bit:
        quant_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
        )

    print(f"Loading tokenizer: {args.model}")
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    # Base models lack a chat template — give them ChatML.
    if tokenizer.chat_template is None:
        tokenizer.chat_template = CHATML_TEMPLATE

    print(f"Loading model: {args.model} (4bit={args.use_4bit})")
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        quantization_config=quant_config,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )
    model.config.use_cache = False  # required with gradient checkpointing

    if args.use_4bit:
        from peft import prepare_model_for_kbit_training
        model = prepare_model_for_kbit_training(model)

    return model, tokenizer


def main() -> None:
    args = parse_args()

    import torch

    if not torch.cuda.is_available() and not args.force_cpu:
        raise SystemExit(
            "No CUDA GPU detected. This script is configured for GPU training.\n"
            "Run it on a CUDA machine, or pass --force-cpu to override (very slow,\n"
            "and --use-4bit / bitsandbytes will not work on CPU)."
        )

    from datasets import load_dataset
    from peft import LoraConfig
    from trl import SFTConfig, SFTTrainer

    train_path = Path(args.data_dir) / "train.jsonl"
    val_path = Path(args.data_dir) / "val.jsonl"
    if not train_path.exists():
        raise SystemExit(f"Missing {train_path}. Run prepare_data.py first.")

    data_files = {"train": str(train_path)}
    if val_path.exists():
        data_files["validation"] = str(val_path)
    dataset = load_dataset("json", data_files=data_files)

    model, tokenizer = build_model_and_tokenizer(args)

    lora_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=LORA_TARGET_MODULES,
    )

    sft_config = SFTConfig(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        warmup_ratio=args.warmup_ratio,
        lr_scheduler_type="cosine",
        logging_steps=args.logging_steps,
        save_steps=args.save_steps,
        save_total_limit=2,
        bf16=True,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        max_length=args.max_seq_len,
        packing=False,
        optim="paged_adamw_8bit" if args.use_4bit else "adamw_torch",
        report_to="none",
        seed=args.seed,
        # SFTTrainer applies the tokenizer's chat template to the "messages" column.
    )

    trainer = SFTTrainer(
        model=model,
        args=sft_config,
        train_dataset=dataset["train"],
        eval_dataset=dataset.get("validation"),
        peft_config=lora_config,
        processing_class=tokenizer,
    )

    print("\n=== Setup complete. Starting training... ===")
    trainer.train()

    final_dir = Path(args.output_dir) / "final-adapter"
    trainer.save_model(str(final_dir))
    tokenizer.save_pretrained(str(final_dir))
    print(f"\nTraining done. LoRA adapter saved to: {final_dir}")


if __name__ == "__main__":
    main()
