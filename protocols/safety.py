"""
agents/safety.py

Write/edit operations için onay (human-in-the-loop) katmanı.

Tasarım:
    EditProposal      -> diske yazılmadan ÖNCE neyin değişeceğini tarif eder (diff üretir)
    ApprovalResult    -> approve / deny + gerekçe
    Approver          -> "evet/hayır" diyebilen her şeyin sözleşmesi (Protocol)
    TerminalApprover  -> CLI'da diff gösterip y/N soran somut approver
    AutoApprover      -> test / end-to-end run'larda input beklemeden geçen approver
    SafeEditProtocol  -> write_file() ve replace_text()'i approver'dan geçirip diske basan orkestratör

Approver bir Protocol olduğu için ileride çok-kullanıcılı dağıtımda
WebApprover yazıp SafeEditProtocol'e dokunmadan takarsın.

Python 3.9 uyumlu.
"""
from __future__ import annotations

import difflib
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Protocol, Union, runtime_checkable

# Public yüzey. Pakete bölününce safety/__init__.py bunu birebir re-export eder,
# böylece `from ...safety import X` çağrıları hiç değişmez.
__all__ = [
    # -> approver.py
    "Decision", "ApprovalResult", "Approver", "TerminalApprover", "AutoApprover",
    # -> safe_edit.py
    "EditProposal", "EditOutcome", "SafeEditProtocol",
    # -> diff.py
    "unified_diff",
]


# --------------------------------------------------------------------------- #
# Diff yardımcıları   (ileride: safety/diff.py)
# --------------------------------------------------------------------------- #
def unified_diff(old: Optional[str], new: str, path: str, context: int = 3) -> str:
    old_lines = (old or "").splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(
            old_lines, new_lines,
            fromfile=f"a/{path}", tofile=f"b/{path}", n=context,
        )
    )


# --------------------------------------------------------------------------- #
# Veri tipleri
# --------------------------------------------------------------------------- #
class Decision(str, Enum):
    APPROVE = "approve"
    DENY = "deny"


@dataclass
class EditProposal:
    """Diske yazılmadan önce önerilen değişiklik."""
    path: str
    new_content: str
    old_content: Optional[str] = None   # None => dosya henüz yok (yeni dosya)
    kind: str = "write"                 # "write" | "replace"
    summary: str = ""

    @property
    def is_new_file(self) -> bool:
        return self.old_content is None

    def unified_diff(self, context: int = 3) -> str:
        return unified_diff(self.old_content, self.new_content, self.path, context)


@dataclass
class CommandProposal:
    """Bir kabuk komutu calistirilmadan once onay icin (EditProposal'in kardesi).

    Ortak taban yerine 'kind' discriminator: approver'lar kind=='command' gorunce
    komut dalina gider, aksi halde (write/replace) diff dalina."""
    command: str
    cwd: str
    kind: str = "command"
    summary: str = ""


# Approver'lara giren proposal tipleri (kind ile ayrilir).
Proposal = Union[EditProposal, CommandProposal]


@dataclass
class ApprovalResult:
    decision: Decision
    reason: str = ""
    approver: str = ""     # karari kim verdi: "web" / "terminal" / "auto" (opsiyonel iz)

    @property
    def approved(self) -> bool:
        return self.decision is Decision.APPROVE

    @classmethod
    def approve(cls, reason: str = "") -> "ApprovalResult":
        return cls(Decision.APPROVE, reason)

    @classmethod
    def deny(cls, reason: str = "") -> "ApprovalResult":
        return cls(Decision.DENY, reason)


@dataclass
class EditOutcome:
    """Tool katmanına dönen sonuç. `message` doğrudan ReAct gözlemi olarak beslenebilir."""
    applied: bool
    path: str
    message: str


# --------------------------------------------------------------------------- #
# Approver sözleşmesi + implementasyonlar
# --------------------------------------------------------------------------- #
@runtime_checkable
class Approver(Protocol):
    def request(self, proposal: Proposal) -> ApprovalResult:
        ...


_GREEN = "\033[32m"
_RED = "\033[31m"
_DIM = "\033[2m"
_RESET = "\033[0m"


class TerminalApprover:
    """CLI'da diff gösterip onay ister."""

    def __init__(self, *, color: bool = True, max_preview_lines: int = 60):
        self.color = color
        self.max_preview_lines = max_preview_lines

    def _c(self, text: str, code: str) -> str:
        return f"{code}{text}{_RESET}" if self.color else text

    def request(self, proposal: Proposal) -> ApprovalResult:
        if getattr(proposal, "kind", "") == "command":
            print()
            print(f"┌─ Önerilen komut (cwd: {proposal.cwd})")
            print(f"│  {proposal.command}")
            print("└─ " + "─" * 50)
            ans = input("   Bu komutu çalıştır? [y/N] ").strip().lower()
            if ans in ("y", "yes", "e", "evet"):
                return ApprovalResult.approve()
            return ApprovalResult.deny("kullanıcı terminalde reddetti")
        print()
        print(f"┌─ Önerilen {proposal.kind}: {proposal.path}")
        if proposal.summary:
            print(f"│  {proposal.summary}")
        print("├─ " + "─" * 50)

        if proposal.is_new_file:
            lines = proposal.new_content.splitlines()
            print(f"│  (yeni dosya, {len(lines)} satır)")
            for line in lines[: self.max_preview_lines]:
                print("│ " + self._c(f"+ {line}", _GREEN))
            if len(lines) > self.max_preview_lines:
                print(self._c(f"│   … +{len(lines) - self.max_preview_lines} satır daha", _DIM))
        else:
            diff_lines = proposal.unified_diff().splitlines()
            for line in diff_lines[: self.max_preview_lines * 2]:
                if line.startswith("+") and not line.startswith("+++"):
                    print("│ " + self._c(line, _GREEN))
                elif line.startswith("-") and not line.startswith("---"):
                    print("│ " + self._c(line, _RED))
                else:
                    print("│ " + self._c(line, _DIM))

        print("└─ " + "─" * 50)
        ans = input("   Bu değişikliği uygula? [y/N] ").strip().lower()
        if ans in ("y", "yes", "e", "evet"):
            return ApprovalResult.approve()
        return ApprovalResult.deny("kullanıcı terminalde reddetti")


class AutoApprover:
    """Test / non-interaktif run'lar için. Varsayılan: hepsini onayla."""

    def __init__(self, approve: bool = True):
        self._approve = approve

    def request(self, proposal: EditProposal) -> ApprovalResult:
        return ApprovalResult.approve("auto") if self._approve else ApprovalResult.deny("auto")


# --------------------------------------------------------------------------- #
# Orkestratör
# --------------------------------------------------------------------------- #
class SafeEditProtocol:
    """
    write_file / replace_text'i approver'dan geçirir, sadece onaylanırsa diske yazar.
    Hata durumlarında exception fırlatmak yerine EditOutcome döner; böylece
    ReAct döngüsü temiz bir gözlem alır ve toparlanabilir.
    """

    def __init__(self, approver: Approver, *, root: Optional[str] = None, session=None):
        self.approver = approver
        self.root = Path(root).resolve() if root else None
        # session verilirse (workspace + session_id ozelligi olan nesne) yazma
        # islemleri checkpoint'lenir; None ise eski (checkpoint'siz) davranis korunur.
        self.session = session

    def _session_rel(self, target: Path) -> str:
        """checkpoint API'si workspace'e goreceli yol bekler.

        _resolve() symlink'leri cozer (Path.resolve), Session.workspace ise sadece
        abspath'tir; macOS'ta /var -> /private/var gibi farklar relpath'i bozar.
        Iki tarafi da realpath ile normalize ederek tutarli relatif yol uretiriz.
        """
        return os.path.relpath(os.path.realpath(target), os.path.realpath(self.session.workspace))

    def _commit(self, target: Path, content: str, *, tool: str, summary: str) -> None:
        """Diske yaz. session varsa: snapshot -> atomic_write -> accept."""
        if self.session is not None:
            from . import checkpoint
            rel = self._session_rel(target)
            ckpt_dir = checkpoint.take_snapshot(self.session, [rel], task=summary, tool=tool)
            checkpoint.atomic_write(self.session, rel, content)
            checkpoint.accept(ckpt_dir)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)

    def _resolve(self, path: str) -> Path:
        p = Path(path)
        if self.root is not None:
            p = p if p.is_absolute() else (self.root / p)
            p = p.resolve()
            try:                                  # workspace dışına çıkışı engelle
                p.relative_to(self.root)
            except ValueError:
                raise PermissionError(f"path workspace kökünün dışına çıkıyor: {path}")
        return p

    def write_file(self, path: str, content: str) -> EditOutcome:
        target = self._resolve(path)
        old = target.read_text() if target.exists() else None
        proposal = EditProposal(
            path=path, new_content=content, old_content=old, kind="write",
            summary="dosyayı üzerine yaz" if old is not None else "yeni dosya oluştur",
        )
        result = self.approver.request(proposal)
        if not result.approved:
            return EditOutcome(False, path, f"REDDEDİLDİ: {result.reason}")
        self._commit(target, content, tool="write_file", summary=proposal.summary)
        return EditOutcome(True, path, f"{len(content)} byte yazıldı -> {path}")

    def replace_text(self, path: str, old_text: str, new_text: str, *, count: int = 1) -> EditOutcome:
        target = self._resolve(path)
        if not target.exists():
            return EditOutcome(False, path, f"HATA: dosya yok: {path}")

        current = target.read_text()
        occurrences = current.count(old_text)
        if occurrences == 0:
            return EditOutcome(False, path, "HATA: old_text bulunamadı (değişiklik yok)")
        # Tekil değişiklik istenip birden fazla eşleşme varsa: sessizce yanlış yeri
        # değiştirmek yerine dur ve daha fazla bağlam iste.
        if count == 1 and occurrences > 1:
            return EditOutcome(
                False, path,
                f"HATA: old_text belirsiz ({occurrences} eşleşme). "
                "Benzersiz olması için etrafına bağlam ekle.",
            )

        updated = current.replace(old_text, new_text, count if count > 0 else -1)
        changed = occurrences if count <= 0 else min(count, occurrences)
        proposal = EditProposal(
            path=path, new_content=updated, old_content=current, kind="replace",
            summary=f"{changed} eşleşme değiştir",
        )
        result = self.approver.request(proposal)
        if not result.approved:
            return EditOutcome(False, path, f"REDDEDİLDİ: {result.reason}")
        self._commit(target, updated, tool="replace_text", summary=proposal.summary)
        return EditOutcome(True, path, f"{path} içinde metin değiştirildi ({changed} yer)")


# --------------------------------------------------------------------------- #
# code_agent.py tarafında tool kaydı (örnek)
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    # end-to-end run'da TerminalApprover, testte AutoApprover() koy
    _protocol = SafeEditProtocol(TerminalApprover(), root=".")

    def write_file(path: str, content: str) -> str:
        return _protocol.write_file(path, content).message

    def replace_text(path: str, old_text: str, new_text: str) -> str:
        return _protocol.replace_text(path, old_text, new_text).message

    # hızlı duman testi
    print(write_file("tmp_demo.txt", "satir1\nsatir2\n"))
    print(replace_text("tmp_demo.txt", "satir2", "DEĞİŞTİ"))
