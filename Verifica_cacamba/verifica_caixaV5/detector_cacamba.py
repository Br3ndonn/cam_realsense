"""
detector_cacamba.py — Lógica pura de detecção de nível da cacamba (V5)

Sem GUI, sem threads. Recebe arrays numpy e retorna ResultadoDeteccao.
Corrige os problemas da V4:
  - Proteções contra pessoas reintroduzidas (ROI, aspect ratio, área, profundidade)
  - Confiança calculada com histórico real (deque)
  - Detecção de mudança de status com tempo mínimo
"""

import time
from collections import deque
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import cv2
import numpy as np


@dataclass
class ResultadoDeteccao:
    status: str = "SEM LEITURA"
    status_estavel: str = "SEM LEITURA"
    distancia: float = 0.0
    percentual: float = 0.0
    confianca: float = 0.0
    caixa_detectada: bool = False
    motivo_rejeicao: str = ""
    # Bounding box (x1, y1, x2, y2) no espaço do depth_meters
    bbox: Optional[Tuple[int, int, int, int]] = None


class DetectorCacamba:
    """
    Encapsula toda a lógica de detecção.
    Thread-safe para leitura (os métodos podem ser chamados de qualquer thread,
    mas a instância deve pertencer a UMA só thread por vez).
    """

    def __init__(self, cfg: dict):
        self._cfg = cfg
        n_hist = cfg["filtros"]["tamanho_historico"]
        n_dist = cfg["filtros"]["historico_distancias"]
        self._hist_status: deque = deque(maxlen=n_hist)
        self._hist_dist: deque = deque(maxlen=n_dist)
        self._hist_confianca: deque = deque(maxlen=30)
        self._status_anterior: Optional[str] = None
        self._ultima_mudanca: float = time.time()

    # ── Config ────────────────────────────────────────────────────────────────

    def atualizar_config(self, cfg: dict) -> None:
        self._cfg = cfg
        n_hist = cfg["filtros"]["tamanho_historico"]
        n_dist = cfg["filtros"]["historico_distancias"]
        if self._hist_status.maxlen != n_hist:
            self._hist_status = deque(list(self._hist_status), maxlen=n_hist)
        if self._hist_dist.maxlen != n_dist:
            self._hist_dist = deque(list(self._hist_dist), maxlen=n_dist)

    # ── Main processing ───────────────────────────────────────────────────────

    def processar_frame(
        self,
        depth_meters: np.ndarray,
    ) -> ResultadoDeteccao:
        """
        Processa um frame de profundidade.

        Args:
            depth_meters: array float32 com profundidades em metros.

        Returns:
            ResultadoDeteccao preenchido.
        """
        cfg = self._cfg

        PROF_MIN = cfg["medicoes"]["profundidade_min_caixa"]
        PROF_MAX = cfg["medicoes"]["profundidade_max_caixa"]
        AREA_MIN = cfg["medicoes"]["area_minima_pixels"]
        KERNEL = cfg["filtros"]["kernel_morph_size"]
        CLIP_MIN = cfg["camera"]["clip_min"]
        CLIP_MAX = cfg["camera"]["clip_max"]
        GRID = cfg["filtros"]["grid_medicao_size"]

        dh, dw = depth_meters.shape[:2]

        # Máscara de profundidade no range da cacamba
        mask = ((depth_meters > PROF_MIN) & (depth_meters < PROF_MAX)).astype(np.uint8) * 255
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (KERNEL, KERNEL))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        melhor_contorno = None
        maior_area = 0.0
        motivo_rejeicao = "Nenhum contorno no range de profundidade"

        for contour in contours:
            area = cv2.contourArea(contour)
            if area < AREA_MIN:
                continue
            valido, motivo = self._validar_deteccao(contour, depth_meters, dw, dh)
            if valido and area > maior_area:
                maior_area = area
                melhor_contorno = contour
                motivo_rejeicao = ""
            elif not valido:
                motivo_rejeicao = motivo

        resultado = ResultadoDeteccao()

        if melhor_contorno is not None:
            x1, y1, wb, hb = cv2.boundingRect(melhor_contorno)
            x2, y2 = x1 + wb, y1 + hb
            resultado.caixa_detectada = True
            resultado.bbox = (x1, y1, x2, y2)
            medicoes = self._medir_grid(depth_meters, x1, y1, x2, y2, GRID, CLIP_MIN, CLIP_MAX)
        else:
            resultado.motivo_rejeicao = motivo_rejeicao
            # Sem caixa detectada: não contaminar o histórico com leituras espúrias
            return resultado  # status = "SEM LEITURA"

        if not medicoes:
            # Box detectada mas sem pixels válidos no range clip
            return resultado  # status = "SEM LEITURA"

        distancia = float(np.median(medicoes))
        self._hist_dist.append(distancia)

        # Calcular percentual de preenchimento
        ALTURA_CAM = cfg["medicoes"]["altura_camera_chao"]
        ALTURA_CAIXA = max(cfg["medicoes"]["altura_caixa"], 0.001)
        percentual = max(0.0, min(100.0, ((ALTURA_CAM - distancia) / ALTURA_CAIXA) * 100))

        # Status instantâneo
        LIMITE_VAZIA = cfg["thresholds"]["limite_vazia"]
        LIMITE_CHEIA = cfg["thresholds"]["limite_cheia"]
        if distancia >= LIMITE_VAZIA:
            status_inst = "VAZIA"
        elif distancia <= LIMITE_CHEIA:
            status_inst = "CHEIA"
        else:
            status_inst = "PARCIAL"

        self._hist_status.append(status_inst)

        # Status estável: maioria dos últimos N frames
        if len(self._hist_status) >= 5:
            contagem = {s: list(self._hist_status).count(s) for s in ("VAZIA", "PARCIAL", "CHEIA")}
            status_est = max(contagem, key=contagem.get)
        else:
            status_est = status_inst

        # Confiança baseada em desvio padrão do histórico
        dist_validos = [d for d in self._hist_dist if d > 0]
        if len(dist_validos) > 1:
            std = float(np.std(dist_validos))
            confianca = max(0.0, min(100.0, 100.0 - std * 1000))
        else:
            confianca = 50.0
        self._hist_confianca.append(confianca)

        resultado.status = status_inst
        resultado.status_estavel = status_est
        resultado.distancia = distancia
        resultado.percentual = percentual
        resultado.confianca = confianca
        return resultado

    # ── Validação (proteção contra pessoas) ──────────────────────────────────

    def _validar_deteccao(
        self,
        contour,
        depth_meters: np.ndarray,
        w_frame: int,
        h_frame: int,
    ) -> Tuple[bool, str]:
        """
        Valida se um contorno é a cacamba e não uma pessoa.
        Implementa as 4 proteções documentadas no resumo_v4.md.
        """
        cfg = self._cfg
        area = cv2.contourArea(contour)
        x, y, w, h = cv2.boundingRect(contour)

        # 1. Aspect ratio — braços/pernas têm proporção muito alongada
        aspect = max(w, h) / max(min(w, h), 1)
        if aspect > 5.0:
            return False, f"Aspect ratio {aspect:.1f} > 5 (objeto muito alongado)"

        # 2. ROI — a cacamba fica na região central configurada
        cx_norm = (x + w / 2) / max(w_frame, 1)
        cy_norm = (y + h / 2) / max(h_frame, 1)
        roi = cfg["roi"]
        if not (roi["x_min"] < cx_norm < roi["x_max"]):
            return False, f"Fora da ROI horizontal (cx={cx_norm:.2f})"
        if not (roi["y_min"] < cy_norm < roi["y_max"]):
            return False, f"Fora da ROI vertical (cy={cy_norm:.2f})"

        # 3. Profundidade mínima — pessoas ficam muito próximas da câmera
        regiao = depth_meters[y : y + h, x : x + w]
        pixels_validos = regiao[(regiao > 0.05) & (regiao < 5.0)]
        if len(pixels_validos) < 10:
            return False, "Poucos pixels válidos na região"
        mediana_prof = float(np.median(pixels_validos))
        prof_min = cfg["protecao_pessoa"]["profundidade_minima_corpo"]
        if mediana_prof < prof_min:
            return False, f"Muito próximo ({mediana_prof:.2f}m < {prof_min}m)"

        # 4. Área máxima — pessoas ocupam muito mais área que a cacamba
        area_max = cfg["protecao_pessoa"]["area_maxima_corpo"]
        if area > area_max:
            return False, f"Área {area:.0f}px² > máximo {area_max}px²"

        return True, "OK"

    # ── Medição grid ──────────────────────────────────────────────────────────

    def _medir_grid(
        self,
        depth_meters: np.ndarray,
        x1: int, y1: int, x2: int, y2: int,
        grid_size: int,
        clip_min: float,
        clip_max: float,
    ) -> List[float]:
        """Mede profundidade em grade NxN; retorna lista de medianas por célula."""
        regiao = depth_meters[y1:y2, x1:x2]
        if regiao.size == 0:
            return []
        h_r, w_r = regiao.shape
        cell_h = max(1, h_r // grid_size)
        cell_w = max(1, w_r // grid_size)
        medicoes: List[float] = []
        for i in range(grid_size):
            for j in range(grid_size):
                ys = i * cell_h
                ye = (i + 1) * cell_h if i < grid_size - 1 else h_r
                xs = j * cell_w
                xe = (j + 1) * cell_w if j < grid_size - 1 else w_r
                celula = regiao[ys:ye, xs:xe]
                validos = celula[(celula > clip_min) & (celula < clip_max)]
                if len(validos) > 10:
                    medicoes.append(float(np.median(validos)))
        return medicoes

    # ── Helpers públicos ──────────────────────────────────────────────────────

    def confianca_media(self) -> float:
        if not self._hist_confianca:
            return 0.0
        return float(np.mean(self._hist_confianca))

    def detectou_mudanca_status(
        self, status_estavel: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Verifica se houve mudança de status respeitando o tempo mínimo entre mudanças.

        Returns:
            (True, status_anterior) se mudou e tempo suficiente passou.
            (False, None) caso contrário.
        """
        tempo_min = self._cfg["protecao_pessoa"]["tempo_minimo_entre_mudancas"]
        agora = time.time()
        if status_estavel != self._status_anterior and (agora - self._ultima_mudanca) > tempo_min:
            anterior = self._status_anterior
            self._status_anterior = status_estavel
            self._ultima_mudanca = agora
            return True, anterior
        return False, None

    def resetar_historicos(self) -> None:
        self._hist_status.clear()
        self._hist_dist.clear()
        self._hist_confianca.clear()
        self._status_anterior = None
        self._ultima_mudanca = time.time()
