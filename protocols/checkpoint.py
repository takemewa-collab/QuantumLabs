"""QuantumLabs — Checkpoint sistemi (v5a-r): snapshot + rollback.

Session'a bagli versiyon. ONEMLI: bu modul runtime/session'i IMPORT ETMEZ;
sadece 'workspace' ve 'session_id' ozelligi olan bir nesne (duck typing) bekler.
Boylece protocols katmani runtime'a siki bagimli olmaz, test etmesi de kolaydir.

Yapisal kural:
  .quantumlabs/checkpoints/<session_id>_<NNN>/
      metadata.json
      files/<dosyanin/repo/icindeki/yolu>
"""

import datetime
import json
import os
import shutil

CHECKPOINT_ROOT = ".quantumlabs/checkpoints"


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


def take_snapshot(session, changed_files, task="", tool=""):
    """Dosyalar DEGISMEDEN ONCE cagrilir. Mevcut hallerini yedekler.

    session: workspace ve session_id ozelligi olan nesne (Session).
    changed_files: repo'ya goreceli yollar listesi (orn: ['agents/x.py']).
    Geri donus: checkpoint klasorunun mutlak yolu.
    """
    workspace = session.workspace
    session_id = session.session_id
    idx = _next_index(workspace, session_id)
    ckpt_name = f"{session_id}_{idx:03d}"
    ckpt_dir = os.path.join(workspace, CHECKPOINT_ROOT, ckpt_name)
    files_dir = os.path.join(ckpt_dir, "files")
    os.makedirs(files_dir, exist_ok=True)

    existed = {}
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


def rollback(session, ckpt_dir):
    """Kullanici reddetti. Dosyalari snapshot'taki haline geri yukler.

    - Snapshot aninda VAR olan dosya  -> eski icerigi geri yazilir.
    - Snapshot aninda YOK olan dosya  -> (yeni olusturulmus) SILINIR.
    """
    workspace = session.workspace
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


def atomic_write(session, rel, content):
    """Dosyayi atomik yazar: gecici dosyaya yaz + os.replace."""
    target = os.path.join(session.workspace, rel)
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    tmp = target + ".qltmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp, target)
