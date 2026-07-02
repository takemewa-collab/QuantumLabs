"""runtime/memory_ingest.py — transcript -> chunk -> embed -> chroma (v0.4.0 B3a)."""
import json
import os
import subprocess
import sys

from runtime.memory_ingest import chunk_turns, ingest_session

SID = "2026-07-02_test"
EVENTS = [
    {"type": "user", "content": "config.py'de DEBUG kapat", "step": 0, "session_id": SID, "ts": "t0"},
    {"type": "assistant",
     "content": '{"thought":"once config.py oku","tool":"read_file","args":{"path":"config.py"}}',
     "step": 1, "session_id": SID, "ts": "t1"},
    {"type": "observation", "tool": "read_file", "ok": True, "content": "DEBUG = True",
     "step": 1, "session_id": SID, "ts": "t1"},
]


def _transcript(workspace, sid=SID):
    return os.path.join(workspace, ".quantumlabs", "transcripts", f"{sid}.jsonl")


def _write_jsonl(path, events):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def test_chunk_turns_groups(tmp_path):
    path = _transcript(str(tmp_path))
    _write_jsonl(path, EVENTS)

    turns = chunk_turns(path)
    assert len(turns) == 2                                  # user | assistant+observation
    assert turns[0].metadata["event_types"] == "user"
    assert turns[0].metadata["step"] == 0
    assert turns[1].metadata["event_types"] == "assistant,observation"
    assert turns[1].metadata["step"] == 1
    assert turns[1].metadata["session_id"] == SID
    assert "DEBUG = True" in turns[1].text                  # document: ham content korunur
    # embed-text temizligi: assistant JSON'dan yalniz 'thought'; tool/args YOK
    assert "once config.py oku" in turns[1].embed_text
    assert "read_file" not in turns[1].embed_text
    assert "args" not in turns[1].embed_text
    assert "DEBUG = True" in turns[1].embed_text            # observation embed'e dahil


def test_ingest_session_creates_index(tmp_path):
    _write_jsonl(_transcript(str(tmp_path)), EVENTS)
    n = ingest_session(SID, str(tmp_path))
    assert n == 2
    assert os.path.isdir(os.path.join(str(tmp_path), ".quantumlabs", "memory"))


def test_ingest_deterministic_no_duplicates(tmp_path):
    ws = str(tmp_path)
    _write_jsonl(_transcript(ws), EVENTS)
    assert ingest_session(SID, ws) == 2
    assert ingest_session(SID, ws) == 2          # ikinci kez: ayni ID'ler -> upsert
    from runtime.memory_ingest import _get_collection
    assert _get_collection(ws).count() == 2      # duplicate YOK (deterministik ID)


def test_missing_transcript_returns_zero(tmp_path):
    assert ingest_session("olmayan_oturum", str(tmp_path)) == 0


def test_import_is_side_effect_free():
    """Ayri surecte: import runtime.memory_ingest -> agir libler YUKLENMEZ (lazy)."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    code = (
        "import sys, runtime.memory_ingest\n"
        "assert 'chromadb' not in sys.modules, 'chromadb erken import edildi'\n"
        "assert 'sentence_transformers' not in sys.modules, 'sentence_transformers erken import edildi'\n"
        "print('lazy ok')\n"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=repo_root)
    assert r.returncode == 0, r.stderr
    assert "lazy ok" in r.stdout
