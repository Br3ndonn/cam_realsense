"""
gui_app.py — Interface gráfica V5

Correções em relação à V4:
  - queue.Queue para comunicação entre threads (sem variáveis compartilhadas sem lock)
  - Config lida do dicionário self.cm.cfg, nunca de widgets Tkinter dentro da thread da câmera
  - validar_deteccao() reintroduzida em detector_cacamba.py
  - Confiança média calculada com deque real (corrigido)
  - GUI atualizada via poll_queue() a ~15 FPS (sem root.after(0,...) a cada frame)

Novas funcionalidades:
  - Alertas sonoros via winsound ao mudar status
  - Exportar histórico para CSV (pasta historico/)
  - Multi-view: color + depth colormap lado a lado
  - Perfis de configuração nomeados
  - Modo simulação sem câmera física
  - Wizard de calibração em 3 passos
"""

import copy
import csv
import queue
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np
import tkinter as tk
from tkinter import messagebox, scrolledtext, simpledialog, ttk
from PIL import Image, ImageTk

try:
    import winsound
    _HAS_WINSOUND = True
except ImportError:
    _HAS_WINSOUND = False

try:
    import pyrealsense2 as rs
    _HAS_REALSENSE = True
except ImportError:
    _HAS_REALSENSE = False

from config_manager import ConfigManager
from detector_cacamba import DetectorCacamba, ResultadoDeteccao

# ── UI constants ──────────────────────────────────────────────────────────────
CORES_STATUS = {
    "VAZIA":       "#f44336",
    "PARCIAL":     "#FF9800",
    "CHEIA":       "#4CAF50",
    "SEM LEITURA": "#808080",
    "AGUARDANDO":  "#808080",
}
CORES_BGR = {
    "VAZIA":   (0, 0, 255),
    "PARCIAL": (0, 165, 255),
    "CHEIA":   (0, 255, 0),
}

VIDEO_W, VIDEO_H = 480, 360   # tamanho de display de cada painel de vídeo
GUI_POLL_MS      = 66          # ~15 FPS de atualização da GUI
HIST_MAX         = 10_000      # máximo de registros no histórico para CSV


class DetectorCacambaGUIV5:
    """Interface gráfica V5 — comunicação via queue.Queue, thread-safe."""

    def __init__(self, root: tk.Tk, config_manager: ConfigManager, simulate: bool = False):
        self.root = root
        self.cm = config_manager
        self.simulate = simulate

        self.root.title(f"Sistema de Detecção V5{'  [SIMULAÇÃO]' if simulate else ''}")
        self.root.geometry("1620x960")
        self.root.configure(bg="#2b2b2b")

        # ── Comunicação entre threads ──────────────────────────────────────
        # A thread da câmera coloca msgs aqui; a GUI consome via poll_queue()
        self.data_queue: queue.Queue = queue.Queue(maxsize=3)
        # A GUI envia comandos para a thread da câmera (ex: atualizar config)
        self.cmd_queue: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()
        self._thread_camera: Optional[threading.Thread] = None

        # Snapshot de config para a thread da câmera.
        # Atualizado APENAS pela GUI thread com o lock.
        self._cfg_lock = threading.Lock()
        self._cfg_snapshot: dict = copy.deepcopy(self.cm.cfg)

        # ── Estado (modificado APENAS pela GUI thread via poll_queue) ──────
        self._camera_ativa = False
        self._ultimo_resultado = ResultadoDeteccao()
        self._ultimo_fps = 0.0
        self._hist_dist: deque = deque(maxlen=150)
        self._hist_completo: deque = deque(maxlen=HIST_MAX)
        self._log_mudancas: list = []
        self._contador_frames = 0
        self._tempo_inicio: Optional[float] = None
        self._hist_fps: deque = deque(maxlen=30)
        self._multi_view = True

        # ── Construir interface ────────────────────────────────────────────
        self._criar_interface()

        # Iniciar polling da queue
        self.root.after(GUI_POLL_MS, self._poll_queue)

        self.root.protocol("WM_DELETE_WINDOW", self.fechar_aplicacao)

    # =========================================================================
    # CRIAÇÃO DA INTERFACE
    # =========================================================================

    def _criar_interface(self):
        self._criar_painel_controles()

        main = tk.Frame(self.root, bg="#2b2b2b")
        main.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # Coluna esquerda: vídeos + status
        left = tk.Frame(main, bg="#2b2b2b")
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._criar_painel_videos(left)
        self._criar_painel_status(left)

        # Coluna direita: abas
        right = tk.Frame(main, bg="#2b2b2b", width=570)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, padx=4)
        right.pack_propagate(False)
        nb = ttk.Notebook(right)
        nb.pack(fill=tk.BOTH, expand=True)
        self._criar_aba_config(nb)
        self._criar_aba_logs(nb)
        self._criar_aba_historico(nb)
        self._criar_aba_stats(nb)

        # Barra de status inferior
        self._barra_status = tk.Label(
            self.root,
            text="💡 Sistema pronto. Clique em INICIAR CÂMERA para começar.",
            font=("Arial", 9), bg="#1e1e1e", fg="white", anchor=tk.W, padx=10,
        )
        self._barra_status.pack(fill=tk.X, side=tk.BOTTOM)

        modo = "SIMULAÇÃO" if self.simulate else "CÂMERA REAL"
        self._adicionar_log(f"Sistema V5 iniciado. Modo: {modo}")
        if not _HAS_REALSENSE and not self.simulate:
            self._adicionar_log("⚠️  pyrealsense2 não encontrado — use --simulate.")

    # ── Painel de controles (topo) ────────────────────────────────────────────

    def _criar_painel_controles(self):
        top = tk.Frame(self.root, bg="#1e1e1e", pady=6)
        top.pack(fill=tk.X, padx=8, pady=(6, 0))

        # Título
        title_row = tk.Frame(top, bg="#1e1e1e")
        title_row.pack()
        tk.Label(
            title_row, text="🎯 SISTEMA DE DETECÇÃO DE NÍVEL DA CACAMBA V5",
            font=("Arial", 15, "bold"), bg="#1e1e1e", fg="#4CAF50",
        ).pack(side=tk.LEFT)
        if self.simulate:
            tk.Label(
                title_row, text="  [MODO SIMULAÇÃO]",
                font=("Arial", 11, "bold"), bg="#1e1e1e", fg="#FF9800",
            ).pack(side=tk.LEFT)

        # Botões principais
        btn_row = tk.Frame(top, bg="#1e1e1e")
        btn_row.pack(pady=6)

        def _btn(parent, text, cmd, color, w=16):
            return tk.Button(
                parent, text=text, command=cmd,
                font=("Arial", 10, "bold"), bg=color, fg="white",
                width=w, relief=tk.RAISED, cursor="hand2",
            )

        self._btn_toggle = _btn(btn_row, "▶ INICIAR CÂMERA", self._toggle_camera, "#4CAF50", 20)
        self._btn_toggle.grid(row=0, column=0, padx=4)
        _btn(btn_row, "💾 SALVAR CONFIG",    self._salvar_configuracoes, "#2196F3").grid(row=0, column=1, padx=4)
        _btn(btn_row, "📥 EXPORTAR CSV",     self._exportar_csv,          "#607D8B").grid(row=0, column=2, padx=4)
        _btn(btn_row, "📷 TOGGLE VIEW",      self._toggle_view,           "#795548").grid(row=0, column=3, padx=4)
        _btn(btn_row, "🔧 WIZARD CALIB.",    self._abrir_wizard,          "#009688").grid(row=0, column=4, padx=4)
        _btn(btn_row, "🔄 RESETAR STATS",    self._resetar_estatisticas,  "#FF9800").grid(row=0, column=5, padx=4)
        _btn(btn_row, "❓ AJUDA",            self._mostrar_ajuda,         "#9C27B0").grid(row=0, column=6, padx=4)

        # Linha de perfis
        perf_row = tk.Frame(top, bg="#1e1e1e")
        perf_row.pack(pady=(0, 4))

        tk.Label(perf_row, text="Perfil:", font=("Arial", 9), bg="#1e1e1e", fg="white").pack(side=tk.LEFT, padx=4)
        self._var_perfil = tk.StringVar()
        self._combo_perfis = ttk.Combobox(perf_row, textvariable=self._var_perfil, width=22, state="readonly")
        self._combo_perfis.pack(side=tk.LEFT, padx=4)

        def _small_btn(txt, cmd, color):
            tk.Button(perf_row, text=txt, command=cmd, font=("Arial", 9),
                      bg=color, fg="white", cursor="hand2").pack(side=tk.LEFT, padx=2)

        _small_btn("📂 Carregar",      self._carregar_perfil, "#455A64")
        _small_btn("💾 Salvar Perfil", self._salvar_perfil,   "#37474F")
        _small_btn("🗑 Deletar",       self._deletar_perfil,  "#B71C1C")

        self._atualizar_dropdown_perfis()

    # ── Painel de vídeos ──────────────────────────────────────────────────────

    def _criar_painel_videos(self, parent):
        vf = tk.Frame(parent, bg="#2b2b2b")
        vf.pack(fill=tk.X, padx=4, pady=4)

        p1 = tk.LabelFrame(vf, text="📹 Color", font=("Arial", 9, "bold"),
                            bg="#1e1e1e", fg="#4CAF50")
        p1.pack(side=tk.LEFT, padx=4)
        self._lbl_video1 = tk.Label(p1, bg="black", width=VIDEO_W, height=VIDEO_H)
        self._lbl_video1.pack(padx=3, pady=3)

        self._frame_video2 = tk.LabelFrame(vf, text="🌈 Depth Colormap",
                                            font=("Arial", 9, "bold"), bg="#1e1e1e", fg="#4CAF50")
        self._frame_video2.pack(side=tk.LEFT, padx=4)
        self._lbl_video2 = tk.Label(self._frame_video2, bg="black", width=VIDEO_W, height=VIDEO_H)
        self._lbl_video2.pack(padx=3, pady=3)

    # ── Painel de status ──────────────────────────────────────────────────────

    def _criar_painel_status(self, parent):
        sf = tk.LabelFrame(parent, text="📊 Status Atual", font=("Arial", 10, "bold"),
                           bg="#1e1e1e", fg="white", pady=4)
        sf.pack(fill=tk.X, padx=4, pady=4)

        inner = tk.Frame(sf, bg="#1e1e1e")
        inner.pack(padx=8, pady=4)

        self._lbl_status = tk.Label(
            inner, text="AGUARDANDO", font=("Arial", 22, "bold"),
            bg="#1e1e1e", fg="#808080", width=16,
        )
        self._lbl_status.grid(row=0, column=0, columnspan=8, pady=6)

        def _metric(row, col, label):
            tk.Label(inner, text=label, font=("Arial", 9), bg="#1e1e1e", fg="#aaaaaa"
                     ).grid(row=row, column=col * 2, sticky=tk.W, padx=5)
            lbl = tk.Label(inner, text="—", font=("Arial", 10, "bold"), bg="#1e1e1e", fg="#4CAF50")
            lbl.grid(row=row, column=col * 2 + 1, sticky=tk.W, padx=5)
            return lbl

        self._lbl_distancia  = _metric(1, 0, "Distância:")
        self._lbl_percentual = _metric(1, 1, "Percentual:")
        self._lbl_confianca  = _metric(1, 2, "Confiança:")
        self._lbl_fps        = _metric(1, 3, "FPS:")

        self._progress = ttk.Progressbar(inner, length=520, mode="determinate", maximum=100)
        self._progress.grid(row=2, column=0, columnspan=8, pady=6)

    # ── Aba Configurações ─────────────────────────────────────────────────────

    def _criar_aba_config(self, nb):
        frame = tk.Frame(nb, bg="#1e1e1e")
        nb.add(frame, text="⚙️ Configurações")

        canvas = tk.Canvas(frame, bg="#1e1e1e", highlightthickness=0)
        sb = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scrollable = tk.Frame(canvas, bg="#1e1e1e")
        scrollable.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self._cfg_widgets: dict = {}
        self._var_beep = tk.BooleanVar(value=self.cm.cfg["sons"]["beep_mudanca_status"])
        self._criar_campos_config(scrollable)

    def _criar_campos_config(self, parent):
        row = 0
        cfg = self.cm.cfg

        def _secao(txt):
            nonlocal row
            tk.Label(parent, text=txt, font=("Arial", 10, "bold"),
                     bg="#1e1e1e", fg="#4CAF50").grid(
                row=row, column=0, columnspan=2, sticky=tk.W, padx=6, pady=(10, 3))
            row += 1

        def _campo(label, chave, valor):
            nonlocal row
            tk.Label(parent, text=label, font=("Arial", 9),
                     bg="#1e1e1e", fg="white").grid(row=row, column=0, sticky=tk.W, padx=6, pady=2)
            e = tk.Entry(parent, width=16)
            e.insert(0, str(valor))
            e.grid(row=row, column=1, padx=6, pady=2)
            self._cfg_widgets[chave] = e
            row += 1

        _secao("📏 MEDIÇÕES")
        _campo("Altura câmera (m):",   "altura_camera_chao",     cfg["medicoes"]["altura_camera_chao"])
        _campo("Altura cacamba (m):",  "altura_caixa",           cfg["medicoes"]["altura_caixa"])
        _campo("Prof. min caixa (m):", "profundidade_min_caixa", cfg["medicoes"]["profundidade_min_caixa"])
        _campo("Prof. max caixa (m):", "profundidade_max_caixa", cfg["medicoes"]["profundidade_max_caixa"])
        _campo("Área mínima (px²):",   "area_minima_pixels",     cfg["medicoes"]["area_minima_pixels"])

        _secao("🎯 THRESHOLDS")
        _campo("Limite VAZIA (m):",    "limite_vazia",  cfg["thresholds"]["limite_vazia"])
        _campo("Limite CHEIA (m):",    "limite_cheia",  cfg["thresholds"]["limite_cheia"])

        _secao("🛡️ PROTEÇÃO PESSOA")
        _campo("Prof. mín corpo (m):",   "profundidade_minima_corpo",    cfg["protecao_pessoa"]["profundidade_minima_corpo"])
        _campo("Área máx corpo (px²):",  "area_maxima_corpo",            cfg["protecao_pessoa"]["area_maxima_corpo"])
        _campo("Tempo mín mudança (s):", "tempo_minimo_entre_mudancas",  cfg["protecao_pessoa"]["tempo_minimo_entre_mudancas"])

        _secao("🎛️ FILTROS")
        _campo("Tamanho histórico:",   "tamanho_historico",    cfg["filtros"]["tamanho_historico"])
        _campo("Histórico dist.:",     "historico_distancias", cfg["filtros"]["historico_distancias"])
        _campo("Kernel morfológico:",  "kernel_morph_size",    cfg["filtros"]["kernel_morph_size"])

        _secao("🔊 SONS")
        tk.Checkbutton(
            parent, text="Beep ao mudar status", variable=self._var_beep,
            bg="#1e1e1e", fg="white", selectcolor="#333",
            activebackground="#1e1e1e", activeforeground="white",
        ).grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=6, pady=4)
        row += 1
        _campo("Frequência (Hz):", "beep_frequencia", cfg["sons"]["beep_frequencia"])
        _campo("Duração (ms):",    "beep_duracao",    cfg["sons"]["beep_duracao"])

        tk.Button(
            parent, text="✅ Aplicar Configurações", command=self._aplicar_configuracoes,
            bg="#4CAF50", fg="white", font=("Arial", 10, "bold"), cursor="hand2",
        ).grid(row=row, column=0, columnspan=2, pady=14)

    # ── Aba Logs ──────────────────────────────────────────────────────────────

    def _criar_aba_logs(self, nb):
        frame = tk.Frame(nb, bg="#1e1e1e")
        nb.add(frame, text="📋 Logs")
        self._text_logs = scrolledtext.ScrolledText(
            frame, font=("Courier", 9), bg="#0d0d0d", fg="#00ff00", wrap=tk.WORD, height=30,
        )
        self._text_logs.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        tk.Button(frame, text="🗑️ Limpar Logs", command=self._limpar_logs,
                  bg="#f44336", fg="white", cursor="hand2").pack(pady=4)

    # ── Aba Histórico ─────────────────────────────────────────────────────────

    def _criar_aba_historico(self, nb):
        frame = tk.Frame(nb, bg="#1e1e1e")
        nb.add(frame, text="📈 Histórico")

        self._canvas_grafico = tk.Canvas(frame, bg="#0d0d0d", height=260)
        self._canvas_grafico.pack(fill=tk.X, padx=4, pady=4)

        tk.Label(frame, text="Mudanças de Status:", font=("Arial", 9, "bold"),
                 bg="#1e1e1e", fg="white").pack(pady=(4, 0))

        lb_frame = tk.Frame(frame, bg="#1e1e1e")
        lb_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        sb = ttk.Scrollbar(lb_frame)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._listbox_mudancas = tk.Listbox(
            lb_frame, font=("Courier", 9), bg="#0d0d0d", fg="white", yscrollcommand=sb.set,
        )
        self._listbox_mudancas.pack(fill=tk.BOTH, expand=True)
        sb.config(command=self._listbox_mudancas.yview)

    # ── Aba Estatísticas ──────────────────────────────────────────────────────

    def _criar_aba_stats(self, nb):
        frame = tk.Frame(nb, bg="#1e1e1e")
        nb.add(frame, text="📊 Estatísticas")

        inner = tk.Frame(frame, bg="#1e1e1e")
        inner.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        self._stats_labels: dict = {}

        items = [
            ("Tempo Total:",        "tempo_total"),
            ("Frames Processados:", "frames_total"),
            ("FPS Médio:",          "fps_medio"),
            ("Tempo em VAZIA:",     "tempo_vazia"),
            ("Tempo em PARCIAL:",   "tempo_parcial"),
            ("Tempo em CHEIA:",     "tempo_cheia"),
            ("Mudanças Totais:",    "mudancas_total"),
            ("Confiança Média:",    "confianca_media"),
            ("Distância Atual:",    "distancia_atual"),
        ]
        for i, (lbl, key) in enumerate(items):
            tk.Label(inner, text=lbl, font=("Arial", 10), bg="#1e1e1e", fg="white"
                     ).grid(row=i, column=0, sticky=tk.W, padx=4, pady=5)
            v = tk.Label(inner, text="—", font=("Arial", 10, "bold"), bg="#1e1e1e", fg="#4CAF50")
            v.grid(row=i, column=1, sticky=tk.W, padx=4, pady=5)
            self._stats_labels[key] = v

    # =========================================================================
    # CONTROLE DA CÂMERA / SIMULAÇÃO
    # =========================================================================

    def _toggle_camera(self):
        if not self._camera_ativa:
            self._iniciar_camera()
        else:
            self._parar_camera()

    def _iniciar_camera(self):
        if self._camera_ativa:
            return
        if not self.simulate and not _HAS_REALSENSE:
            messagebox.showerror("Erro", "pyrealsense2 não encontrado.\nUse --simulate ou instale o SDK RealSense.")
            return

        self._stop_event.clear()
        # Limpar fila antiga
        while not self.data_queue.empty():
            try:
                self.data_queue.get_nowait()
            except queue.Empty:
                break

        # Snapshot de config para a thread
        with self._cfg_lock:
            self._cfg_snapshot = copy.deepcopy(self.cm.cfg)

        target = self._loop_simulacao if self.simulate else self._loop_camera
        self._thread_camera = threading.Thread(target=target, daemon=True)
        self._thread_camera.start()

        self._camera_ativa = True
        self._tempo_inicio = time.time()
        self._btn_toggle.config(text="⏸ PARAR CÂMERA", bg="#f44336")
        self._barra_status.config(text=f"✅ {'Simulação' if self.simulate else 'Câmera'} ativa — detectando...")
        self._adicionar_log(f"🚀 {'Simulação' if self.simulate else 'Câmera RealSense'} iniciada.")

    def _parar_camera(self):
        self._stop_event.set()
        if self._thread_camera:
            self._thread_camera.join(timeout=3.0)
        self._camera_ativa = False
        self._btn_toggle.config(text="▶ INICIAR CÂMERA", bg="#4CAF50")
        self._barra_status.config(text="💤 Câmera parada.")
        self._adicionar_log("✅ Câmera parada.")

    # =========================================================================
    # THREADS
    # =========================================================================

    def _loop_camera(self):
        """Thread da câmera RealSense — nunca acessa widgets Tkinter."""
        with self._cfg_lock:
            cfg = copy.deepcopy(self._cfg_snapshot)

        detector = DetectorCacamba(cfg)
        pipeline = rs.pipeline()
        rs_cfg = rs.config()

        W = cfg["camera"]["resolucao_largura"]
        H = cfg["camera"]["resolucao_altura"]
        FPS = cfg["camera"]["fps"]
        rs_cfg.enable_stream(rs.stream.depth, W, H, rs.format.z16, FPS)
        rs_cfg.enable_stream(rs.stream.infrared, 1, W, H, rs.format.y8, FPS)
        rs_cfg.enable_stream(rs.stream.color, W, H, rs.format.bgr8, FPS)

        try:
            profile = pipeline.start(rs_cfg)
            device = profile.get_device()
            depth_sensor = device.first_depth_sensor()
            depth_scale = depth_sensor.get_depth_scale()

            if depth_sensor.supports(rs.option.emitter_enabled):
                depth_sensor.set_option(rs.option.emitter_enabled, 1.0)
                if depth_sensor.supports(rs.option.laser_power):
                    lp = cfg["camera"]["laser_potencia"]
                    if lp > 0:
                        depth_sensor.set_option(rs.option.laser_power, float(lp))

            # Filtros de profundidade
            decimation = rs.decimation_filter()
            spatial = rs.spatial_filter()
            spatial.set_option(rs.option.filter_magnitude, 2)
            spatial.set_option(rs.option.filter_smooth_alpha, 0.5)
            spatial.set_option(rs.option.filter_smooth_delta, 20)
            temporal = rs.temporal_filter()
            temporal.set_option(rs.option.filter_smooth_alpha, 0.4)
            temporal.set_option(rs.option.filter_smooth_delta, 20)
            hole_filling = rs.hole_filling_filter()

            self._enqueue_log("✅ RealSense conectada e configurada.")

            t_prev_frame = time.time()  # para medir FPS inter-frame real
            while not self._stop_event.is_set():
                # Processar comandos da GUI (ex: update_config)
                self._processar_cmd_queue(detector)

                frames = pipeline.wait_for_frames(timeout_ms=1000)
                depth_raw = frames.get_depth_frame()
                color_frame = frames.get_color_frame()
                ir_frame = frames.get_infrared_frame(1)

                if not depth_raw:
                    continue

                # FPS medido como frequência real entre frames (inclui wait da câmera)
                t_now = time.time()
                fps = 1.0 / max(t_now - t_prev_frame, 1e-6)
                t_prev_frame = t_now

                filtered = decimation.process(depth_raw)
                filtered = spatial.process(filtered)
                filtered = temporal.process(filtered)
                filtered = hole_filling.process(filtered)

                depth_image = np.asanyarray(filtered.get_data())
                depth_meters = depth_image * depth_scale

                if color_frame:
                    frame_bgr = np.asanyarray(color_frame.get_data())
                    dh, dw = depth_meters.shape[:2]
                    if frame_bgr.shape[:2] != (dh, dw):
                        frame_bgr = cv2.resize(frame_bgr, (dw, dh))
                else:
                    ir_img = np.asanyarray(ir_frame.get_data())
                    frame_bgr = cv2.cvtColor(ir_img, cv2.COLOR_GRAY2BGR)

                ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                self._processar_e_enfileirar(frame_bgr, depth_meters, fps, ts, detector, cfg)

        except Exception as e:
            self._enqueue_log(f"❌ Erro câmera: {e}")
            try:
                self.data_queue.put_nowait({"tipo": "erro", "mensagem": str(e)})
            except queue.Full:
                pass
        finally:
            try:
                pipeline.stop()
            except Exception:
                pass
            self._enqueue_camera_parada()

    def _loop_simulacao(self):
        """Thread de simulação — gera frames sintéticos sem câmera física."""
        with self._cfg_lock:
            cfg = copy.deepcopy(self._cfg_snapshot)

        detector = DetectorCacamba(cfg)
        t_start = time.time()
        self._enqueue_log("🎮 Modo simulação ativo — câmera virtual rodando.")

        while not self._stop_event.is_set():
            self._processar_cmd_queue(detector)

            t = time.time() - t_start
            t0 = time.time()

            frame_bgr, depth_meters = self._gerar_frame_simulado(t, cfg)
            fps = 30.0
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            self._processar_e_enfileirar(frame_bgr, depth_meters, fps, ts, detector, cfg)

            # Simular ~30 FPS
            elapsed = time.time() - t0
            time.sleep(max(0.0, (1.0 / 30) - elapsed))

        self._enqueue_camera_parada()

    def _gerar_frame_simulado(self, t: float, cfg: dict) -> Tuple[np.ndarray, np.ndarray]:
        """Gera frame de depth + frame colorido sintéticos."""
        h, w = 480, 640
        LIMITE_VAZIA = cfg["thresholds"]["limite_vazia"]
        LIMITE_CHEIA = cfg["thresholds"]["limite_cheia"]
        mid = (LIMITE_VAZIA + LIMITE_CHEIA) / 2
        amp = (LIMITE_VAZIA - LIMITE_CHEIA) / 2
        target_depth = mid + amp * np.sin(t * 0.25)

        # Depth frame — zero no background, target_depth na região da caixa
        depth = np.zeros((h, w), dtype=np.float32)
        bx1, by1 = int(w * 0.30), int(h * 0.28)
        bx2, by2 = int(w * 0.70), int(h * 0.75)
        noise = np.random.normal(0, 0.004, (by2 - by1, bx2 - bx1)).astype(np.float32)
        depth[by1:by2, bx1:bx2] = np.clip(target_depth + noise, 0.1, 2.0)

        # Color frame
        frame_bgr = np.full((h, w, 3), 25, dtype=np.uint8)
        pct = (LIMITE_VAZIA - target_depth) / max(LIMITE_VAZIA - LIMITE_CHEIA, 0.001)
        pct = max(0.0, min(1.0, pct))
        fill_y = by2 - int((by2 - by1) * pct)
        cv2.rectangle(frame_bgr, (bx1, by1), (bx2, by2), (60, 60, 60), -1)
        cv2.rectangle(frame_bgr, (bx1, fill_y), (bx2, by2), (40, 120, 40), -1)
        cv2.rectangle(frame_bgr, (bx1, by1), (bx2, by2), (180, 180, 180), 2)
        cv2.putText(frame_bgr, f"SIMULACAO  t={t:.1f}s  {pct * 100:.0f}%",
                    (10, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 220, 220), 2)
        return frame_bgr, depth

    # ── Processamento de frame (compartilhado entre câmera e simulação) ───────

    def _processar_cmd_queue(self, detector: DetectorCacamba):
        """Drena o cmd_queue e aplica comandos na thread da câmera."""
        try:
            while True:
                cmd = self.cmd_queue.get_nowait()
                if cmd.get("tipo") == "update_config":
                    detector.atualizar_config(cmd["cfg"])
        except queue.Empty:
            pass

    def _processar_e_enfileirar(
        self,
        frame_bgr: np.ndarray,
        depth_meters: np.ndarray,
        fps: float,
        ts: str,
        detector: DetectorCacamba,
        cfg: dict,
    ):
        """Detecta, desenha overlays e coloca resultado na data_queue."""
        # Detecção leve sempre ocorre (atualiza históricos)
        resultado = detector.processar_frame(depth_meters)
        mudou, status_anterior = detector.detectou_mudanca_status(resultado.status_estavel)

        # Se a fila já está cheia, descartar ANTES de fazer qualquer trabalho pesado
        if self.data_queue.full():
            return

        frame_rgb = cv2.cvtColor(
            self._desenhar_overlays_color(frame_bgr.copy(), resultado, cfg),
            cv2.COLOR_BGR2RGB,
        )
        # Só processa depth colormap se o painel estiver visível (leitura de bool é thread-safe no CPython)
        frame_depth_rgb: Optional[np.ndarray] = (
            cv2.cvtColor(
                self._desenhar_depth_colormap(depth_meters, resultado, cfg),
                cv2.COLOR_BGR2RGB,
            )
            if self._multi_view
            else None
        )

        msg: dict = {
            "tipo": "frame",
            "frame_color": frame_rgb,
            "frame_depth": frame_depth_rgb,
            "resultado": resultado,
            "fps": fps,
            "timestamp": ts,
        }
        if mudou:
            msg["mudanca"] = {"de": status_anterior, "para": resultado.status_estavel, "ts": ts}

        try:
            self.data_queue.put_nowait(msg)
        except queue.Full:
            pass  # descarta frame se GUI ainda não consumiu

    # ── Desenho de overlays ───────────────────────────────────────────────────

    def _desenhar_overlays_color(
        self, frame_bgr: np.ndarray, resultado: ResultadoDeteccao, cfg: dict
    ) -> np.ndarray:
        h, w = frame_bgr.shape[:2]
        cor = CORES_BGR.get(resultado.status_estavel, (128, 128, 128))

        # Header com status
        cv2.rectangle(frame_bgr, (0, 0), (w, 70), (20, 20, 20), -1)
        cv2.putText(frame_bgr, f"STATUS: {resultado.status_estavel}",
                    (8, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, cor, 2)
        cv2.putText(
            frame_bgr,
            f"Dist:{resultado.distancia:.3f}m  {resultado.percentual:.0f}%  Conf:{resultado.confianca:.0f}%",
            (8, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (210, 210, 210), 1,
        )

        # Bounding box e grid
        if resultado.bbox:
            x1, y1, x2, y2 = resultado.bbox
            cv2.rectangle(frame_bgr, (x1, y1), (x2, y2), (0, 255, 255), 2)
            g = cfg["filtros"]["grid_medicao_size"]
            for gi in range(1, g):
                gx = x1 + gi * (x2 - x1) // g
                gy = y1 + gi * (y2 - y1) // g
                cv2.line(frame_bgr, (gx, y1), (gx, y2), (0, 200, 200), 1)
                cv2.line(frame_bgr, (x1, gy), (x2, gy), (0, 200, 200), 1)
        else:
            cx, cy = w // 2, h // 2
            cv2.line(frame_bgr, (cx - 25, cy), (cx + 25, cy), (200, 200, 200), 2)
            cv2.line(frame_bgr, (cx, cy - 25), (cx, cy + 25), (200, 200, 200), 2)

        # ROI
        roi = cfg["roi"]
        cv2.rectangle(
            frame_bgr,
            (int(roi["x_min"] * w), int(roi["y_min"] * h)),
            (int(roi["x_max"] * w), int(roi["y_max"] * h)),
            (80, 80, 220), 1,
        )
        return frame_bgr

    def _desenhar_depth_colormap(
        self, depth_meters: np.ndarray, resultado: ResultadoDeteccao, cfg: dict
    ) -> np.ndarray:
        clip_min = cfg["camera"]["clip_min"]
        clip_max = cfg["camera"]["clip_max"]
        depth_clip = np.clip(depth_meters, clip_min, clip_max)
        depth_norm = (255 - ((depth_clip - clip_min) / (clip_max - clip_min) * 255)).astype(np.uint8)
        colormap = cfg["visualizacao"].get("colormap", 2)
        depth_color = cv2.applyColorMap(depth_norm, colormap)

        h, w = depth_color.shape[:2]
        if resultado.bbox:
            x1, y1, x2, y2 = resultado.bbox
            # Escalar bbox se depth foi redimensionado
            dh_orig, dw_orig = depth_meters.shape[:2]
            sx, sy = w / dw_orig, h / dh_orig
            cv2.rectangle(depth_color,
                          (int(x1 * sx), int(y1 * sy)),
                          (int(x2 * sx), int(y2 * sy)),
                          (255, 255, 255), 2)

        roi = cfg["roi"]
        cv2.rectangle(
            depth_color,
            (int(roi["x_min"] * w), int(roi["y_min"] * h)),
            (int(roi["x_max"] * w), int(roi["y_max"] * h)),
            (180, 180, 180), 1,
        )
        cv2.putText(depth_color, f"DEPTH  {resultado.distancia:.3f}m",
                    (8, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
        return depth_color

    # =========================================================================
    # QUEUE POLLING (GUI thread — ~15 FPS)
    # =========================================================================

    def _poll_queue(self):
        """Consome mensagens da data_queue e atualiza a GUI.

        Mensagens leves (log, erro, controle) são drenadas todas.
        Mensagens de frame são limitadas a 1 por tick para não travar a GUI
        com múltiplos resize+canvas em sequência dentro do mesmo ciclo.
        """
        try:
            while True:
                msg = self.data_queue.get_nowait()
                self._processar_mensagem(msg)
                # Frame pesado (resize + canvas): processar só 1 por tick
                if msg.get("tipo") == "frame":
                    break
        except queue.Empty:
            pass
        finally:
            self.root.after(GUI_POLL_MS, self._poll_queue)

    def _processar_mensagem(self, msg: dict):
        tipo = msg.get("tipo")

        if tipo == "frame":
            resultado: ResultadoDeteccao = msg["resultado"]
            fps = msg["fps"]
            ts = msg["timestamp"]

            self._ultimo_resultado = resultado
            self._ultimo_fps = fps
            self._contador_frames += 1
            self._hist_fps.append(fps)
            self._hist_dist.append(resultado.distancia)

            record = {
                "timestamp": ts,
                "status": resultado.status_estavel,
                "distancia_m": round(resultado.distancia, 4),
                "percentual": round(resultado.percentual, 1),
                "confianca": round(resultado.confianca, 1),
                "fps": round(fps, 1),
            }
            self._hist_completo.append(record)

            self._atualizar_videos(msg["frame_color"], msg["frame_depth"])
            self._atualizar_status_panel(resultado, fps)
            self._desenhar_grafico()
            self._atualizar_stats()

            if "mudanca" in msg:
                m = msg["mudanca"]
                self._registrar_mudanca_status(m["de"], m["para"], m["ts"])

        elif tipo == "log":
            self._adicionar_log(msg["mensagem"])

        elif tipo == "erro":
            self._adicionar_log(f"❌ {msg['mensagem']}")
            self._barra_status.config(text=f"❌ Erro: {msg['mensagem'][:90]}")

        elif tipo == "camera_parada":
            if self._camera_ativa:
                self._camera_ativa = False
                self._btn_toggle.config(text="▶ INICIAR CÂMERA", bg="#4CAF50")
                self._barra_status.config(text="💤 Câmera parada.")

    # ── Helpers para a thread da câmera enfileirar mensagens ─────────────────

    def _enqueue_log(self, msg: str):
        try:
            self.data_queue.put_nowait({"tipo": "log", "mensagem": msg})
        except queue.Full:
            pass

    def _enqueue_camera_parada(self):
        try:
            self.data_queue.put_nowait({"tipo": "camera_parada"})
        except queue.Full:
            pass

    # =========================================================================
    # ATUALIZAÇÕES DA GUI
    # =========================================================================

    def _atualizar_videos(self, frame_color_rgb: np.ndarray, frame_depth_rgb: Optional[np.ndarray]):
        def _show(label, arr):
            # BILINEAR é ~4x mais rápido que LANCZOS sem perda perceptível em vídeo ao vivo
            img = Image.fromarray(arr).resize((VIDEO_W, VIDEO_H), Image.Resampling.BILINEAR)
            img_tk = ImageTk.PhotoImage(image=img)
            label.config(image=img_tk)
            label.image = img_tk  # manter referência

        _show(self._lbl_video1, frame_color_rgb)
        if self._multi_view and frame_depth_rgb is not None:
            _show(self._lbl_video2, frame_depth_rgb)

    def _atualizar_status_panel(self, resultado: ResultadoDeteccao, fps: float):
        cor = CORES_STATUS.get(resultado.status_estavel, "#808080")
        self._lbl_status.config(text=resultado.status_estavel, fg=cor)
        self._lbl_distancia.config(text=f"{resultado.distancia:.3f} m")
        self._lbl_percentual.config(text=f"{resultado.percentual:.0f}%")
        self._lbl_confianca.config(text=f"{resultado.confianca:.0f}%")
        self._lbl_fps.config(text=f"{fps:.1f}")
        self._progress["value"] = resultado.percentual

    def _desenhar_grafico(self):
        c = self._canvas_grafico
        c.delete("all")
        dados = list(self._hist_dist)
        if len(dados) < 2:
            return

        cw = c.winfo_width() or 540
        ch = c.winfo_height() or 260
        mx, my = 42, 20
        gw, gh = cw - 2 * mx, ch - 2 * my

        # Eixos
        c.create_line(mx, ch - my, cw - mx, ch - my, fill="white", width=1)
        c.create_line(mx, my, mx, ch - my, fill="white", width=1)

        mn_v, mx_v = min(dados), max(dados)
        rng = max(mx_v - mn_v, 0.01)

        def _to_y(v):
            return ch - my - ((v - mn_v) / rng) * gh

        # Labels Y
        for val in (mn_v, (mn_v + mx_v) / 2, mx_v):
            yy = _to_y(val)
            c.create_text(mx - 4, yy, text=f"{val:.2f}", fill="#888", anchor="e", font=("Arial", 7))

        # Linhas de threshold
        cfg = self.cm.cfg
        lv = cfg["thresholds"]["limite_vazia"]
        lc = cfg["thresholds"]["limite_cheia"]
        if mn_v <= lv <= mx_v:
            yv = _to_y(lv)
            c.create_line(mx, yv, cw - mx, yv, fill="#f44336", dash=(5, 5))
            c.create_text(mx - 2, yv - 8, text="VAZIA", fill="#f44336", anchor="e", font=("Arial", 7))
        if mn_v <= lc <= mx_v:
            yc = _to_y(lc)
            c.create_line(mx, yc, cw - mx, yc, fill="#4CAF50", dash=(5, 5))
            c.create_text(mx - 2, yc - 8, text="CHEIA", fill="#4CAF50", anchor="e", font=("Arial", 7))

        # Linha de dados — única chamada create_line com todos os pontos (N-1x mais rápido)
        n = len(dados)
        pts = [
            (mx + (i / (n - 1)) * gw, _to_y(v))
            for i, v in enumerate(dados)
        ]
        flat_pts = [coord for pt in pts for coord in pt]
        c.create_line(*flat_pts, fill="#00ff00", width=2)

        c.create_text(cw // 2, ch - 5, text="Tempo →", fill="#666", font=("Arial", 8))

    def _atualizar_stats(self):
        sl = self._stats_labels
        if self._tempo_inicio:
            sl["tempo_total"].config(text=f"{time.time() - self._tempo_inicio:.0f}s")
        sl["frames_total"].config(text=str(self._contador_frames))
        fps_med = float(np.mean(self._hist_fps)) if self._hist_fps else 0.0
        sl["fps_medio"].config(text=f"{fps_med:.1f}")

        recentes = list(self._hist_completo)[-500:] if self._hist_completo else []
        statuses = [r["status"] for r in recentes]
        sl["tempo_vazia"].config(text=str(statuses.count("VAZIA")))
        sl["tempo_parcial"].config(text=str(statuses.count("PARCIAL")))
        sl["tempo_cheia"].config(text=str(statuses.count("CHEIA")))
        sl["mudancas_total"].config(text=str(len(self._log_mudancas)))

        confs = [r["confianca"] for r in recentes if r["confianca"] > 0]
        if confs:
            sl["confianca_media"].config(text=f"{np.mean(confs):.1f}%")
        sl["distancia_atual"].config(text=f"{self._ultimo_resultado.distancia:.3f}m")

    # =========================================================================
    # CONFIGURAÇÕES
    # =========================================================================

    def _aplicar_configuracoes(self):
        try:
            w = self._cfg_widgets
            cfg = self.cm.cfg
            cfg["medicoes"]["altura_camera_chao"]              = float(w["altura_camera_chao"].get())
            cfg["medicoes"]["altura_caixa"]                    = float(w["altura_caixa"].get())
            cfg["medicoes"]["profundidade_min_caixa"]          = float(w["profundidade_min_caixa"].get())
            cfg["medicoes"]["profundidade_max_caixa"]          = float(w["profundidade_max_caixa"].get())
            cfg["medicoes"]["area_minima_pixels"]              = int(w["area_minima_pixels"].get())
            cfg["thresholds"]["limite_vazia"]                  = float(w["limite_vazia"].get())
            cfg["thresholds"]["limite_cheia"]                  = float(w["limite_cheia"].get())
            cfg["protecao_pessoa"]["profundidade_minima_corpo"]     = float(w["profundidade_minima_corpo"].get())
            cfg["protecao_pessoa"]["area_maxima_corpo"]             = int(w["area_maxima_corpo"].get())
            cfg["protecao_pessoa"]["tempo_minimo_entre_mudancas"]   = float(w["tempo_minimo_entre_mudancas"].get())
            cfg["filtros"]["tamanho_historico"]                = int(w["tamanho_historico"].get())
            cfg["filtros"]["historico_distancias"]             = int(w["historico_distancias"].get())
            cfg["filtros"]["kernel_morph_size"]                = int(w["kernel_morph_size"].get())
            cfg["sons"]["beep_mudanca_status"]                 = self._var_beep.get()
            cfg["sons"]["beep_frequencia"]                     = int(w["beep_frequencia"].get())
            cfg["sons"]["beep_duracao"]                        = int(w["beep_duracao"].get())

            # Enviar update para thread da câmera via cmd_queue (sem acessar widgets de outra thread)
            if self._camera_ativa:
                try:
                    self.cmd_queue.put_nowait({"tipo": "update_config", "cfg": copy.deepcopy(cfg)})
                except queue.Full:
                    pass

            self._adicionar_log("✅ Configurações aplicadas.")
            messagebox.showinfo("Sucesso", "Configurações aplicadas!")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao aplicar configurações:\n{e}")

    def _salvar_configuracoes(self):
        self._aplicar_configuracoes()
        try:
            self.cm.salvar()
            self._adicionar_log(f"💾 Config salva: {self.cm.caminho}")
            messagebox.showinfo("Sucesso", f"Config salva em:\n{self.cm.caminho}")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao salvar:\n{e}")

    def _preencher_campos_config(self):
        """Atualiza os widgets de config com os valores atuais do cm.cfg."""
        cfg = self.cm.cfg
        w = self._cfg_widgets

        def _set(key, val):
            if key in w:
                w[key].delete(0, tk.END)
                w[key].insert(0, str(val))

        _set("altura_camera_chao",          cfg["medicoes"]["altura_camera_chao"])
        _set("altura_caixa",                cfg["medicoes"]["altura_caixa"])
        _set("profundidade_min_caixa",      cfg["medicoes"]["profundidade_min_caixa"])
        _set("profundidade_max_caixa",      cfg["medicoes"]["profundidade_max_caixa"])
        _set("area_minima_pixels",          cfg["medicoes"]["area_minima_pixels"])
        _set("limite_vazia",                cfg["thresholds"]["limite_vazia"])
        _set("limite_cheia",                cfg["thresholds"]["limite_cheia"])
        _set("profundidade_minima_corpo",   cfg["protecao_pessoa"]["profundidade_minima_corpo"])
        _set("area_maxima_corpo",           cfg["protecao_pessoa"]["area_maxima_corpo"])
        _set("tempo_minimo_entre_mudancas", cfg["protecao_pessoa"]["tempo_minimo_entre_mudancas"])
        _set("tamanho_historico",           cfg["filtros"]["tamanho_historico"])
        _set("historico_distancias",        cfg["filtros"]["historico_distancias"])
        _set("kernel_morph_size",           cfg["filtros"]["kernel_morph_size"])
        _set("beep_frequencia",             cfg["sons"]["beep_frequencia"])
        _set("beep_duracao",                cfg["sons"]["beep_duracao"])
        self._var_beep.set(cfg["sons"]["beep_mudanca_status"])

    # =========================================================================
    # PERFIS
    # =========================================================================

    def _atualizar_dropdown_perfis(self):
        perfis = self.cm.listar_perfis()
        self._combo_perfis["values"] = perfis
        if perfis and not self._var_perfil.get():
            self._var_perfil.set(perfis[0])

    def _carregar_perfil(self):
        nome = self._var_perfil.get()
        if not nome:
            messagebox.showwarning("Aviso", "Selecione um perfil primeiro.")
            return
        if self.cm.carregar_perfil(nome):
            self._preencher_campos_config()
            if self._camera_ativa:
                try:
                    self.cmd_queue.put_nowait({"tipo": "update_config", "cfg": copy.deepcopy(self.cm.cfg)})
                except queue.Full:
                    pass
            self._adicionar_log(f"📂 Perfil '{nome}' carregado.")
            messagebox.showinfo("Sucesso", f"Perfil '{nome}' carregado!")
        else:
            messagebox.showerror("Erro", f"Perfil '{nome}' não encontrado.")

    def _salvar_perfil(self):
        nome = simpledialog.askstring("Salvar Perfil", "Nome do perfil:", parent=self.root)
        if not nome or not nome.strip():
            return
        nome = nome.strip()
        self._aplicar_configuracoes()
        self.cm.salvar_perfil(nome)
        self._atualizar_dropdown_perfis()
        self._var_perfil.set(nome)
        self._adicionar_log(f"💾 Perfil '{nome}' salvo.")
        messagebox.showinfo("Sucesso", f"Perfil '{nome}' salvo!")

    def _deletar_perfil(self):
        nome = self._var_perfil.get()
        if not nome:
            messagebox.showwarning("Aviso", "Selecione um perfil primeiro.")
            return
        if messagebox.askyesno("Confirmar", f"Deletar perfil '{nome}'?"):
            self.cm.deletar_perfil(nome)
            self._atualizar_dropdown_perfis()
            self._var_perfil.set("")
            self._adicionar_log(f"🗑 Perfil '{nome}' deletado.")

    # =========================================================================
    # FUNCIONALIDADES
    # =========================================================================

    def _exportar_csv(self):
        if not self._hist_completo:
            messagebox.showwarning("Aviso", "Nenhum dado para exportar.")
            return
        try:
            pasta = Path(__file__).parent / "historico"
            pasta.mkdir(exist_ok=True)
            nome = pasta / f"historico_{datetime.now():%Y%m%d_%H%M%S}.csv"
            campos = ["timestamp", "status", "distancia_m", "percentual", "confianca", "fps"]
            with open(nome, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=campos)
                writer.writeheader()
                writer.writerows(self._hist_completo)
            self._adicionar_log(f"📥 CSV exportado: {nome.name} ({len(self._hist_completo)} registros)")
            messagebox.showinfo("Exportado", f"Arquivo salvo em:\n{nome}")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao exportar CSV:\n{e}")

    def _emitir_beep(self, status: str):
        if not _HAS_WINSOUND:
            return
        cfg = self.cm.cfg
        if not cfg["sons"]["beep_mudanca_status"]:
            return
        freq_base = int(cfg["sons"]["beep_frequencia"])
        dur = int(cfg["sons"]["beep_duracao"])
        freqs = {"VAZIA": freq_base, "PARCIAL": int(freq_base * 1.25), "CHEIA": int(freq_base * 0.8)}
        freq = freqs.get(status, freq_base)
        threading.Thread(target=lambda: winsound.Beep(freq, dur), daemon=True).start()

    def _registrar_mudanca_status(self, de: Optional[str], para: str, ts: str):
        entrada = f"{ts}  {de or 'N/A'} → {para}"
        self._log_mudancas.append(entrada)
        self._listbox_mudancas.insert(0, entrada)
        self._adicionar_log(f"🔔 Mudança de status: {de or 'N/A'} → {para}")
        self._emitir_beep(para)

    def _toggle_view(self):
        self._multi_view = not self._multi_view
        if self._multi_view:
            self._frame_video2.pack(side=tk.LEFT, padx=4)
            self._adicionar_log("📷 Multi-view ativado (Color + Depth).")
        else:
            self._frame_video2.pack_forget()
            self._adicionar_log("📷 Single-view ativado (somente Color).")

    # ── Wizard de calibração ──────────────────────────────────────────────────

    def _abrir_wizard(self):
        if not self._camera_ativa:
            messagebox.showwarning("Wizard", "Inicie a câmera antes de usar o wizard.")
            return
        WizardCalibracao(self.root, self)

    # ── Logs ──────────────────────────────────────────────────────────────────

    def _adicionar_log(self, mensagem: str):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._text_logs.insert(tk.END, f"[{ts}] {mensagem}\n")
        self._text_logs.see(tk.END)

    def _limpar_logs(self):
        self._text_logs.delete(1.0, tk.END)
        self._adicionar_log("Logs limpos.")

    def _resetar_estatisticas(self):
        self._contador_frames = 0
        self._tempo_inicio = time.time()
        self._hist_dist.clear()
        self._hist_fps.clear()
        self._hist_completo.clear()
        self._log_mudancas.clear()
        self._listbox_mudancas.delete(0, tk.END)
        self._adicionar_log("🔄 Estatísticas resetadas.")
        messagebox.showinfo("Resetado", "Estatísticas resetadas!")

    def _mostrar_ajuda(self):
        messagebox.showinfo("Ajuda — V5", """
SISTEMA DE DETECÇÃO DE NÍVEL DA CACAMBA V5
==========================================

COMO USAR:
1. Ajuste as configurações na aba "Configurações"
2. Clique em "INICIAR CÂMERA" para começar
3. O sistema detecta o nível automaticamente
4. Use "SALVAR CONFIG" para persistir as configurações

MODOS:
• Câmera Real: requer hardware RealSense conectado
• Simulação: use --simulate para testar sem câmera

WIZARD DE CALIBRAÇÃO:
Com a câmera ativa, o wizard guia em 3 passos:
  1. Mede a altura da câmera ao chão
  2. Mede o limite da cacamba vazia
  3. Mede o limite da cacamba cheia

PERFIS:
Salve conjuntos de configurações com nomes
para reutilizar em diferentes cenários.

EXPORTAR CSV:
Grava o histórico de medições em historico/

TOGGLE VIEW:
Alterna entre exibir color + depth ou só color.

Versão: 5.0
""")

    def fechar_aplicacao(self):
        if self._camera_ativa:
            self._parar_camera()
        self.root.quit()
        self.root.destroy()


# =============================================================================
# WIZARD DE CALIBRAÇÃO
# =============================================================================

class WizardCalibracao(tk.Toplevel):
    """Janela modal de calibração em 3 passos."""

    PASSOS = [
        (
            "Passo 1 de 3 — Altura da Câmera",
            "Certifique-se de que o campo de visão está LIVRE (sem a cacamba).\n"
            "A câmera deve estar apontada para o chão ou superfície de referência.\n\n"
            "Quando a leitura estiver estável, clique em 'Capturar'.",
            "altura_camera_chao",
        ),
        (
            "Passo 2 de 3 — Cacamba VAZIA",
            "Posicione a cacamba VAZIA no campo de visão da câmera.\n"
            "Aguarde a leitura estabilizar e clique em 'Capturar'.",
            "limite_vazia",
        ),
        (
            "Passo 3 de 3 — Cacamba CHEIA",
            "Encha completamente a cacamba.\n"
            "Aguarde a leitura estabilizar e clique em 'Capturar'.",
            "limite_cheia",
        ),
    ]

    def __init__(self, parent: tk.Tk, app: DetectorCacambaGUIV5):
        super().__init__(parent)
        self.app = app
        self.passo_atual = 0
        self.capturas: dict = {}

        self.title("🔧 Wizard de Calibração")
        self.geometry("480x320")
        self.configure(bg="#2b2b2b")
        self.resizable(False, False)
        self.grab_set()  # modal
        self.transient(parent)

        # Título do passo
        self._lbl_titulo = tk.Label(self, font=("Arial", 12, "bold"),
                                     bg="#2b2b2b", fg="#4CAF50")
        self._lbl_titulo.pack(pady=(14, 4), padx=16)

        # Instrução
        self._lbl_instrucao = tk.Label(self, wraplength=440, justify=tk.LEFT,
                                        font=("Arial", 10), bg="#2b2b2b", fg="white")
        self._lbl_instrucao.pack(pady=8, padx=16)

        # Leitura atual
        frame_leit = tk.Frame(self, bg="#1e1e1e", pady=8)
        frame_leit.pack(fill=tk.X, padx=16, pady=4)
        tk.Label(frame_leit, text="Leitura atual:", font=("Arial", 10),
                 bg="#1e1e1e", fg="#aaaaaa").pack(side=tk.LEFT, padx=8)
        self._lbl_leitura = tk.Label(frame_leit, text="—", font=("Arial", 14, "bold"),
                                      bg="#1e1e1e", fg="#4CAF50")
        self._lbl_leitura.pack(side=tk.LEFT, padx=8)

        # Botões
        btn_frame = tk.Frame(self, bg="#2b2b2b")
        btn_frame.pack(pady=14)
        self._btn_capturar = tk.Button(btn_frame, text="📸 Capturar", command=self._capturar,
                                        font=("Arial", 11, "bold"), bg="#4CAF50", fg="white",
                                        width=14, cursor="hand2")
        self._btn_capturar.grid(row=0, column=0, padx=8)
        tk.Button(btn_frame, text="❌ Cancelar", command=self.destroy,
                  font=("Arial", 11), bg="#f44336", fg="white", width=10,
                  cursor="hand2").grid(row=0, column=1, padx=8)

        self._atualizar_passo()
        self._atualizar_leitura()

    def _atualizar_passo(self):
        titulo, instrucao, _ = self.PASSOS[self.passo_atual]
        self._lbl_titulo.config(text=titulo)
        self._lbl_instrucao.config(text=instrucao)

    def _atualizar_leitura(self):
        if not self.winfo_exists():
            return
        dist = self.app._ultimo_resultado.distancia
        conf = self.app._ultimo_resultado.confianca
        self._lbl_leitura.config(text=f"{dist:.4f} m  (confiança: {conf:.0f}%)")
        self.after(200, self._atualizar_leitura)

    def _capturar(self):
        dist = self.app._ultimo_resultado.distancia
        if dist <= 0:
            messagebox.showwarning("Aviso", "Sem leitura válida. Aguarde a câmera estabilizar.",
                                   parent=self)
            return

        _, _, chave = self.PASSOS[self.passo_atual]
        self.capturas[chave] = dist

        self.passo_atual += 1
        if self.passo_atual < len(self.PASSOS):
            self._atualizar_passo()
        else:
            self._finalizar()

    def _finalizar(self):
        """Aplica os valores capturados à configuração."""
        cfg = self.app.cm.cfg
        w = self.app._cfg_widgets

        if "altura_camera_chao" in self.capturas:
            v = self.capturas["altura_camera_chao"]
            cfg["medicoes"]["altura_camera_chao"] = v
            if "altura_camera_chao" in w:
                w["altura_camera_chao"].delete(0, tk.END)
                w["altura_camera_chao"].insert(0, str(round(v, 4)))

        if "limite_vazia" in self.capturas:
            v = self.capturas["limite_vazia"]
            cfg["thresholds"]["limite_vazia"] = v
            if "limite_vazia" in w:
                w["limite_vazia"].delete(0, tk.END)
                w["limite_vazia"].insert(0, str(round(v, 4)))

        if "limite_cheia" in self.capturas:
            v = self.capturas["limite_cheia"]
            cfg["thresholds"]["limite_cheia"] = v
            if "limite_cheia" in w:
                w["limite_cheia"].delete(0, tk.END)
                w["limite_cheia"].insert(0, str(round(v, 4)))

            # Calcular altura da cacamba automaticamente
            if "limite_vazia" in self.capturas:
                altura_caixa = round(self.capturas["limite_vazia"] - v, 4)
                if altura_caixa > 0:
                    cfg["medicoes"]["altura_caixa"] = altura_caixa
                    if "altura_caixa" in w:
                        w["altura_caixa"].delete(0, tk.END)
                        w["altura_caixa"].insert(0, str(altura_caixa))

        resumo = "\n".join(f"  {k}: {v:.4f} m" for k, v in self.capturas.items())
        messagebox.showinfo(
            "Calibração Concluída",
            f"Valores capturados e aplicados:\n{resumo}\n\n"
            "Clique em 'Salvar Config' para persistir.",
            parent=self,
        )
        self.app._adicionar_log("🔧 Wizard de calibração concluído.")
        self.destroy()
