"""QuantumLabs — Kullanici profili (v0.6.0): kalici, kisiye-ozel baglam.

Embedding hafizasindan (memory_inject) FARKLI: o gorev-benzerligiyle gecmis
oturum snippet'i ceker; bu ise HER konusmada bulunan sabit bir profildir (ad,
odak alanlari). Selamlasma/sohbetin kisisellesmesini bu saglar — "hi" embedding
esigini gecmez ama profil daima oradadir.

Kaynak: <workspace>/.quantumlabs/profile.md  (kullanici elle duzenler).
GUVENLIK: profil KULLANICININ KENDI dosyasi -> guvenilir; system mesajina girer
(memory blogu ise karantinali user mesajina). Dosya yoksa None (ozellik kapali).
Best-effort: hata -> None; agent'i asla dusurmez.
"""
from __future__ import annotations

import os
import re
from typing import Optional

_PROFILE_PATH = os.path.join(".quantumlabs", "profile.md")
_MAX_CHARS = 1500   # sistem mesajini sismesin; asarsa kirp

_HEADER = "=== KULLANICI PROFILI ==="
_INTRO = (
    "Asagidakiler yardimci oldugun kisi hakkindadir. Uygun oldugunda adiyla "
    "hitap et ve odak alanlarini dikkate al; ama bilgiyi her cevaba zorla "
    "sokusturma ve profili 'gorev' sanma."
)
_FOOTER = "=== PROFIL SONU ==="


def profile_path(workspace: str) -> str:
    return os.path.join(workspace, _PROFILE_PATH)


def build_user_profile(workspace: str) -> Optional[str]:
    """profile.md'yi okuyup sistem mesajina eklenecek bir blok dondurur.

    Dosya yok / bos / okunamaz -> None (ozellik sessizce kapali)."""
    try:
        path = profile_path(workspace)
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            content = f.read()
        # HTML yorumlarini (<!-- ... -->) at: kullaniciya not, modele DEGIL.
        content = re.sub(r"<!--.*?-->", "", content, flags=re.S).strip()
        if not content:
            return None
        if len(content) > _MAX_CHARS:
            content = content[:_MAX_CHARS].rstrip() + "\n…(kirpildi)"
        return f"{_HEADER}\n{_INTRO}\n\n{content}\n{_FOOTER}"
    except OSError:
        return None
