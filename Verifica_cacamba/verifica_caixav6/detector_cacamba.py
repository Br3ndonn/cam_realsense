"""detector_cacamba.py — Lógica de detecção e volumetria 3D (V6).

Mantém a detecção por profundidade da V5 e adiciona um modo 3D com point cloud.
Opcionalmente, pode capturar uma referência de caçamba vazia para calcular o
volume por diferença em relação ao baseline.
"""

import time
from collections import deque
from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import numpy as np


@dataclass
class ResultadoDeteccao:
    status: str = "SEM LEITURA"
    status_estavel: str = "SEM LEITURA"
    distancia: float = 0.0
    percentual: float = 0.0
    percentual_volumetrico: float = 0.0
    volume_material_m3: float = 0.0
    volume_vazio_m3: float = 0.0
    confianca: float = 0.0
    caixa_detectada: bool = False
    material_detectado: bool = False # Flag para qualquer presença de material
    motivo_rejeicao: str = ""
    bbox: Optional[Tuple[int, int, int, int]] = None


class DetectorCacamba:
    """Encapsula a lógica de detecção e cálculo volumétrico 3D."""

    def __init__(self, cfg: dict):
        self._cfg = cfg

        n_hist = cfg["filtros"]["tamanho_historico"]
        n_dist = cfg["filtros"]["historico_distancias"]

        self._hist_status = deque(maxlen=n_hist)
        self._hist_dist = deque(maxlen=n_dist)
        self._hist_vol = deque(maxlen=n_dist)
        self._hist_confianca = deque(maxlen=30)
        self._status_anterior = None
        self._ultima_mudanca = time.time()

        # Baseline 3D da caçamba vazia
        self._reference_z = None
        self._reference_mask = None

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

    def capture_reference(self, depth_meters: np.ndarray, verts_xyz: np.ndarray) -> bool:
        """Captura a caçamba vazia como referência (baseline) para o modo 3D."""
        dh, dw = depth_meters.shape[:2]
        if verts_xyz.shape[0] != dh * dw:
            return False

        resultado = self.processar_frame_3d(depth_meters, verts_xyz)
        if not resultado.caixa_detectada or resultado.bbox is None:
            return False

        x1, y1, x2, y2 = resultado.bbox
        verts_3d = verts_xyz.reshape(dh, dw, 3)
        self._reference_z = verts_3d[y1:y2, x1:x2, 2].copy()
        self._reference_mask = (self._reference_z > 0.05) & (self._reference_z < 5.0)
        return bool(np.any(self._reference_mask))

    def processar_frame_3d(
        self,
        depth_meters: np.ndarray,
        verts_xyz: Optional[np.ndarray] = None,
    ) -> ResultadoDeteccao:
        """Processa o frame com point cloud; cai para 2D se não houver `verts_xyz`."""
        if verts_xyz is None:
            return self.processar_frame(depth_meters)

        cfg = self._cfg
        dh, dw = depth_meters.shape[:2]

        prof_min = cfg["medicoes"]["profundidade_min_caixa"]
        prof_max = cfg["medicoes"]["profundidade_max_caixa"]
        area_min = cfg["medicoes"]["area_minima_pixels"]
        kernel_size = cfg["filtros"]["kernel_morph_size"]

        mask = ((depth_meters > prof_min) & (depth_meters < prof_max)).astype(np.uint8) * 255
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        melhor_contorno = None
        maior_area = 0.0
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < area_min:
                continue
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

        if verts_xyz.shape[0] != dh * dw:
            return self.processar_frame(depth_meters)

        verts_3d = verts_xyz.reshape(dh, dw, 3)
        box_3d = verts_3d[y1 : y1 + hb, x1 : x1 + wb]
        z_coords = box_3d[:, :, 2]
        x_coords = box_3d[:, :, 0]
        y_coords = box_3d[:, :, 1]

        clip_min = cfg["camera"]["clip_min"]
        clip_max = cfg["camera"]["clip_max"]
        mask_valid = (z_coords > clip_min) & (z_coords < clip_max)
        if np.count_nonzero(mask_valid) < 100:
            return resultado

        alt_caixa = max(cfg["medicoes"]["altura_caixa"], 0.01)
        z_vazia = cfg["thresholds"]["limite_vazia"]

        area_pixel_media = self._estimar_area_pixel_media(x_coords, y_coords, mask_valid)

        if self._reference_z is not None and self._reference_mask is not None and self._reference_z.shape == z_coords.shape:
            diff = self._reference_z - z_coords
            alturas = np.where((diff > 0.02) & mask_valid & self._reference_mask, diff, 0.0)
            volume_material = float(np.sum(alturas) * area_pixel_media)
            volume_total_capacidade = float(np.sum(self._reference_mask) * area_pixel_media * alt_caixa)
        else:
            alturas = np.maximum(0.0, z_vazia - z_coords)
            alturas[~mask_valid] = 0.0
            volume_material = float(np.sum(alturas) * area_pixel_media)
            area_base_m2 = float(np.count_nonzero(mask_valid) * area_pixel_media)
            volume_total_capacidade = area_base_m2 * alt_caixa

        percentual_vol = (volume_material / volume_total_capacidade * 100.0) if volume_total_capacidade > 0 else 0.0
        distancia = float(np.median(z_coords[mask_valid]))

        self._hist_dist.append(distancia)
        self._hist_vol.append(volume_material)

        # 4. DETERMINAÇÃO DE STATUS POR VOLUME (ALTA SENSIBILIDADE)
        # Flag imediata: Se temos baseline, > 0.5% de volume já confirma presença física
        resultado.material_detectado = (self._reference_z is not None and percentual_vol > 0.5)

        # Limites lógicos para o status textual
        limite_v = 1.5 if self._reference_z is not None else 15.0 # Muito mais sensível com baseline
        limite_c = 85.0
        
        if percentual_vol < limite_v:
            status_inst = "VAZIA"
        elif percentual_vol > limite_c:
            status_inst = "CHEIA"
        else:
            status_inst = "PARCIAL"

        self._hist_status.append(status_inst)
        if len(self._hist_status) >= 5:
            contagem = {s: list(self._hist_status).count(s) for s in ("VAZIA", "PARCIAL", "CHEIA")}
            status_est = max(contagem, key=contagem.get)
        else:
            status_est = status_inst

        std_z = float(np.std(z_coords[mask_valid]))
        base_conf = 100.0 - (std_z * 400.0)
        if self._reference_z is not None:
            base_conf += 10.0
        confianca = max(0.0, min(100.0, base_conf))
        self._hist_confianca.append(confianca)

        resultado.status = status_inst
        resultado.status_estavel = status_est
        resultado.distancia = distancia
        resultado.volume_material_m3 = volume_material
        resultado.volume_vazio_m3 = float(volume_total_capacidade)
        resultado.percentual_volumetrico = float(percentual_vol)
        resultado.percentual = float(np.clip((z_vazia - distancia) / alt_caixa * 100.0, 0.0, 100.0))
        resultado.confianca = confianca
        return resultado

    def processar_frame(self, depth_meters: np.ndarray) -> ResultadoDeteccao:
        """Fallback 2D se não houver point cloud."""
        cfg = self._cfg
        prof_min = cfg["medicoes"]["profundidade_min_caixa"]
        prof_max = cfg["medicoes"]["profundidade_max_caixa"]
        area_min = cfg["medicoes"]["area_minima_pixels"]
        kernel_size = cfg["filtros"]["kernel_morph_size"]
        clip_min = cfg["camera"]["clip_min"]
        clip_max = cfg["camera"]["clip_max"]
        grid = cfg["filtros"]["grid_medicao_size"]

        dh, dw = depth_meters.shape[:2]
        mask = ((depth_meters > prof_min) & (depth_meters < prof_max)).astype(np.uint8) * 255
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        melhor_contorno = None
        maior_area = 0.0
        for contour in contours:
            area = cv2.contourArea(contour)
            if area >= area_min:
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

        medicoes = self._medir_grid(depth_meters, x1, y1, x1 + wb, y1 + hb, grid, clip_min, clip_max)
        if not medicoes:
            return resultado

        distancia = float(np.median(medicoes))
        z_vazia = cfg["thresholds"]["limite_vazia"]
        alt_caixa = max(cfg["medicoes"]["altura_caixa"], 0.001)
        percentual = max(0.0, min(100.0, ((z_vazia - distancia) / alt_caixa) * 100.0))

        if percentual < 20.0:
            status_inst = "VAZIA"
        elif percentual > 80.0:
            status_inst = "CHEIA"
        else:
            status_inst = "PARCIAL"

        self._hist_dist.append(distancia)
        self._hist_status.append(status_inst)

        if len(self._hist_status) >= 5:
            contagem = {s: list(self._hist_status).count(s) for s in ("VAZIA", "PARCIAL", "CHEIA")}
            status_est = max(contagem, key=contagem.get)
        else:
            status_est = status_inst

        resultado.status = status_inst
        resultado.status_estavel = status_est
        resultado.distancia = distancia
        resultado.percentual = percentual
        resultado.confianca = 70.0
        return resultado

    def _validar_deteccao(self, contour, depth_meters, w_frame, h_frame) -> Tuple[bool, str]:
        cfg = self._cfg
        x, y, w, h = cv2.boundingRect(contour)
        aspect = max(w, h) / max(min(w, h), 1)
        if aspect > 5.0:
            return False, "Aspect ratio"

        cx_norm = (x + w / 2) / w_frame
        cy_norm = (y + h / 2) / h_frame
        roi = cfg["roi"]
        if not (roi["x_min"] < cx_norm < roi["x_max"] and roi["y_min"] < cy_norm < roi["y_max"]):
            return False, "Fora da ROI"

        regiao = depth_meters[y : y + h, x : x + w]
        pixels_validos = regiao[(regiao > 0.05) & (regiao < 5.0)]
        if len(pixels_validos) < 10:
            return False, "Poucos pixels"
        if float(np.median(pixels_validos)) < cfg["protecao_pessoa"]["profundidade_minima_corpo"]:
            return False, "Muito proximo"
        if cv2.contourArea(contour) > cfg["protecao_pessoa"]["area_maxima_corpo"]:
            return False, "Area muito grande"
        return True, "OK"

    def _medir_grid(self, depth_meters, x1, y1, x2, y2, grid_size, clip_min, clip_max) -> List[float]:
        regiao = depth_meters[y1:y2, x1:x2]
        if regiao.size == 0:
            return []

        h_r, w_r = regiao.shape
        ch, cw = max(1, h_r // grid_size), max(1, w_r // grid_size)
        meds = []
        for i in range(grid_size):
            for j in range(grid_size):
                cel = regiao[i * ch : (i + 1) * ch, j * cw : (j + 1) * cw]
                valores = cel[(cel > clip_min) & (cel < clip_max)]
                if len(valores) > 5:
                    meds.append(float(np.median(valores)))
        return meds

    def _estimar_area_pixel_media(self, x_coords: np.ndarray, y_coords: np.ndarray, mask_valid: np.ndarray) -> float:
        dx = np.abs(np.diff(x_coords, axis=1))
        dy = np.abs(np.diff(y_coords, axis=0))

        dx_valid = dx[mask_valid[:, :-1]] if dx.size > 0 else np.array([], dtype=np.float32)
        dy_valid = dy[mask_valid[:-1, :]] if dy.size > 0 else np.array([], dtype=np.float32)

        dx_avg = float(np.mean(dx_valid)) if dx_valid.size > 0 else 0.002
        dy_avg = float(np.mean(dy_valid)) if dy_valid.size > 0 else 0.002
        area_pixel_media = dx_avg * dy_avg
        return float(area_pixel_media if area_pixel_media > 0 else 1e-6)

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
