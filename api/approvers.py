"""QuantumLabs API — approver'lar (v0.5.0 S1b).

Web'de interaktif onay akisi HENUZ YOK (S2). O gelene kadar guvenlik default'u
DENY: her yazma/degistirme reddedilir. AutoApprover ASLA kullanilmaz — web'de
onaysiz dosya yazmaya izin vermek kabul edilemez.
"""
from protocols.safety import ApprovalResult


class DenyAllApprover:
    """Approver protokolu: request(proposal) -> ApprovalResult. Hep reddeder."""

    def request(self, proposal):
        return ApprovalResult.deny("web onay akisi henuz yok (S2)")
