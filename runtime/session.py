"""QuantumLabs — Session (runtime): tum agent ve protokollerin paylastigi state.

Neden SINIF (modul-global degil): step degisken bir state. Global olsa, iki agent
paralel calisinca sayaclar birbirine karisirdi (multi-agent'in en sinsi bug'i).
Sinif olunca her agent kendi Session'ini tasir ya da ortak bir instance acikca
paylasilir; kim neyi paylasiyor gorunur olur.
"""

import datetime
import os


class Session:
    def __init__(self, workspace, model_config=None):
        self.workspace = os.path.abspath(workspace)
        self.session_id = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.started_at = datetime.datetime.now().isoformat()
        self.step = 0
        # LLM endpoint config'i (opaque; runtime katmani agents.llm'i IMPORT ETMEZ).
        # run_agent bunu model_config secim sirasinda kullanir. None -> env default.
        self.model_config = model_config

    def next_step(self):
        """Bir sonraki adim numarasini dondurur ve sayaci artirir."""
        self.step += 1
        return self.step

    def __repr__(self):
        return (f"Session(id={self.session_id}, step={self.step}, "
                f"workspace={self.workspace})")
