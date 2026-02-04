"""
Sistema de Detecção de Nível da Cacamba - Versão 4 com GUI
=========================================================

NOVA FUNCIONALIDADE V4:
- Interface gráfica completa com Tkinter
- Controles para ajustar parâmetros em tempo real
- Visualização de estatísticas em painéis dedicados
- Botões para salvar configurações
- Histórico de mudanças de status
- Gráfico de profundidade em tempo real
- Controles de câmera (ligar/desligar)
- Sistema de logs integrado
"""

import pyrealsense2 as rs
import numpy as np
import cv2
from collections import deque
import time
import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from PIL import Image, ImageTk
import threading
from datetime import datetime


def carregar_configuracoes(caminho_config="config.json"):
    """
    Carrega configurações do arquivo JSON.
    Se o arquivo não existir, usa valores padrão.
    """
    caminho = Path(__file__).parent / caminho_config

    # Valores padrão caso o arquivo não exista
    config_padrao = {
        "camera": {
            "resolucao_largura": 640,
            "resolucao_altura": 480,
            "fps": 30,
            "clip_min": 0.1,
            "clip_max": 2.0,
            "laser_potencia": 360
        },
        "medicoes": {
            "altura_camera_chao": 0.725,
            "altura_caixa": 0.20,
            "profundidade_min_caixa": 0.45,
            "profundidade_max_caixa": 0.85,
            "area_minima_pixels": 5000
        },
        "protecao_pessoa": {
            "profundidade_minima_corpo": 0.20,
            "area_maxima_corpo": 200000,
            "velocidade_max_mudanca": 0.05,
            "tempo_minimo_entre_mudancas": 1.0
        },
        "roi": {
            "x_min": 0.25,
            "x_max": 0.75,
            "y_min": 0.25,
            "y_max": 0.85
        },
        "thresholds": {
            "limite_vazia": 0.70,
            "limite_cheia": 0.55,
            "threshold_binary": 127
        },
        "filtros": {
            "tamanho_historico": 10,
            "historico_distancias": 30,
            "kernel_morph_size": 5,
            "grid_medicao_size": 3
        },
        "visualizacao": {
            "mostrar_fps": True,
            "mostrar_grid": True,
            "mostrar_ir": True,
            "colormap": 2
        },
        "sons": {
            "beep_mudanca_status": True,
            "beep_frequencia": 1000,
            "beep_duracao": 200
        }
    }

    try:
        if caminho.exists():
            with open(caminho, 'r', encoding='utf-8') as f:
                config = json.load(f)
            return config
        else:
            # Criar arquivo de configuração padrão
            with open(caminho, 'w', encoding='utf-8') as f:
                json.dump(config_padrao, f, indent=2, ensure_ascii=False)
            return config_padrao
    except Exception as e:
        print(f"❌ Erro ao carregar configurações: {e}")
        return config_padrao


class DetectorCacambaGUI:
    """Interface gráfica para o sistema de detecção da cacamba"""

    def __init__(self, root):
        self.root = root
        self.root.title("Sistema de Detecção de Nível da Cacamba V4")
        self.root.geometry("1400x900")
        self.root.configure(bg="#2b2b2b")

        # Carregar configurações
        self.cfg = carregar_configuracoes()

        # Estados
        self.camera_ativa = False
        self.pipeline = None
        self.thread_camera = None
        self.parar_camera = False

        # Dados em tempo real
        self.frame_atual = None
        self.depth_frame_atual = None
        self.ir_frame_atual = None
        self.status_atual = "AGUARDANDO"
        self.distancia_atual = 0.0
        self.confianca_atual = 0.0
        self.fps_atual = 0.0
        self.percentual_cheio = 0.0

        # Históricos
        self.historico_status = deque(maxlen=50)
        self.historico_distancias = deque(maxlen=100)
        self.historico_fps = deque(maxlen=30)
        self.log_mudancas = []

        # Estatísticas
        self.contador_frames = 0
        self.tempo_inicio = None

        # Criar interface
        self.criar_interface()

        # Protocolo de fechamento
        self.root.protocol("WM_DELETE_WINDOW", self.fechar_aplicacao)

    def criar_interface(self):
        """Cria todos os componentes da interface gráfica"""

        # ==== PAINEL SUPERIOR - CONTROLES ====
        painel_controles = tk.Frame(self.root, bg="#1e1e1e", pady=10)
        painel_controles.pack(fill=tk.X, padx=10, pady=5)

        # Título
        titulo = tk.Label(
            painel_controles,
            text="🎯 SISTEMA DE DETECÇÃO DE NÍVEL DA CACAMBA V4",
            font=("Arial", 16, "bold"),
            bg="#1e1e1e",
            fg="#4CAF50"
        )
        titulo.pack()

        # Frame de botões
        frame_botoes = tk.Frame(painel_controles, bg="#1e1e1e")
        frame_botoes.pack(pady=10)

        # Botão Iniciar/Parar
        self.btn_toggle_camera = tk.Button(
            frame_botoes,
            text="▶ INICIAR CÂMERA",
            command=self.toggle_camera,
            font=("Arial", 12, "bold"),
            bg="#4CAF50",
            fg="white",
            width=20,
            height=2,
            relief=tk.RAISED,
            cursor="hand2"
        )
        self.btn_toggle_camera.grid(row=0, column=0, padx=5)

        # Botão Salvar Configurações
        btn_salvar = tk.Button(
            frame_botoes,
            text="💾 SALVAR CONFIG",
            command=self.salvar_configuracoes,
            font=("Arial", 12),
            bg="#2196F3",
            fg="white",
            width=18,
            relief=tk.RAISED,
            cursor="hand2"
        )
        btn_salvar.grid(row=0, column=1, padx=5)

        # Botão Resetar Estatísticas
        btn_reset = tk.Button(
            frame_botoes,
            text="🔄 RESETAR STATS",
            command=self.resetar_estatisticas,
            font=("Arial", 12),
            bg="#FF9800",
            fg="white",
            width=18,
            relief=tk.RAISED,
            cursor="hand2"
        )
        btn_reset.grid(row=0, column=2, padx=5)

        # Botão Ajuda
        btn_ajuda = tk.Button(
            frame_botoes,
            text="❓ AJUDA",
            command=self.mostrar_ajuda,
            font=("Arial", 12),
            bg="#9C27B0",
            fg="white",
            width=18,
            relief=tk.RAISED,
            cursor="hand2"
        )
        btn_ajuda.grid(row=0, column=3, padx=5)

        # ==== PAINEL CENTRAL - VÍDEOS E STATUS ====
        painel_central = tk.Frame(self.root, bg="#2b2b2b")
        painel_central.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Coluna esquerda - Vídeo principal e status
        coluna_esquerda = tk.Frame(painel_central, bg="#2b2b2b")
        coluna_esquerda.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Frame de vídeo principal
        frame_video = tk.LabelFrame(
            coluna_esquerda,
            text="📹 Visualização Principal",
            font=("Arial", 10, "bold"),
            bg="#1e1e1e",
            fg="white",
            pady=5
        )
        frame_video.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.label_video = tk.Label(frame_video, bg="black")
        self.label_video.pack(padx=5, pady=5)

        # Frame de status
        frame_status = tk.LabelFrame(
            coluna_esquerda,
            text="📊 Status Atual",
            font=("Arial", 10, "bold"),
            bg="#1e1e1e",
            fg="white",
            pady=5
        )
        frame_status.pack(fill=tk.X, padx=5, pady=5)

        # Grid de status
        grid_status = tk.Frame(frame_status, bg="#1e1e1e")
        grid_status.pack(pady=5, padx=10)

        # Status da cacamba (grande)
        self.label_status = tk.Label(
            grid_status,
            text="AGUARDANDO",
            font=("Arial", 24, "bold"),
            bg="#1e1e1e",
            fg="#808080",
            width=15
        )
        self.label_status.grid(row=0, column=0, columnspan=2, pady=10)

        # Distância
        tk.Label(
            grid_status,
            text="Distância:",
            font=("Arial", 10),
            bg="#1e1e1e",
            fg="white"
        ).grid(row=1, column=0, sticky=tk.W, padx=5)

        self.label_distancia = tk.Label(
            grid_status,
            text="0.000 m",
            font=("Arial", 10, "bold"),
            bg="#1e1e1e",
            fg="#4CAF50"
        )
        self.label_distancia.grid(row=1, column=1, sticky=tk.W, padx=5)

        # Percentual
        tk.Label(
            grid_status,
            text="Percentual:",
            font=("Arial", 10),
            bg="#1e1e1e",
            fg="white"
        ).grid(row=2, column=0, sticky=tk.W, padx=5)

        self.label_percentual = tk.Label(
            grid_status,
            text="0%",
            font=("Arial", 10, "bold"),
            bg="#1e1e1e",
            fg="#4CAF50"
        )
        self.label_percentual.grid(row=2, column=1, sticky=tk.W, padx=5)

        # Confiança
        tk.Label(
            grid_status,
            text="Confiança:",
            font=("Arial", 10),
            bg="#1e1e1e",
            fg="white"
        ).grid(row=3, column=0, sticky=tk.W, padx=5)

        self.label_confianca = tk.Label(
            grid_status,
            text="0%",
            font=("Arial", 10, "bold"),
            bg="#1e1e1e",
            fg="#4CAF50"
        )
        self.label_confianca.grid(row=3, column=1, sticky=tk.W, padx=5)

        # FPS
        tk.Label(
            grid_status,
            text="FPS:",
            font=("Arial", 10),
            bg="#1e1e1e",
            fg="white"
        ).grid(row=4, column=0, sticky=tk.W, padx=5)

        self.label_fps = tk.Label(
            grid_status,
            text="0.0",
            font=("Arial", 10, "bold"),
            bg="#1e1e1e",
            fg="#4CAF50"
        )
        self.label_fps.grid(row=4, column=1, sticky=tk.W, padx=5)

        # Barra de progresso (percentual)
        self.progress_percentual = ttk.Progressbar(
            grid_status,
            length=300,
            mode='determinate',
            maximum=100
        )
        self.progress_percentual.grid(row=5, column=0, columnspan=2, pady=10)

        # Coluna direita - Configurações e logs
        coluna_direita = tk.Frame(painel_central, bg="#2b2b2b", width=400)
        coluna_direita.pack(side=tk.RIGHT, fill=tk.BOTH, padx=5)
        coluna_direita.pack_propagate(False)

        # Notebook para abas
        notebook = ttk.Notebook(coluna_direita)
        notebook.pack(fill=tk.BOTH, expand=True, pady=5)

        # ==== ABA 1 - CONFIGURAÇÕES ====
        aba_config = tk.Frame(notebook, bg="#1e1e1e")
        notebook.add(aba_config, text="⚙️ Configurações")

        # Scrollable frame para configurações
        canvas_config = tk.Canvas(aba_config, bg="#1e1e1e", highlightthickness=0)
        scrollbar_config = ttk.Scrollbar(aba_config, orient="vertical", command=canvas_config.yview)
        frame_scrollable = tk.Frame(canvas_config, bg="#1e1e1e")

        frame_scrollable.bind(
            "<Configure>",
            lambda e: canvas_config.configure(scrollregion=canvas_config.bbox("all"))
        )

        canvas_config.create_window((0, 0), window=frame_scrollable, anchor="nw")
        canvas_config.configure(yscrollcommand=scrollbar_config.set)

        canvas_config.pack(side="left", fill="both", expand=True)
        scrollbar_config.pack(side="right", fill="y")

        # Dicionário para armazenar widgets de configuração
        self.config_widgets = {}

        # Criar campos de configuração
        self.criar_campos_configuracao(frame_scrollable)

        # ==== ABA 2 - LOGS ====
        aba_logs = tk.Frame(notebook, bg="#1e1e1e")
        notebook.add(aba_logs, text="📋 Logs")

        # Área de texto para logs
        self.text_logs = scrolledtext.ScrolledText(
            aba_logs,
            font=("Courier", 9),
            bg="#0d0d0d",
            fg="#00ff00",
            wrap=tk.WORD,
            height=30
        )
        self.text_logs.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Botão limpar logs
        btn_limpar_logs = tk.Button(
            aba_logs,
            text="🗑️ Limpar Logs",
            command=self.limpar_logs,
            bg="#f44336",
            fg="white",
            cursor="hand2"
        )
        btn_limpar_logs.pack(pady=5)

        # ==== ABA 3 - HISTÓRICO ====
        aba_historico = tk.Frame(notebook, bg="#1e1e1e")
        notebook.add(aba_historico, text="📈 Histórico")

        # Canvas para gráfico
        self.canvas_grafico = tk.Canvas(
            aba_historico,
            bg="#0d0d0d",
            width=350,
            height=300
        )
        self.canvas_grafico.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Lista de mudanças de status
        tk.Label(
            aba_historico,
            text="Mudanças de Status:",
            font=("Arial", 10, "bold"),
            bg="#1e1e1e",
            fg="white"
        ).pack(pady=5)

        self.listbox_mudancas = tk.Listbox(
            aba_historico,
            font=("Courier", 9),
            bg="#0d0d0d",
            fg="white",
            height=10
        )
        self.listbox_mudancas.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # ==== ABA 4 - ESTATÍSTICAS ====
        aba_stats = tk.Frame(notebook, bg="#1e1e1e")
        notebook.add(aba_stats, text="📊 Estatísticas")

        # Frame de estatísticas
        frame_stats = tk.Frame(aba_stats, bg="#1e1e1e")
        frame_stats.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Criar labels de estatísticas
        self.stats_labels = {}

        stats_info = [
            ("Tempo Total:", "tempo_total"),
            ("Frames Processados:", "frames_total"),
            ("FPS Médio:", "fps_medio"),
            ("Tempo em VAZIA:", "tempo_vazia"),
            ("Tempo em PARCIAL:", "tempo_parcial"),
            ("Tempo em CHEIA:", "tempo_cheia"),
            ("Mudanças Totais:", "mudancas_total"),
            ("Confiança Média:", "confianca_media"),
        ]

        for i, (label_text, key) in enumerate(stats_info):
            tk.Label(
                frame_stats,
                text=label_text,
                font=("Arial", 10),
                bg="#1e1e1e",
                fg="white"
            ).grid(row=i, column=0, sticky=tk.W, padx=5, pady=5)

            label_valor = tk.Label(
                frame_stats,
                text="0",
                font=("Arial", 10, "bold"),
                bg="#1e1e1e",
                fg="#4CAF50"
            )
            label_valor.grid(row=i, column=1, sticky=tk.W, padx=5, pady=5)
            self.stats_labels[key] = label_valor

        # ==== BARRA DE STATUS INFERIOR ====
        self.barra_status = tk.Label(
            self.root,
            text="💡 Sistema pronto. Clique em 'INICIAR CÂMERA' para começar.",
            font=("Arial", 9),
            bg="#1e1e1e",
            fg="white",
            anchor=tk.W,
            padx=10
        )
        self.barra_status.pack(fill=tk.X, side=tk.BOTTOM)

        # Adicionar log inicial
        self.adicionar_log("Sistema inicializado com sucesso.")

    def criar_campos_configuracao(self, parent):
        """Cria campos editáveis para todas as configurações"""

        row = 0

        # SEÇÃO: Medições
        tk.Label(
            parent,
            text="📏 MEDIÇÕES",
            font=("Arial", 11, "bold"),
            bg="#1e1e1e",
            fg="#4CAF50"
        ).grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=5, pady=(10, 5))
        row += 1

        # Altura câmera ao chão
        tk.Label(
            parent,
            text="Altura câmera (m):",
            font=("Arial", 9),
            bg="#1e1e1e",
            fg="white"
        ).grid(row=row, column=0, sticky=tk.W, padx=5, pady=2)

        self.config_widgets['altura_camera_chao'] = tk.Entry(parent, width=15)
        self.config_widgets['altura_camera_chao'].insert(0, str(self.cfg['medicoes']['altura_camera_chao']))
        self.config_widgets['altura_camera_chao'].grid(row=row, column=1, padx=5, pady=2)
        row += 1

        # Altura cacamba
        tk.Label(
            parent,
            text="Altura cacamba (m):",
            font=("Arial", 9),
            bg="#1e1e1e",
            fg="white"
        ).grid(row=row, column=0, sticky=tk.W, padx=5, pady=2)

        self.config_widgets['altura_caixa'] = tk.Entry(parent, width=15)
        self.config_widgets['altura_caixa'].insert(0, str(self.cfg['medicoes']['altura_caixa']))
        self.config_widgets['altura_caixa'].grid(row=row, column=1, padx=5, pady=2)
        row += 1

        # SEÇÃO: Thresholds
        tk.Label(
            parent,
            text="🎯 THRESHOLDS",
            font=("Arial", 11, "bold"),
            bg="#1e1e1e",
            fg="#4CAF50"
        ).grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=5, pady=(10, 5))
        row += 1

        # Limite vazia
        tk.Label(
            parent,
            text="Limite VAZIA (m):",
            font=("Arial", 9),
            bg="#1e1e1e",
            fg="white"
        ).grid(row=row, column=0, sticky=tk.W, padx=5, pady=2)

        self.config_widgets['limite_vazia'] = tk.Entry(parent, width=15)
        self.config_widgets['limite_vazia'].insert(0, str(self.cfg['thresholds']['limite_vazia']))
        self.config_widgets['limite_vazia'].grid(row=row, column=1, padx=5, pady=2)
        row += 1

        # Limite cheia
        tk.Label(
            parent,
            text="Limite CHEIA (m):",
            font=("Arial", 9),
            bg="#1e1e1e",
            fg="white"
        ).grid(row=row, column=0, sticky=tk.W, padx=5, pady=2)

        self.config_widgets['limite_cheia'] = tk.Entry(parent, width=15)
        self.config_widgets['limite_cheia'].insert(0, str(self.cfg['thresholds']['limite_cheia']))
        self.config_widgets['limite_cheia'].grid(row=row, column=1, padx=5, pady=2)
        row += 1

        # SEÇÃO: Proteção
        tk.Label(
            parent,
            text="🛡️ PROTEÇÃO CONTRA PESSOAS",
            font=("Arial", 11, "bold"),
            bg="#1e1e1e",
            fg="#4CAF50"
        ).grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=5, pady=(10, 5))
        row += 1

        # Profundidade mínima corpo
        tk.Label(
            parent,
            text="Prof. mínima corpo (m):",
            font=("Arial", 9),
            bg="#1e1e1e",
            fg="white"
        ).grid(row=row, column=0, sticky=tk.W, padx=5, pady=2)

        self.config_widgets['profundidade_minima_corpo'] = tk.Entry(parent, width=15)
        self.config_widgets['profundidade_minima_corpo'].insert(0, str(self.cfg['protecao_pessoa']['profundidade_minima_corpo']))
        self.config_widgets['profundidade_minima_corpo'].grid(row=row, column=1, padx=5, pady=2)
        row += 1

        # Área máxima corpo
        tk.Label(
            parent,
            text="Área máxima (px²):",
            font=("Arial", 9),
            bg="#1e1e1e",
            fg="white"
        ).grid(row=row, column=0, sticky=tk.W, padx=5, pady=2)

        self.config_widgets['area_maxima_corpo'] = tk.Entry(parent, width=15)
        self.config_widgets['area_maxima_corpo'].insert(0, str(self.cfg['protecao_pessoa']['area_maxima_corpo']))
        self.config_widgets['area_maxima_corpo'].grid(row=row, column=1, padx=5, pady=2)
        row += 1

        # SEÇÃO: Filtros
        tk.Label(
            parent,
            text="🎛️ FILTROS",
            font=("Arial", 11, "bold"),
            bg="#1e1e1e",
            fg="#4CAF50"
        ).grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=5, pady=(10, 5))
        row += 1

        # Tamanho histórico
        tk.Label(
            parent,
            text="Tamanho histórico:",
            font=("Arial", 9),
            bg="#1e1e1e",
            fg="white"
        ).grid(row=row, column=0, sticky=tk.W, padx=5, pady=2)

        self.config_widgets['tamanho_historico'] = tk.Entry(parent, width=15)
        self.config_widgets['tamanho_historico'].insert(0, str(self.cfg['filtros']['tamanho_historico']))
        self.config_widgets['tamanho_historico'].grid(row=row, column=1, padx=5, pady=2)
        row += 1

        # Botão aplicar configurações
        btn_aplicar = tk.Button(
            parent,
            text="✅ Aplicar Configurações",
            command=self.aplicar_configuracoes,
            bg="#4CAF50",
            fg="white",
            font=("Arial", 10, "bold"),
            cursor="hand2"
        )
        btn_aplicar.grid(row=row, column=0, columnspan=2, pady=15)

    def toggle_camera(self):
        """Liga ou desliga a câmera"""
        if not self.camera_ativa:
            self.iniciar_camera()
        else:
            self.parar_camera_thread()

    def iniciar_camera(self):
        """Inicia o pipeline da câmera em uma thread separada"""
        try:
            self.adicionar_log("Iniciando câmera RealSense...")
            self.barra_status.config(text="🔄 Iniciando câmera...")

            # Iniciar thread de câmera
            self.parar_camera = False
            self.thread_camera = threading.Thread(target=self.loop_camera, daemon=True)
            self.thread_camera.start()

            self.camera_ativa = True
            self.btn_toggle_camera.config(text="⏸️ PARAR CÂMERA", bg="#f44336")
            self.tempo_inicio = time.time()

            self.adicionar_log("✅ Câmera iniciada com sucesso!")
            self.barra_status.config(text="✅ Câmera ativa - Detectando...")

        except Exception as e:
            self.adicionar_log(f"❌ Erro ao iniciar câmera: {e}")
            messagebox.showerror("Erro", f"Não foi possível iniciar a câmera:\n{e}")

    def parar_camera_thread(self):
        """Para a thread da câmera"""
        self.adicionar_log("Parando câmera...")
        self.barra_status.config(text="🔄 Parando câmera...")

        self.parar_camera = True

        if self.thread_camera and self.thread_camera.is_alive():
            self.thread_camera.join(timeout=2.0)

        self.camera_ativa = False
        self.btn_toggle_camera.config(text="▶ INICIAR CÂMERA", bg="#4CAF50")

        self.adicionar_log("✅ Câmera parada.")
        self.barra_status.config(text="💤 Câmera parada. Clique em 'INICIAR CÂMERA' para retomar.")

    def loop_camera(self):
        """Loop principal de captura e processamento (roda em thread separada)"""

        # Configurar pipeline
        pipeline = rs.pipeline()
        config = rs.config()

        cfg = self.cfg

        RESOLUCAO_LARGURA = cfg['camera']['resolucao_largura']
        RESOLUCAO_ALTURA = cfg['camera']['resolucao_altura']
        FPS = cfg['camera']['fps']

        config.enable_stream(rs.stream.depth, RESOLUCAO_LARGURA, RESOLUCAO_ALTURA, rs.format.z16, FPS)
        config.enable_stream(rs.stream.infrared, 1, RESOLUCAO_LARGURA, RESOLUCAO_ALTURA, rs.format.y8, FPS)
        config.enable_stream(rs.stream.color, RESOLUCAO_LARGURA, RESOLUCAO_ALTURA, rs.format.bgr8, FPS)

        try:
            profile = pipeline.start(config)
            self.pipeline = pipeline

            # Configurar sensor
            device = profile.get_device()
            depth_sensor = device.first_depth_sensor()
            depth_scale = depth_sensor.get_depth_scale()

            # Laser
            if depth_sensor.supports(rs.option.emitter_enabled):
                depth_sensor.set_option(rs.option.emitter_enabled, 1.0)
                if depth_sensor.supports(rs.option.laser_power):
                    laser_power = cfg['camera']['laser_potencia']
                    if laser_power > 0:
                        depth_sensor.set_option(rs.option.laser_power, laser_power)

            # Filtros
            decimation = rs.decimation_filter()
            spatial = rs.spatial_filter()
            spatial.set_option(rs.option.filter_magnitude, 2)
            spatial.set_option(rs.option.filter_smooth_alpha, 0.5)
            spatial.set_option(rs.option.filter_smooth_delta, 20)

            temporal = rs.temporal_filter()
            temporal.set_option(rs.option.filter_smooth_alpha, 0.4)
            temporal.set_option(rs.option.filter_smooth_delta, 20)

            hole_filling = rs.hole_filling_filter()

            # Variáveis de controle
            historico_status = deque(maxlen=cfg['filtros']['tamanho_historico'])
            historico_distancias_local = deque(maxlen=cfg['filtros']['historico_distancias'])
            status_anterior = None
            ultima_mudanca_status = time.time()

            # Loop de processamento
            while not self.parar_camera:
                inicio_frame = time.time()

                frames = pipeline.wait_for_frames()

                depth_frame = frames.get_depth_frame()
                ir_frame = frames.get_infrared_frame(1)
                color_frame = frames.get_color_frame()

                if not depth_frame:
                    continue

                # Aplicar filtros
                filtered_depth = decimation.process(depth_frame)
                filtered_depth = spatial.process(filtered_depth)
                filtered_depth = temporal.process(filtered_depth)
                filtered_depth = hole_filling.process(filtered_depth)

                # Converter para numpy
                depth_image = np.asanyarray(filtered_depth.get_data())

                if color_frame:
                    display_image = np.asanyarray(color_frame.get_data())
                else:
                    ir_image = np.asanyarray(ir_frame.get_data())
                    display_image = cv2.cvtColor(ir_image, cv2.COLOR_GRAY2BGR)

                h, w = display_image.shape[:2]

                # Processar detecção (código similar ao V3)
                depth_meters = depth_image * depth_scale

                PROFUNDIDADE_MIN_CAIXA = cfg['medicoes']['profundidade_min_caixa']
                PROFUNDIDADE_MAX_CAIXA = cfg['medicoes']['profundidade_max_caixa']
                AREA_MINIMA_PIXELS = cfg['medicoes']['area_minima_pixels']
                KERNEL_MORPH_SIZE = cfg['filtros']['kernel_morph_size']

                mask_roi = (depth_meters > PROFUNDIDADE_MIN_CAIXA) & (depth_meters < PROFUNDIDADE_MAX_CAIXA)
                mask_uint8 = mask_roi.astype(np.uint8) * 255

                kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (KERNEL_MORPH_SIZE, KERNEL_MORPH_SIZE))
                mask_uint8 = cv2.morphologyEx(mask_uint8, cv2.MORPH_CLOSE, kernel)
                mask_uint8 = cv2.morphologyEx(mask_uint8, cv2.MORPH_OPEN, kernel)

                contours, _ = cv2.findContours(mask_uint8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                caixa_detectada = False
                melhor_contorno = None
                maior_area = 0
                medicoes_grid = []

                CLIP_MIN = cfg['camera']['clip_min']
                CLIP_MAX = cfg['camera']['clip_max']
                GRID_SIZE = cfg['filtros']['grid_medicao_size']

                for contour in contours:
                    area = cv2.contourArea(contour)
                    if area > AREA_MINIMA_PIXELS and area > maior_area:
                        maior_area = area
                        melhor_contorno = contour
                        caixa_detectada = True

                if caixa_detectada and melhor_contorno is not None:
                    x1, y1, w_box, h_box = cv2.boundingRect(melhor_contorno)
                    x2, y2 = x1 + w_box, y1 + h_box

                    cv2.drawContours(display_image, [melhor_contorno], -1, (0, 255, 255), 2)
                    cv2.rectangle(display_image, (x1, y1), (x2, y2), (255, 0, 255), 2)

                    regiao_depth = depth_meters[y1:y2, x1:x2]
                    h_reg, w_reg = regiao_depth.shape

                    cell_h, cell_w = h_reg // GRID_SIZE, w_reg // GRID_SIZE

                    for i in range(GRID_SIZE):
                        for j in range(GRID_SIZE):
                            y_start = i * cell_h
                            y_end = (i + 1) * cell_h if i < GRID_SIZE - 1 else h_reg
                            x_start = j * cell_w
                            x_end = (j + 1) * cell_w if j < GRID_SIZE - 1 else w_reg

                            celula = regiao_depth[y_start:y_end, x_start:x_end]
                            celula_valida = celula[(celula > CLIP_MIN) & (celula < CLIP_MAX)]

                            if len(celula_valida) > 10:
                                medicoes_grid.append(np.median(celula_valida))
                else:
                    # Fallback
                    center_x, center_y = w // 2, h // 2
                    size = 50
                    x1 = max(0, center_x - size)
                    x2 = min(w, center_x + size)
                    y1 = max(0, center_y - size)
                    y2 = min(h, center_y + size)

                    regiao_depth = depth_meters[y1:y2, x1:x2]
                    regiao_valida = regiao_depth[(regiao_depth > CLIP_MIN) & (regiao_depth < CLIP_MAX)]

                    if len(regiao_valida) > 10:
                        medicoes_grid = [np.median(regiao_valida)]

                    cv2.line(display_image, (center_x - 30, center_y), (center_x + 30, center_y), (255, 255, 255), 2)
                    cv2.line(display_image, (center_x, center_y - 30), (center_x, center_y + 30), (255, 255, 255), 2)

                # Processar medições
                if len(medicoes_grid) > 0:
                    distancia_final = np.median(medicoes_grid)
                    historico_distancias_local.append(distancia_final)

                    ALTURA_CAMERA_CHAO = float(self.config_widgets['altura_camera_chao'].get())
                    ALTURA_CAIXA = float(self.config_widgets['altura_caixa'].get())
                    LIMITE_VAZIA = float(self.config_widgets['limite_vazia'].get())
                    LIMITE_CHEIA = float(self.config_widgets['limite_cheia'].get())

                    altura_conteudo = ALTURA_CAMERA_CHAO - distancia_final
                    percentual_cheio = (altura_conteudo / ALTURA_CAIXA) * 100
                    percentual_cheio = max(0, min(100, percentual_cheio))

                    # Determinar status
                    if distancia_final >= LIMITE_VAZIA:
                        status_atual = "VAZIA"
                        cor_status = (0, 0, 255)
                    elif distancia_final <= LIMITE_CHEIA:
                        status_atual = "CHEIA"
                        cor_status = (0, 255, 0)
                    else:
                        status_atual = "PARCIAL"
                        cor_status = (0, 165, 255)

                    historico_status.append(status_atual)

                    # Status estável
                    if len(historico_status) >= 5:
                        contagem = {
                            "VAZIA": historico_status.count("VAZIA"),
                            "PARCIAL": historico_status.count("PARCIAL"),
                            "CHEIA": historico_status.count("CHEIA")
                        }
                        status_estavel = max(contagem, key=contagem.get)
                    else:
                        status_estavel = status_atual

                    # Detectar mudança
                    tempo_agora = time.time()
                    TEMPO_MINIMO_ENTRE_MUDANCAS = cfg['protecao_pessoa']['tempo_minimo_entre_mudancas']

                    if status_estavel != status_anterior and (tempo_agora - ultima_mudanca_status) > TEMPO_MINIMO_ENTRE_MUDANCAS:
                        ultima_mudanca_status = tempo_agora
                        self.registrar_mudanca_status(status_anterior, status_estavel)
                        status_anterior = status_estavel

                    # Calcular confiança
                    desvio_padrao = np.std(list(historico_distancias_local)) if len(historico_distancias_local) > 1 else 0
                    confianca = 100 - (desvio_padrao * 1000)
                    confianca = max(0, min(100, confianca))

                    # Atualizar dados
                    self.distancia_atual = distancia_final
                    self.confianca_atual = confianca
                    self.percentual_cheio = percentual_cheio
                    self.status_atual = status_estavel

                    # Desenhar informações no frame
                    cv2.rectangle(display_image, (0, 0), (w, 80), (20, 20, 20), -1)
                    cv2.putText(display_image, f"STATUS: {status_estavel}", (10, 30),
                              cv2.FONT_HERSHEY_SIMPLEX, 1.0, cor_status, 2)
                    cv2.putText(display_image, f"Dist: {distancia_final:.3f}m | {percentual_cheio:.0f}%", (10, 60),
                              cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                else:
                    self.status_atual = "SEM LEITURA"
                    self.distancia_atual = 0.0
                    self.confianca_atual = 0.0
                    self.percentual_cheio = 0.0

                # Atualizar contador e FPS
                self.contador_frames += 1
                fim_frame = time.time()
                fps_frame = 1.0 / (fim_frame - inicio_frame) if (fim_frame - inicio_frame) > 0 else 0
                self.historico_fps.append(fps_frame)
                self.fps_atual = np.mean(list(self.historico_fps))

                # Converter frame para GUI
                self.frame_atual = cv2.cvtColor(display_image, cv2.COLOR_BGR2RGB)
                self.depth_frame_atual = depth_image

                # Adicionar distância ao histórico para gráfico
                self.historico_distancias.append(self.distancia_atual)

                # Atualizar GUI (deve ser chamado da thread principal)
                self.root.after(0, self.atualizar_gui)

        except Exception as e:
            self.adicionar_log(f"❌ Erro no loop da câmera: {e}")

        finally:
            if pipeline:
                pipeline.stop()
                self.pipeline = None

    def atualizar_gui(self):
        """Atualiza todos os componentes da GUI com os dados mais recentes"""

        # Atualizar vídeo
        if self.frame_atual is not None:
            img = Image.fromarray(self.frame_atual)
            img = img.resize((640, 480), Image.Resampling.LANCZOS)
            img_tk = ImageTk.PhotoImage(image=img)
            self.label_video.config(image=img_tk)
            self.label_video.image = img_tk

        # Atualizar status
        cores_status = {
            "VAZIA": "#f44336",
            "PARCIAL": "#FF9800",
            "CHEIA": "#4CAF50",
            "SEM LEITURA": "#808080",
            "AGUARDANDO": "#808080"
        }

        self.label_status.config(
            text=self.status_atual,
            fg=cores_status.get(self.status_atual, "#808080")
        )

        # Atualizar medições
        self.label_distancia.config(text=f"{self.distancia_atual:.3f} m")
        self.label_percentual.config(text=f"{self.percentual_cheio:.0f}%")
        self.label_confianca.config(text=f"{self.confianca_atual:.0f}%")
        self.label_fps.config(text=f"{self.fps_atual:.1f}")

        # Atualizar barra de progresso
        self.progress_percentual['value'] = self.percentual_cheio

        # Atualizar gráfico
        self.desenhar_grafico()

        # Atualizar estatísticas
        self.atualizar_estatisticas()

    def desenhar_grafico(self):
        """Desenha gráfico de histórico de distância"""
        self.canvas_grafico.delete("all")

        if len(self.historico_distancias) < 2:
            return

        # Dimensões do canvas
        w = self.canvas_grafico.winfo_width()
        h = self.canvas_grafico.winfo_height()

        if w <= 1 or h <= 1:
            w, h = 350, 300

        # Margens
        margin_x, margin_y = 40, 30
        graph_w = w - 2 * margin_x
        graph_h = h - 2 * margin_y

        # Eixos
        self.canvas_grafico.create_line(margin_x, h - margin_y, w - margin_x, h - margin_y, fill="white", width=2)
        self.canvas_grafico.create_line(margin_x, margin_y, margin_x, h - margin_y, fill="white", width=2)

        # Dados
        distancias = list(self.historico_distancias)
        n = len(distancias)

        if n == 0:
            return

        min_dist = min(distancias)
        max_dist = max(distancias)
        range_dist = max_dist - min_dist if max_dist != min_dist else 1

        # Linhas de referência
        try:
            LIMITE_VAZIA = float(self.config_widgets['limite_vazia'].get())
            LIMITE_CHEIA = float(self.config_widgets['limite_cheia'].get())

            # Linha VAZIA
            y_vazia = h - margin_y - ((LIMITE_VAZIA - min_dist) / range_dist) * graph_h
            self.canvas_grafico.create_line(margin_x, y_vazia, w - margin_x, y_vazia, fill="red", dash=(5, 5))
            self.canvas_grafico.create_text(margin_x - 5, y_vazia, text="V", fill="red", anchor="e")

            # Linha CHEIA
            y_cheia = h - margin_y - ((LIMITE_CHEIA - min_dist) / range_dist) * graph_h
            self.canvas_grafico.create_line(margin_x, y_cheia, w - margin_x, y_cheia, fill="green", dash=(5, 5))
            self.canvas_grafico.create_text(margin_x - 5, y_cheia, text="C", fill="green", anchor="e")
        except:
            pass

        # Desenhar linha do gráfico
        pontos = []
        for i, dist in enumerate(distancias):
            x = margin_x + (i / (n - 1)) * graph_w if n > 1 else margin_x + graph_w / 2
            y = h - margin_y - ((dist - min_dist) / range_dist) * graph_h
            pontos.append((x, y))

        for i in range(len(pontos) - 1):
            self.canvas_grafico.create_line(
                pontos[i][0], pontos[i][1],
                pontos[i + 1][0], pontos[i + 1][1],
                fill="#00ff00", width=2
            )

        # Labels
        self.canvas_grafico.create_text(w / 2, h - 10, text="Tempo", fill="white")
        self.canvas_grafico.create_text(15, margin_y, text="Dist (m)", fill="white", angle=90)

    def atualizar_estatisticas(self):
        """Atualiza painel de estatísticas"""
        if self.tempo_inicio:
            tempo_total = time.time() - self.tempo_inicio
            self.stats_labels['tempo_total'].config(text=f"{tempo_total:.0f}s")

        self.stats_labels['frames_total'].config(text=str(self.contador_frames))
        self.stats_labels['fps_medio'].config(text=f"{self.fps_atual:.1f}")

        # Contar tempo em cada status
        tempo_vazia = self.historico_status.count("VAZIA")
        tempo_parcial = self.historico_status.count("PARCIAL")
        tempo_cheia = self.historico_status.count("CHEIA")

        self.stats_labels['tempo_vazia'].config(text=str(tempo_vazia))
        self.stats_labels['tempo_parcial'].config(text=str(tempo_parcial))
        self.stats_labels['tempo_cheia'].config(text=str(tempo_cheia))
        self.stats_labels['mudancas_total'].config(text=str(len(self.log_mudancas)))

        if len(self.historico_distancias) > 0:
            # Calcular confiança média
            confianca_media = np.mean([self.confianca_atual])
            self.stats_labels['confianca_media'].config(text=f"{confianca_media:.0f}%")

    def registrar_mudanca_status(self, status_anterior, status_novo):
        """Registra mudança de status no histórico"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        mudanca = f"{timestamp} - {status_anterior or 'N/A'} → {status_novo}"

        self.log_mudancas.append(mudanca)
        self.listbox_mudancas.insert(0, mudanca)
        self.adicionar_log(f"🔔 Mudança: {status_anterior or 'N/A'} → {status_novo}")

    def adicionar_log(self, mensagem):
        """Adiciona mensagem ao log"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {mensagem}\n"
        self.text_logs.insert(tk.END, log_entry)
        self.text_logs.see(tk.END)

    def limpar_logs(self):
        """Limpa área de logs"""
        self.text_logs.delete(1.0, tk.END)
        self.adicionar_log("Logs limpos.")

    def aplicar_configuracoes(self):
        """Aplica as configurações editadas"""
        try:
            # Atualizar dicionário de configurações
            self.cfg['medicoes']['altura_camera_chao'] = float(self.config_widgets['altura_camera_chao'].get())
            self.cfg['medicoes']['altura_caixa'] = float(self.config_widgets['altura_caixa'].get())
            self.cfg['thresholds']['limite_vazia'] = float(self.config_widgets['limite_vazia'].get())
            self.cfg['thresholds']['limite_cheia'] = float(self.config_widgets['limite_cheia'].get())
            self.cfg['protecao_pessoa']['profundidade_minima_corpo'] = float(self.config_widgets['profundidade_minima_corpo'].get())
            self.cfg['protecao_pessoa']['area_maxima_corpo'] = int(self.config_widgets['area_maxima_corpo'].get())
            self.cfg['filtros']['tamanho_historico'] = int(self.config_widgets['tamanho_historico'].get())

            self.adicionar_log("✅ Configurações aplicadas!")
            messagebox.showinfo("Sucesso", "Configurações aplicadas com sucesso!")

        except Exception as e:
            self.adicionar_log(f"❌ Erro ao aplicar configurações: {e}")
            messagebox.showerror("Erro", f"Erro ao aplicar configurações:\n{e}")

    def salvar_configuracoes(self):
        """Salva as configurações no arquivo JSON"""
        try:
            # Primeiro aplicar
            self.aplicar_configuracoes()

            # Salvar no arquivo
            caminho = Path(__file__).parent / "config.json"
            with open(caminho, 'w', encoding='utf-8') as f:
                json.dump(self.cfg, f, indent=2, ensure_ascii=False)

            self.adicionar_log(f"💾 Configurações salvas em: {caminho}")
            messagebox.showinfo("Sucesso", f"Configurações salvas em:\n{caminho}")

        except Exception as e:
            self.adicionar_log(f"❌ Erro ao salvar configurações: {e}")
            messagebox.showerror("Erro", f"Erro ao salvar configurações:\n{e}")

    def resetar_estatisticas(self):
        """Reseta todas as estatísticas"""
        self.contador_frames = 0
        self.tempo_inicio = time.time()
        self.historico_status.clear()
        self.historico_distancias.clear()
        self.historico_fps.clear()
        self.log_mudancas.clear()
        self.listbox_mudancas.delete(0, tk.END)

        self.adicionar_log("🔄 Estatísticas resetadas!")
        messagebox.showinfo("Sucesso", "Estatísticas resetadas!")

    def mostrar_ajuda(self):
        """Mostra janela de ajuda"""
        ajuda_texto = """
        SISTEMA DE DETECÇÃO DE NÍVEL DA CACAMBA V4
        ==========================================
        
        COMO USAR:
        1. Ajuste as configurações na aba "Configurações"
        2. Clique em "INICIAR CÂMERA" para começar
        3. O sistema detectará automaticamente o nível
        4. Use "SALVAR CONFIG" para gravar as configurações
        
        CONFIGURAÇÕES PRINCIPAIS:
        • Altura câmera: Distância da câmera ao chão (m)
        • Altura cacamba: Altura total da cacamba (m)
        • Limite VAZIA: Distância para considerar vazia (m)
        • Limite CHEIA: Distância para considerar cheia (m)
        
        STATUS:
        • VAZIA: Cacamba sem conteúdo
        • PARCIAL: Cacamba parcialmente cheia
        • CHEIA: Cacamba completamente cheia
        
        DICAS:
        • Mantenha a área limpa durante calibração
        • Ajuste os limites conforme necessário
        • Use a aba "Histórico" para visualizar tendências
        
        Versão: 4.0
        """

        messagebox.showinfo("Ajuda", ajuda_texto)

    def fechar_aplicacao(self):
        """Fecha a aplicação de forma segura"""
        if self.camera_ativa:
            self.parar_camera_thread()

        self.root.quit()
        self.root.destroy()


def main():
    """Função principal"""
    root = tk.Tk()
    app = DetectorCacambaGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()

