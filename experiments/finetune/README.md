# Qwen3 Multilingual LoRA Fine-tuning

LoRA / QLoRA fine-tuning of a **Qwen3 base** model on a small **multilingual**
instruction dataset (`CohereForAI/aya_dataset`), using
**transformers + peft + trl**.

Everything here is **GPU-ready but not started** — you set it up on any machine,
then run the training step on a CUDA GPU.

```
experiments/finetune/
├── prepare_data.py     # download + format the dataset (CPU only)
├── train_lora.py       # LoRA/QLoRA training loop (needs CUDA GPU)
├── requirements.txt    # transformers, peft, trl, datasets, accelerate, bitsandbytes
├── README.md           # this file
├── data/               # generated train.jsonl / val.jsonl (gitignored)
└── outputs/            # checkpoints + final adapter (gitignored)
```

---

## Step-by-step: run on a GPU

### 1. Get on a CUDA GPU machine
Any NVIDIA GPU works. Rough VRAM guidance (with `--use-4bit` QLoRA):

| Model                  | bf16 LoRA | 4-bit QLoRA |
|------------------------|-----------|-------------|
| `Qwen/Qwen3-0.6B-Base` | ~6 GB     | ~3 GB       |
| `Qwen/Qwen3-1.7B-Base` | ~12 GB    | ~5 GB       |
| `Qwen/Qwen3-4B-Base`   | ~24 GB    | ~9 GB       |
| `Qwen/Qwen3-8B-Base`   | ~40 GB    | ~14 GB      |

### 2. Create a Python 3.10+ environment
> The repo's `.python-version` is 3.9, but modern transformers/trl/Qwen3 need
> **Python ≥ 3.10**. Use a fresh venv on the GPU box.

```bash
cd experiments/finetune
python3.10 -m venv .venv && source .venv/bin/activate
# or:  uv venv --python 3.10 && source .venv/bin/activate
```

### 3. Install dependencies
Install the CUDA build of PyTorch first, then the rest:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt
```

### 4. (Optional) Log in to Hugging Face
The aya dataset is open, but logging in avoids rate limits:

```bash
huggingface-cli login
```

### 5. Prepare the data (CPU only)
```bash
python prepare_data.py
# customise:
python prepare_data.py --languages English Turkish Arabic --max-per-lang 500
```
Writes `data/train.jsonl` and `data/val.jsonl`.

### 6. Launch training
```bash
# bf16 LoRA (small models / plenty of VRAM)
python train_lora.py --model Qwen/Qwen3-1.7B-Base

# 4-bit QLoRA (larger models / limited VRAM)
python train_lora.py --model Qwen/Qwen3-4B-Base --use-4bit
```

Useful flags: `--epochs`, `--batch-size`, `--grad-accum`, `--lr`,
`--lora-r`, `--lora-alpha`, `--max-seq-len`. See `python train_lora.py --help`.

> **Safety:** `train_lora.py` refuses to run without a CUDA GPU unless you pass
> `--force-cpu`. This prevents accidental (extremely slow) CPU training.

### 7. Multi-GPU (optional)
```bash
accelerate config           # one-time
accelerate launch train_lora.py --model Qwen/Qwen3-4B-Base --use-4bit
```

### 8. Output
The trained LoRA adapter lands in:
```
outputs/qwen3-lora-multilingual/final-adapter/
```

Load it for inference:
```python
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

base = "Qwen/Qwen3-1.7B-Base"
adapter = "outputs/qwen3-lora-multilingual/final-adapter"

tok = AutoTokenizer.from_pretrained(adapter)
model = AutoModelForCausalLM.from_pretrained(base, device_map="auto")
model = PeftModel.from_pretrained(model, adapter)

msgs = [{"role": "user", "content": "Merhaba, nasılsın?"}]
inputs = tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt").to(model.device)
print(tok.decode(model.generate(inputs, max_new_tokens=128)[0]))
```

To merge the adapter into the base weights:
```python
merged = model.merge_and_unload()
merged.save_pretrained("outputs/qwen3-merged")
```

---

## Notes
- **Dataset:** `CohereForAI/aya_dataset` — open, human-annotated instructions in
  ~65 languages. `prepare_data.py` filters to a few languages and caps rows so
  the run stays fast/cheap; widen `--languages` / raise `--max-per-lang` to scale.
- **bitsandbytes is CUDA-only** — it won't install on macOS/Apple Silicon. You
  only need it for `--use-4bit`.
- **Base vs Instruct:** we fine-tune the `*-Base` model and apply a ChatML chat
  template ourselves (base models ship without one).
