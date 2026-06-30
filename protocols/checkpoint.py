"""QuantumLabs — Checkpoint sistemi (v5a): snapshot + rollback.

SafeEditProtocol'un temeli. Henuz agent akisina bagli DEGIL; once tek basina
test edilecek. Yapisal kural:
  .quantumlabs/checkpoints/<session>_<NNN>/
      metadata.json
      files/<dosyanin/repo/icindeki/yolu>

<session> : agent basladiginda BIR KEZ alinan zaman damgasi (sabit kalir).
<NNN>     : o oturumdaki her SafeEdit'in artan sayaci (001, 002, ...).
            En yuksek numara = en son degisiklik => LIFO geri-alma dogal gelir.
"""

import datetime
import json
import os
import shutil

CHECKPOINT_ROOT = ".quantumlabs/checkpoints"


def make_session_id():
    """Oturum basinda BIR KEZ cagrilir. Sabit kalir."""
    return datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")


def _next_index(workspace, session_id):
    """Bu oturum icin bir sonraki NNN numarasini bulur (mevcut klasorlere bakar)."""
    root = os.path.join(workspace, CHECKPOINT_ROOT)
    if not os.path.isdir(root):
        return 1
    prefix = session_id + "_"
    nums = []
    for name in os.listdir(root):
        if name.startswith(prefix):
            tail = name[len(prefix):]
            if tail.isdigit():
                nums.append(int(tail))
    return (max(nums) + 1) if nums else 1


def take_snapshot(workspace, session_id, changed_files, task="", tool=""):
    """Dosyalar DEGISMEDEN ONCE cagrilir. Mevcut hallerini yedekler.

    changed_files: repo'ya goreceli yollar listesi (orn: ['agents/x.py']).
    Geri donus: checkpoint klasorunun mutlak yolu.
    """
    idx = _next_index(workspace, session_id)
    ckpt_name = f"{session_id}_{idx:03d}"
    ckpt_dir = os.path.join(workspace, CHECKPOINT_ROOT, ckpt_name)
    files_dir = os.path.join(ckpt_dir, "files")
    os.makedirs(files_dir, exist_ok=True)

    existed = {}  # dosya snapshot aninda var miydi? (yeni dosya tespiti icin)
    for rel in changed_files:
        src = os.path.join(workspace, rel)
        if os.path.exists(src):
            dst = os.path.join(files_dir, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            existed[rel] = True
        else:
            existed[rel] = False

    metadata = {
        "task": task,
        "tool": tool,
        "changed_files": list(changed_files),
        "existed": existed,
        "created_at": datetime.datetime.now().isoformat(),
        "status": "pending",
    }
    with open(os.path.join(ckpt_dir, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    return ckpt_dir


def _load_meta(ckpt_dir):
    with open(os.path.join(ckpt_dir, "metadata.json"), "r", encoding="utf-8") as f:
        return json.load(f)


def _save_meta(ckpt_dir, meta):
    with open(os.path.join(ckpt_dir, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def accept(ckpt_dir):
    """Kullanici degisikligi kabul etti. Snapshot durur (status: accepted)."""
    meta = _load_meta(ckpt_dir)
    meta["status"] = "accepted"
    _save_meta(ckpt_dir, meta)


def rollback(workspace, ckpt_dir):
    """Kullanici reddetti. Dosyalari snapshot'taki haline geri yukler.

    - Snapshot aninda VAR olan dosya  -> eski icerigi geri yazilir.
    - Snapshot aninda YOK olan dosya  -> (yeni olusturulmus) SILINIR.
    """
    meta = _load_meta(ckpt_dir)
    files_dir = os.path.join(ckpt_dir, "files")
    for rel in meta["changed_files"]:
        target = os.path.join(workspace, rel)
        if meta["existed"].get(rel):
            backup = os.path.join(files_dir, rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(backup, target)
        else:
            if os.path.exists(target):
                os.remove(target)
    meta["status"] = "rolled_back"
    _save_meta(ckpt_dir, meta)


def atomic_write(workspace, rel, content):
    """Dosyayi atomik yazar: gecici dosyaya yaz + os.replace.
    Boylece yazma yarida kesilse bile orijinal bozulmaz."""
    target = os.path.join(workspace, rel)
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    tmp = target + ".qltmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp, target)
