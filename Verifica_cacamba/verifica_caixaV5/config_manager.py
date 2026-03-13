"""
config_manager.py — Gerenciamento de configurações e perfis (V5)
"""

import copy
import json
from pathlib import Path

CONFIG_PADRAO: dict = {
    "camera": {
        "resolucao_largura": 640,
        "resolucao_altura": 480,
        "fps": 30,
        "clip_min": 0.1,
        "clip_max": 2.0,
        "laser_potencia": 360,
    },
    "medicoes": {
        "altura_camera_chao": 0.725,
        "altura_caixa": 0.20,
        "profundidade_min_caixa": 0.45,
        "profundidade_max_caixa": 0.85,
        "area_minima_pixels": 5000,
    },
    "protecao_pessoa": {
        "profundidade_minima_corpo": 0.20,
        "area_maxima_corpo": 200000,
        "tempo_minimo_entre_mudancas": 1.0,
    },
    "roi": {
        "x_min": 0.25,
        "x_max": 0.75,
        "y_min": 0.25,
        "y_max": 0.85,
    },
    "thresholds": {
        "limite_vazia": 0.70,
        "limite_cheia": 0.55,
    },
    "filtros": {
        "tamanho_historico": 10,
        "historico_distancias": 30,
        "kernel_morph_size": 5,
        "grid_medicao_size": 3,
    },
    "visualizacao": {
        "mostrar_fps": True,
        "mostrar_grid": True,
        "mostrar_ir": True,
        "colormap": 2,
    },
    "sons": {
        "beep_mudanca_status": True,
        "beep_frequencia": 1000,
        "beep_duracao": 200,
    },
    "perfis": {},
}


class ConfigManager:
    """Carrega, salva e gerencia perfis de configuração."""

    def __init__(self, caminho_config: str = "config_v5.json"):
        self.caminho = Path(__file__).parent / caminho_config
        self._config = self._carregar()

    # ── Internals ────────────────────────────────────────────────────────────

    def _carregar(self) -> dict:
        base = copy.deepcopy(CONFIG_PADRAO)
        if self.caminho.exists():
            try:
                with open(self.caminho, "r", encoding="utf-8") as f:
                    dados = json.load(f)
                return self._merge(base, dados)
            except Exception as e:
                print(f"⚠️  Erro ao carregar config: {e}. Usando padrão.")
        # Criar arquivo com valores padrão
        self._gravar(base)
        return base

    def _merge(self, base: dict, override: dict) -> dict:
        """Merge recursivo: garante que todos os campos do padrão existam."""
        for k, v in override.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                self._merge(base[k], v)
            else:
                base[k] = v
        return base

    def _gravar(self, cfg: dict) -> None:
        with open(self.caminho, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def cfg(self) -> dict:
        return self._config

    def salvar(self) -> None:
        self._gravar(self._config)

    def atualizar(self, novos_valores: dict) -> None:
        """Merge parcial e persiste."""
        self._merge(self._config, novos_valores)
        self.salvar()

    # ── Profiles ─────────────────────────────────────────────────────────────

    def listar_perfis(self) -> list:
        return list(self._config.get("perfis", {}).keys())

    def salvar_perfil(self, nome: str) -> None:
        """Captura seções relevantes das configurações atuais como perfil."""
        secoes = ("medicoes", "thresholds", "roi", "protecao_pessoa", "filtros")
        perfil = {s: copy.deepcopy(self._config[s]) for s in secoes if s in self._config}
        self._config.setdefault("perfis", {})[nome] = perfil
        self.salvar()

    def carregar_perfil(self, nome: str) -> bool:
        """Aplica um perfil salvo sobre a config atual. Retorna True se encontrado."""
        perfil = self._config.get("perfis", {}).get(nome)
        if perfil is None:
            return False
        for secao, valores in perfil.items():
            if secao in self._config:
                self._config[secao].update(valores)
        self.salvar()
        return True

    def deletar_perfil(self, nome: str) -> bool:
        perfis = self._config.get("perfis", {})
        if nome in perfis:
            del perfis[nome]
            self.salvar()
            return True
        return False
