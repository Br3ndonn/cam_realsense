"""
verificar_caixaV6.py — Entry point do Sistema de Detecção de Nível da Cacamba V6

Nova feature: Volumetria 3D RealSense
"""

import argparse
import sys
import tkinter as tk
from pathlib import Path

# Garante que o diretório do script está no path para imports relativos
sys.path.insert(0, str(Path(__file__).parent))

from config_manager import ConfigManager
from gui_app import DetectorCacambaGUIV6

def main():
    parser = argparse.ArgumentParser(
        description="Sistema de Detecção de Nível da Cacamba V6 - Volumetria"
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Rodar em modo simulação (sem câmera RealSense física)",
    )
    parser.add_argument(
        "--config",
        default="config_v6.json",
        help="Caminho do arquivo de configuração (padrão: config_v6.json)",
    )
    args = parser.parse_args()

    cm = ConfigManager(caminho_config=args.config)

    root = tk.Tk()
    app = DetectorCacambaGUIV6(root, config_manager=cm, simulate=args.simulate)
    root.mainloop()

if __name__ == "__main__":
    main()
