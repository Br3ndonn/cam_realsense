"""
verificar_caixaV5.py — Entry point do Sistema de Detecção de Nível da Cacamba V5

Uso:
    python verificar_caixaV5.py              # Câmera RealSense real
    python verificar_caixaV5.py --simulate   # Modo simulação (sem câmera)
"""

import argparse
import sys
import tkinter as tk
from pathlib import Path

# Garante que o diretório do script está no path para imports relativos
sys.path.insert(0, str(Path(__file__).parent))

from config_manager import ConfigManager
from gui_app import DetectorCacambaGUIV5


def main():
    parser = argparse.ArgumentParser(
        description="Sistema de Detecção de Nível da Cacamba V5"
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Rodar em modo simulação (sem câmera RealSense física)",
    )
    parser.add_argument(
        "--config",
        default="config_v5.json",
        help="Caminho do arquivo de configuração (padrão: config_v5.json)",
    )
    args = parser.parse_args()

    cm = ConfigManager(caminho_config=args.config)

    root = tk.Tk()
    app = DetectorCacambaGUIV5(root, config_manager=cm, simulate=args.simulate)  # noqa: F841
    root.mainloop()


if __name__ == "__main__":
    main()
