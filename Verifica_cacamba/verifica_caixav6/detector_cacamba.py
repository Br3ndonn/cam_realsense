"""
detector_cacamba.py — Lógica de detecção e VOLUMETRIA 3D (V6)

Objetivo:
  1. Detectar espaço de volume da caçamba vazia (referência)
  2. Calcular volume do material dentro da caçamba (m³)
  3. Determinar status (VAZIA, PARCIAL, CHEIA) baseado em volumetria
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
    percentual: float = 0.0  # Percentual linear (baseado em profundidade central)
    percentual_volumetrico: float = 0.0 # Percentual baseado em Volume ocupado / Volume total
    volume_material_m3: float = 0.0
    volume_vazio_m3: float = 0.0
    confianca: float = 0.0
    caixa_detectada: bool = False
    motivo_rejeicao: str = ""
    bbox: Optional[Tuple[int, int, int, int]] = None


class DetectorCacamba:
    """
    Encapsula lógica de detecção e cálculo volumétrico 3D.
    """

    def __init__(self, cfg: dict):
        self._cfg = cfg
        n_hist = cfg["filtros"]["tamanho_historico"]
        n_dist = cfg["filtros"]["historico_distancias"]
        self._hist_status: deque = deque(maxlen=n_hist)
        self._hist_dist: deque = deque(maxlen=n_dist)
        self._hist_vol: deque = deque(maxlen=n_dist)
        self._hist_confianca: deque = deque(maxlen=30)
        self._status_anterior: Optional[str] = None
        self._ultima_mudanca: float = time.time()

    def atualizar_config(self, cfg: dict) -> None:
        self._cfg = cfg
        n_hist = cfg["filtros"]["tamanho_historico"]
        n_dist = cfg["filtros"]["historico_distancias"]
        if self._hist_status.maxlen != n_hist:
            self._hist_status = deque(list(self._hist_status), maxlen=n_hist)
        if self._hist_dist.maxlen != n_dist:
            self._hist_dist = deque(list(self._hist_dist), maxlen=n_dist)
        if self._hist_vol.maxlen != n_dist:
            self._hist_vol = deque(list(self._hist_vol), maxlen=n_dist)

    def processar_frame_3d(
        self,
        depth_meters: np.ndarray,
        verts_xyz: Optional[np.ndarray] = None,
    ) -> ResultadoDeteccao:
        """
        Realiza a volumetria 3D integrando a altura de cada ponto.
        """
        if verts_xyz is None:
            return self.processar_frame(depth_meters)

        cfg = self._cfg
        dh, dw = depth_meters.shape[:2]

        # 1. Detecção da Bounding Box (Mascara de profundidade)
        PROF_MIN = cfg["medicoes"]["profundidade_min_caixa"]
        PROF_MAX = cfg["medicoes"]["profundidade_max_caixa"]
        AREA_MIN = cfg["medicoes"]["area_minima_pixels"]
        KERNEL = cfg["filtros"]["kernel_morph_size"]

        mask = ((depth_meters > PROF_MIN) & (depth_meters < PROF_MAX)).astype(np.uint8) * 255
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (KERNEL, KERNEL))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        melhor_contorno = None
        maior_area = 0.0
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < AREA_MIN: continue
            valido, _ = self._validar_deteccao(contour, depth_meters, dw, dh)
            if valido and area > maior_area:
                maior_area = area
                melhor_contorno = contour

        resultado = ResultadoDeteccao()
        if melhor_contorno is None:
            return resultado

        x1, y1, wb, hb = cv2.boundingRect(melhor_contorno)
        resultado.caixa_detectada = True
        resultado.bbox = (x1, y1, x1 + wb, y1 + hb)

        # 2. Reshape e Recorte 3D
        if verts_xyz.shape[0] == dh * dw:
            verts_3d = verts_xyz.reshape(dh, dw, 3)
        else:
            return self.processar_frame(depth_meters)

        box_3d = verts_3d[y1:y1+hb, x1:x1+wb]
        x_coords = box_3d[:, :, 0]
        y_coords = box_3d[:, :, 1]
        z_coords = box_3d[:, :, 2]

        # Filtros de ruído e clip
        CLIP_MIN = cfg["camera"]["clip_min"]
        CLIP_MAX = cfg["camera"]["clip_max"]
        mask_valid = (z_coords > CLIP_MIN) & (z_coords < CLIP_MAX)
        
        if np.count_nonzero(mask_valid) < 100:
            return resultado

        # 3. CÁLCULO DE VOLUMETRIA (Integração)
        # Z_VAZIA é a distância da câmera até o fundo da caçamba (referência)
        Z_VAZIA = cfg["thresholds"]["limite_vazia"]
        ALT_CAIXA = max(cfg["medicoes"]["altura_caixa"], 0.01)
        
        # Diferença de altura em cada ponto (m)
        # h = Z_vazia - Z_atual. Se for negativo (chão?), clipamos em 0.
        alturas = np.maximum(0, Z_VAZIA - z_coords)
        alturas[~mask_valid] = 0
        
        # Estimar a área de cada pixel em metros quadrados.
        # A densidade de pontos no espaço RealSense diminui com o quadrado da distância.
        # Mas como temos X e Y reais, podemos calcular a área média local.
        # Uma aproximação rápida e eficiente para tempo real:
        dx = np.abs(np.diff(x_coords, axis=1))
        dy = np.abs(np.diff(y_coords, axis=0))
        
        # Preencher diffs para manter o shape (H, W)
        dx_avg = np.mean(dx[mask_valid[:, :-1]]) if dx.size > 0 else 0.002
        dy_avg = np.mean(dy[mask_valid[:-1, :]]) if dy.size > 0 else 0.002
        area_pixel_media = dx_avg * dy_avg
        
        # Volume Total do Material (Soma de h * area)
        volume_material = float(np.sum(alturas[mask_valid]) * area_pixel_media)
        
        # Estimativa de Volume Total da Caçamba (Capacidade)
        # Usamos a área total detectada na BB * Altura teórica
        area_base_m2 = np.count_nonzero(mask_valid) * area_pixel_media
        volume_total_capacidade = area_base_m2 * ALT_CAIXA
        
        percentual_vol = (volume_material / volume_total_capacidade * 100) if volume_total_capacidade > 0 else 0
        
        # Distância central (mediana) para compatibilidade V5
        distancia = float(np.median(z_coords[mask_valid]))
        self._hist_dist.append(distancia)
        self._hist_vol.append(volume_material)

        # 4. Determinação de Status por Volume
        # Se preencheu menos de 15% do volume -> VAZIA
        # Se preencheu mais de 85% do volume -> CHEIA
        if percentual_vol < 15.0: status_inst = "VAZIA"
        elif percentual_vol > 85.0: status_inst = "CHEIA"
        else: status_inst = "PARCIAL"

        self._hist_status.append(status_inst)
        if len(self._hist_status) >= 5:
            contagem = {s: list(self._hist_status).count(s) for s in ("VAZIA", "PARCIAL", "CHEIA")}
            status_est = max(contagem, key=contagem.get)
        else:
            status_est = status_inst

        # Confiança baseada na dispersão dos pontos (ruído)
        std_z = float(np.std(z_coords[mask_valid]))
        confianca = max(0.0, min(100.0, 100.0 - std_z * 500))
        self._hist_confianca.append(confianca)

        resultado.status = status_inst
        resultado.status_estavel = status_est
        resultado.distancia = distancia
        resultado.volume_material_m3 = volume_material
        resultado.volume_vazio_m3 = volume_total_capacidade
        resultado.percentual_volumetrico = float(percentual_vol)
        resultado.percentual = float(np.clip((Z_VAZIA - distancia) / ALT_CAIXA * 100, 0, 100))
        resultado.confianca = confianca
        
        return resultado

    def processar_frame(self, depth_meters: np.ndarray) -> ResultadoDeteccao:
        """Fallback 2D se não houver PointCloud."""
        # Mantém a lógica da V5 para compatibilidade, mas sem os novos campos volumétricos
        cfg = self._cfg
        PROF_MIN, PROF_MAX = cfg["medicoes"]["profundidade_min_caixa"], cfg["medicoes"]["profundidade_max_caixa"]
        AREA_MIN = cfg["medicoes"]["area_minima_pixels"]
        KERNEL = cfg["filtros"]["kernel_morph_size"]
        CLIP_MIN, CLIP_MAX = cfg["camera"]["clip_min"], cfg["camera"]["clip_max"]
        GRID = cfg["filtros"]["grid_medicao_size"]

        dh, dw = depth_meters.shape[:2]
        mask = ((depth_meters > PROF_MIN) & (depth_meters < PROF_MAX)).astype(np.uint8) * 255
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (KERNEL, KERNEL))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        melhor_contorno = None
        maior_area = 0.0
        for contour in contours:
            area = cv2.contourArea(contour)
            if area >= AREA_MIN:
                valido, _ = self._validar_deteccao(contour, depth_meters, dw, dh)
                if valido and area > maior_area:
                    maior_area = area
                    melhor_contorno = contour

        resultado = ResultadoDeteccao()
        if melhor_contorno is not None:
            x1, y1, wb, hb = cv2.boundingRect(melhor_contorno)
            resultado.caixa_detectada = True
            resultado.bbox = (x1, y1, x1+wb, y1+hb)
            medicoes = self._medir_grid(depth_meters, x1, y1, x1+wb, y1+hb, GRID, CLIP_MIN, CLIP_MAX)
            if medicoes:
                distancia = float(np.median(medicoes))
                self._hist_dist.append(distancia)
                Z_VAZIA = cfg["thresholds"]["limite_vazia"]
                ALT_CAIXA = max(cfg["medicoes"]["altura_caixa"], 0.001)
                percentual = max(0.0, min(100.0, ((Z_VAZIA - distancia) / ALT_CAIXA) * 100))
                
                if percentual < 20: status_inst = "VAZIA"
                elif percentual > 80: status_inst = "CHEIA"
                else: status_inst = "PARCIAL"
                
                self._hist_status.append(status_inst)
                status_est = max(set(self._hist_status), key=list(self._hist_status).count) if len(self._hist_status) >= 5 else status_inst
                
                resultado.status = status_inst
                resultado.status_estavel = status_est
                resultado.distancia = distancia
                resultado.percentual = percentual
                resultado.confianca = 70.0 # Confiança fixa no modo 2D
        return resultado

    def _validar_deteccao(self, contour, depth_meters, w_frame, h_frame) -> Tuple[bool, str]:
        cfg = self._cfg
        x, y, w, h = cv2.boundingRect(contour)
        aspect = max(w, h) / max(min(w, h), 1)
        if aspect > 5.0: return False, "Aspect ratio"
        cx_norm, cy_norm = (x + w/2) / w_frame, (y + h/2) / h_frame
        roi = cfg["roi"]
        if not (roi["x_min"] < cx_norm < roi["x_max"] and roi["y_min"] < cy_norm < roi["y_max"]):
            return False, "Fora da ROI"
        regiao = depth_meters[y:y+h, x:x+w]
        pixels_validos = regiao[(regiao > 0.05) & (regiao < 5.0)]
        if len(pixels_validos) < 10: return False, "Poucos pixels"
        if float(np.median(pixels_validos)) < cfg["protecao_pessoa"]["profundidade_minima_corpo"]:
            return False, "Muito proximo"
        if cv2.contourArea(contour) > cfg["protecao_pessoa"]["area_maxima_corpo"]:
            return False, "Area muito grande"
        return True, "OK"

    def _medir_grid(self, depth_meters, x1, y1, x2, y2, grid_size, clip_min, clip_max) -> List[float]:
        regiao = depth_meters[y1:y2, x1:x2]
        if regiao.size == 0: return []
        h_r, w_r = regiao.shape
        ch, cw = max(1, h_r // grid_size), max(1, w_r // grid_size)
        meds = []
        for i in range(grid_size):
            for j in range(grid_size):
                cel = regiao[i*ch:(i+1)*ch, j*cw:(j+1)*cw]
                v = cel[(cel > clip_min) & (cel < clip_max)]
                if len(v) > 5: meds.append(float(np.median(v)))
        return meds

    def detectou_mudanca_status(self, status_estavel: str) -> Tuple[bool, Optional[str]]:
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
        self._hist_vol.clear()
        self._hist_confianca.clear()
        self._status_anterior = None
        self._ultima_mudanca = time.time()
