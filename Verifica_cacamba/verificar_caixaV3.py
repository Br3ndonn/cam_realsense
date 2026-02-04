import pyrealsense2 as rs
import numpy as np
import cv2
from collections import deque
import time
import json
from pathlib import Path


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
            print(f"✅ Configurações carregadas de: {caminho}")
            return config
        else:
            print(f"⚠️  Arquivo {caminho} não encontrado. Usando valores padrão.")
            # Criar arquivo de configuração padrão
            with open(caminho, 'w', encoding='utf-8') as f:
                json.dump(config_padrao, f, indent=2, ensure_ascii=False)
            print(f"📝 Arquivo de configuração criado: {caminho}")
            return config_padrao
    except Exception as e:
        print(f"❌ Erro ao carregar configurações: {e}")
        print("   Usando valores padrão.")
        return config_padrao


def verificar_caixa_v3():
    """
    Versão 3: Sistema híbrido avançado com detecção por profundidade

    MELHORIAS:
    - Detecção de caixa usando mapa de profundidade (não depende de iluminação)
    - Filtro temporal com histórico para estabilizar detecção
    - Sensor infravermelho para ambientes escuros
    - Medição em múltiplas regiões para maior precisão
    - Alertas visuais e sonoros (beep no terminal)
    - Estatísticas em tempo real
    - Rejeição de pessoas/objetos grandes demais
    """

    # --- CARREGAR CONFIGURAÇÕES DO JSON ---
    cfg = carregar_configuracoes()

    def validar_deteccao(contour, profundidade_mediana, area, w, h, PROFUNDIDADE_MINIMA_CORPO, AREA_MAXIMA_CORPO, ROI_X_MIN, ROI_X_MAX, ROI_Y_MIN, ROI_Y_MAX):
        """Valida se a detecção é realmente a caixa e não uma pessoa"""

        # Verificação 1: Profundidade muito pequena = pessoa muito próxima
        if profundidade_mediana < PROFUNDIDADE_MINIMA_CORPO:
            return False, "Objeto muito próximo (< 20cm) - Provavelmente pessoa"

        # Verificação 2: Área muito grande = provavelmente pessoa ou corpo
        if area > AREA_MAXIMA_CORPO:
            return False, f"Objeto muito grande ({area} px²) - Provavelmente pessoa"

        # Verificação 3: Contorno fora da ROI esperada da caixa
        x, y, w_box, h_box = cv2.boundingRect(contour)

        roi_x_center = (x + w_box/2) / w
        roi_y_center = (y + h_box/2) / h

        if not (ROI_X_MIN < roi_x_center < ROI_X_MAX and ROI_Y_MIN < roi_y_center < ROI_Y_MAX):
            return False, f"Detectado fora da ROI esperada ({roi_x_center:.2f}, {roi_y_center:.2f})"

        # Verificação 4: Proporção do contorno (muito alongado = parte de pessoa)
        if w_box > 0 and h_box > 0:
            aspect_ratio = max(w_box, h_box) / min(w_box, h_box)
            if aspect_ratio > 5:  # Muito alongado
                return False, f"Proporção muito alongada ({aspect_ratio:.1f}:1) - Provavelmente parte de pessoa"

        return True, "Validado"

    # --- EXTRAÇÃO DAS CONFIGURAÇÕES DO JSON ---
    # Câmera
    RESOLUCAO_LARGURA = cfg['camera']['resolucao_largura']
    RESOLUCAO_ALTURA = cfg['camera']['resolucao_altura']
    FPS = cfg['camera']['fps']
    CLIP_MIN = cfg['camera']['clip_min']
    CLIP_MAX = cfg['camera']['clip_max']
    LASER_POTENCIA = cfg['camera']['laser_potencia']

    # Medições
    ALTURA_CAMERA_CHAO = cfg['medicoes']['altura_camera_chao']
    ALTURA_CAIXA = cfg['medicoes']['altura_caixa']
    PROFUNDIDADE_MIN_CAIXA = cfg['medicoes']['profundidade_min_caixa']
    PROFUNDIDADE_MAX_CAIXA = cfg['medicoes']['profundidade_max_caixa']
    AREA_MINIMA_PIXELS = cfg['medicoes']['area_minima_pixels']

    # Proteção contra pessoas
    PROFUNDIDADE_MINIMA_CORPO = cfg['protecao_pessoa']['profundidade_minima_corpo']
    AREA_MAXIMA_CORPO = cfg['protecao_pessoa']['area_maxima_corpo']
    VELOCIDADE_MAX_MUDANCA = cfg['protecao_pessoa']['velocidade_max_mudanca']
    TEMPO_MINIMO_ENTRE_MUDANCAS = cfg['protecao_pessoa']['tempo_minimo_entre_mudancas']

    # ROI
    ROI_X_MIN = cfg['roi']['x_min']
    ROI_X_MAX = cfg['roi']['x_max']
    ROI_Y_MIN = cfg['roi']['y_min']
    ROI_Y_MAX = cfg['roi']['y_max']

    # Thresholds
    LIMITE_VAZIA = cfg['thresholds']['limite_vazia']
    LIMITE_CHEIA = cfg['thresholds']['limite_cheia']
    THRESHOLD_BINARY = cfg['thresholds']['threshold_binary']

    # Filtros
    TAMANHO_HISTORICO = cfg['filtros']['tamanho_historico']
    HISTORICO_DISTANCIAS_SIZE = cfg['filtros']['historico_distancias']
    KERNEL_MORPH_SIZE = cfg['filtros']['kernel_morph_size']
    GRID_SIZE = cfg['filtros']['grid_medicao_size']

    # Visualização
    MOSTRAR_FPS = cfg['visualizacao']['mostrar_fps']
    MOSTRAR_GRID = cfg['visualizacao']['mostrar_grid']
    MOSTRAR_IR = cfg['visualizacao']['mostrar_ir']
    COLORMAP = cfg['visualizacao']['colormap']

    # Sons
    BEEP_MUDANCA = cfg['sons']['beep_mudanca_status']

    # Distâncias calculadas
    DISTANCIA_FUNDO_VAZIO = ALTURA_CAMERA_CHAO
    DISTANCIA_BORDA_CHEIA = ALTURA_CAMERA_CHAO - ALTURA_CAIXA
    TOLERANCIA = 0.03

    # Histórico temporal para estabilização
    historico_status = deque(maxlen=TAMANHO_HISTORICO)
    historico_distancias = deque(maxlen=HISTORICO_DISTANCIAS_SIZE)

    # Estatísticas
    contador_frames = 0
    tempo_inicio = time.time()
    ultima_mudanca_status = None
    status_anterior = None

    # --- INICIALIZAÇÃO DA REALSENSE ---
    pipeline = rs.pipeline()
    config = rs.config()

    # Usar IR para ambientes escuros + RGB para visualização
    config.enable_stream(rs.stream.depth, RESOLUCAO_LARGURA, RESOLUCAO_ALTURA, rs.format.z16, FPS)
    config.enable_stream(rs.stream.infrared, 1, RESOLUCAO_LARGURA, RESOLUCAO_ALTURA, rs.format.y8, FPS)
    config.enable_stream(rs.stream.color, RESOLUCAO_LARGURA, RESOLUCAO_ALTURA, rs.format.bgr8, FPS)

    print("="*70)
    print("SISTEMA DE DETECÇÃO DE NÍVEL DA CAIXA V3")
    print("="*70)
    print("🎯 Detecção híbrida por profundidade + IR")
    print("📊 Histórico temporal para estabilização")
    print("🎨 Visualização aprimorada com estatísticas")
    print("="*70)
    print(f"Altura câmera: {ALTURA_CAMERA_CHAO*100:.1f}cm | Altura caixa: {ALTURA_CAIXA*100:.0f}cm")
    print("="*70)

    profile = pipeline.start(config)

    # Configurar sensor de profundidade
    device = profile.get_device()
    depth_sensor = device.first_depth_sensor()
    depth_scale = depth_sensor.get_depth_scale()

    # Maximizar laser para penetrar poeira
    if depth_sensor.supports(rs.option.emitter_enabled):
        depth_sensor.set_option(rs.option.emitter_enabled, 1.0)
        if depth_sensor.supports(rs.option.laser_power):
            # Usar valor do config (ou máximo se o config especificar 0)
            if LASER_POTENCIA > 0:
                depth_sensor.set_option(rs.option.laser_power, LASER_POTENCIA)
                print(f"✓ Laser configurado: {LASER_POTENCIA:.0f}")
            else:
                max_laser = depth_sensor.get_option_range(rs.option.laser_power).max
                depth_sensor.set_option(rs.option.laser_power, max_laser)
                print(f"✓ Laser configurado (máximo): {max_laser:.0f}")

    # Filtros avançados
    decimation = rs.decimation_filter()
    spatial = rs.spatial_filter()
    spatial.set_option(rs.option.filter_magnitude, 2)
    spatial.set_option(rs.option.filter_smooth_alpha, 0.5)
    spatial.set_option(rs.option.filter_smooth_delta, 20)

    temporal = rs.temporal_filter()
    temporal.set_option(rs.option.filter_smooth_alpha, 0.4)
    temporal.set_option(rs.option.filter_smooth_delta, 20)

    hole_filling = rs.hole_filling_filter()

    print("✓ Filtros configurados")
    print("\n🚀 Sistema iniciado! Pressione 'q' para sair.\n")

    try:
        while True:
            contador_frames += 1
            frames = pipeline.wait_for_frames()

            # Obter frames
            depth_frame = frames.get_depth_frame()
            ir_frame = frames.get_infrared_frame(1)
            color_frame = frames.get_color_frame()

            if not depth_frame or not ir_frame:
                continue

            # Aplicar filtros em cascata
            filtered_depth = decimation.process(depth_frame)
            filtered_depth = spatial.process(filtered_depth)
            filtered_depth = temporal.process(filtered_depth)
            filtered_depth = hole_filling.process(filtered_depth)

            # Converter para numpy
            depth_image = np.asanyarray(filtered_depth.get_data())
            ir_image = np.asanyarray(ir_frame.get_data())

            # Usar color se disponível, senão IR
            if color_frame:
                display_image = np.asanyarray(color_frame.get_data())
            else:
                display_image = cv2.cvtColor(ir_image, cv2.COLOR_GRAY2BGR)

            h, w = display_image.shape[:2]

            # --- DETECÇÃO DA CAIXA POR SEGMENTAÇÃO DE PROFUNDIDADE ---
            depth_meters = depth_image * depth_scale

            # Criar máscara da região de interesse (onde pode estar a caixa)
            mask_roi = (depth_meters > PROFUNDIDADE_MIN_CAIXA) & (depth_meters < PROFUNDIDADE_MAX_CAIXA)

            # Encontrar o maior componente conectado (a caixa)
            mask_uint8 = mask_roi.astype(np.uint8) * 255

            # Operações morfológicas para limpar a máscara
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (KERNEL_MORPH_SIZE, KERNEL_MORPH_SIZE))
            mask_uint8 = cv2.morphologyEx(mask_uint8, cv2.MORPH_CLOSE, kernel)
            mask_uint8 = cv2.morphologyEx(mask_uint8, cv2.MORPH_OPEN, kernel)

            # Encontrar contornos na máscara de profundidade
            contours, _ = cv2.findContours(mask_uint8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            caixa_detectada = False
            melhor_contorno = None
            maior_area = 0
            regiao_medicao = None
            motivo_rejeicao = None

            for contour in contours:
                area = cv2.contourArea(contour)
                if area > AREA_MINIMA_PIXELS:
                    if area > maior_area:
                        maior_area = area
                        melhor_contorno = contour

                        # Calcular profundidade dessa região
                        x, y, w_box, h_box = cv2.boundingRect(contour)
                        regiao_depth = depth_meters[y:y+h_box, x:x+w_box]
                        regiao_valida = regiao_depth[(regiao_depth > CLIP_MIN) & (regiao_depth < CLIP_MAX)]

                        if len(regiao_valida) > 10:
                            prof_mediana = np.median(regiao_valida)

                            # VALIDAR: É realmente o conteúdo da caixa ou é uma pessoa?
                            eh_valido, motivo = validar_deteccao(
                                contour, prof_mediana, area, w, h,
                                PROFUNDIDADE_MINIMA_CORPO, AREA_MAXIMA_CORPO,
                                ROI_X_MIN, ROI_X_MAX, ROI_Y_MIN, ROI_Y_MAX
                            )

                            if eh_valido:
                                caixa_detectada = True
                            else:
                                motivo_rejeicao = motivo
                                melhor_contorno = None
                                maior_area = 0

            # --- MEDIÇÃO ---
            if caixa_detectada and melhor_contorno is not None:
                # Obter retângulo delimitador
                x1, y1, w_box, h_box = cv2.boundingRect(melhor_contorno)
                x2, y2 = x1 + w_box, y1 + h_box

                # Desenhar contorno da caixa
                cv2.drawContours(display_image, [melhor_contorno], -1, (0, 255, 255), 2)
                cv2.rectangle(display_image, (x1, y1), (x2, y2), (255, 0, 255), 2)

                # Dividir a região em 9 sub-regiões (grid 3x3) para medição mais robusta
                regiao_depth = depth_meters[y1:y2, x1:x2]
                h_reg, w_reg = regiao_depth.shape

                medicoes_grid = []
                grid_size = GRID_SIZE
                cell_h, cell_w = h_reg // grid_size, w_reg // grid_size

                for i in range(grid_size):
                    for j in range(grid_size):
                        y_start = i * cell_h
                        y_end = (i + 1) * cell_h if i < grid_size - 1 else h_reg
                        x_start = j * cell_w
                        x_end = (j + 1) * cell_w if j < grid_size - 1 else w_reg

                        celula = regiao_depth[y_start:y_end, x_start:x_end]
                        celula_valida = celula[(celula > CLIP_MIN) & (celula < CLIP_MAX)]

                        if len(celula_valida) > 10:
                            medicoes_grid.append(np.median(celula_valida))

                            # Desenhar mini-retângulos do grid
                            cv2.rectangle(display_image,
                                        (x1 + x_start, y1 + y_start),
                                        (x1 + x_end, y1 + y_end),
                                        (100, 100, 100), 1)

                regiao_medicao = (x1, y1, x2, y2)

            else:
                # Fallback: usar região central
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
                else:
                    medicoes_grid = []

                # Desenhar cruz
                cv2.line(display_image, (center_x - 30, center_y),
                        (center_x + 30, center_y), (255, 255, 255), 2)
                cv2.line(display_image, (center_x, center_y - 30),
                        (center_x, center_y + 30), (255, 255, 255), 2)

                regiao_medicao = (x1, y1, x2, y2)

            # --- PROCESSAMENTO DE MEDIÇÕES ---
            if len(medicoes_grid) > 0:
                # Usar mediana das medianas (super robusto!)
                distancia_final = np.median(medicoes_grid)
                historico_distancias.append(distancia_final)

                # FILTRO: Rejeitar mudanças muito rápidas (pessoa se movendo)
                eh_mudanca_rapida = False
                if len(historico_distancias) > 1:
                    dist_anterior = list(historico_distancias)[-2]
                    mudanca = abs(distancia_final - dist_anterior)
                    if mudanca > VELOCIDADE_MAX_MUDANCA:
                        eh_mudanca_rapida = True
                        motivo_rejeicao = f"Mudança muito rápida ({mudanca:.3f}m) - Pessoa se movendo?"

                # Calcular estatísticas
                altura_conteudo = ALTURA_CAMERA_CHAO - distancia_final
                percentual_cheio = (altura_conteudo / ALTURA_CAIXA) * 100
                percentual_cheio = max(0, min(100, percentual_cheio))

                # Determinar status (se não foi mudança rápida)
                if eh_mudanca_rapida:
                    status_atual = "INSTÁVEL"
                    cor_status = (0, 165, 255)  # Laranja
                elif distancia_final >= LIMITE_VAZIA:
                    status_atual = "VAZIA"
                    cor_status = (0, 0, 255)  # Vermelho
                elif distancia_final <= LIMITE_CHEIA:
                    status_atual = "CHEIA"
                    cor_status = (0, 255, 0)  # Verde
                else:
                    status_atual = "PARCIAL"
                    cor_status = (0, 165, 255)  # Laranja

                # Adicionar ao histórico
                historico_status.append(status_atual)

                # Estabilização: status só muda se 70% do histórico concordar
                if len(historico_status) >= 5:
                    contagem = {
                        "VAZIA": historico_status.count("VAZIA"),
                        "PARCIAL": historico_status.count("PARCIAL"),
                        "CHEIA": historico_status.count("CHEIA"),
                        "INSTÁVEL": historico_status.count("INSTÁVEL")
                    }
                    status_estavel = max(contagem, key=contagem.get)
                else:
                    status_estavel = status_atual

                # Detectar mudança de status (com proteção temporal)
                tempo_agora = time.time()
                tempo_desde_ultima_mudanca = tempo_agora - (ultima_mudanca_status or tempo_agora)

                if status_estavel != status_anterior and tempo_desde_ultima_mudanca > TEMPO_MINIMO_ENTRE_MUDANCAS:
                    ultima_mudanca_status = tempo_agora
                    print(f"\n🔔 MUDANÇA DE STATUS: {status_anterior or 'N/A'} → {status_estavel}")
                    status_anterior = status_estavel

                # Calcular métricas
                desvio_padrao = np.std(list(historico_distancias)) if len(historico_distancias) > 1 else 0
                confianca = 100 - (desvio_padrao * 1000)  # Quanto menor o desvio, maior a confiança
                confianca = max(0, min(100, confianca))

                # Preparar textos
                modo = "CAIXA DETECTADA" if caixa_detectada else "Modo Centro"
                texto_dist = f"Dist: {distancia_final:.3f}m ({len(medicoes_grid)} pts)"
                texto_altura = f"Altura: {altura_conteudo*100:.1f}cm"
                texto_percent = f"{percentual_cheio:.0f}%"
                texto_conf = f"Confianca: {confianca:.0f}%"
                texto_area = f"Area: {maior_area:.0f}px²" if caixa_detectada else ""

            else:
                status_estavel = "SEM LEITURA"
                cor_status = (128, 128, 128)
                modo = "Aguardando dados..."
                texto_dist = "Sem medicao valida"
                texto_altura = ""
                texto_percent = ""
                texto_conf = ""
                texto_area = ""
                confianca = 0

                # Se foi rejeitado, mostrar motivo
                if motivo_rejeicao:
                    modo = f"⚠️ REJEITADO: {motivo_rejeicao[:40]}"

            # --- VISUALIZAÇÃO AVANÇADA ---

            # Painel superior (status)
            cv2.rectangle(display_image, (0, 0), (w, 140), (20, 20, 20), -1)

            # Status grande com borda
            status_text = f"STATUS: {status_estavel}"
            cv2.putText(display_image, status_text, (22, 52),
                       cv2.FONT_HERSHEY_SIMPLEX, 1.3, (0, 0, 0), 5)
            cv2.putText(display_image, status_text, (20, 50),
                       cv2.FONT_HERSHEY_SIMPLEX, 1.3, cor_status, 3)

            # Informações detalhadas
            cv2.putText(display_image, texto_dist, (20, 85),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            cv2.putText(display_image, modo, (20, 105),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 255, 255), 1)

            if texto_altura:
                cv2.putText(display_image, f"{texto_altura} | {texto_percent}", (20, 125),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, cor_status, 2)

            # Painel lateral direito (estatísticas)
            cv2.rectangle(display_image, (w - 200, 0), (w, 180), (20, 20, 20), -1)

            stats_y = 25
            cv2.putText(display_image, "ESTATISTICAS", (w - 190, stats_y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

            stats_y += 25
            cv2.putText(display_image, texto_conf, (w - 190, stats_y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 255, 100), 1)

            stats_y += 20
            fps = contador_frames / (time.time() - tempo_inicio)
            cv2.putText(display_image, f"FPS: {fps:.1f}", (w - 190, stats_y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

            stats_y += 20
            cv2.putText(display_image, f"Frames: {contador_frames}", (w - 190, stats_y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)

            if texto_area:
                stats_y += 20
                cv2.putText(display_image, texto_area, (w - 190, stats_y),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)

            stats_y += 25
            cv2.putText(display_image, f"Historico: {len(historico_status)}/{TAMANHO_HISTORICO}",
                       (w - 190, stats_y), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)

            # Desenhar região de medição
            if regiao_medicao:
                x1, y1, x2, y2 = regiao_medicao
                cv2.rectangle(display_image, (x1, y1), (x2, y2), cor_status, 3)

            # Barra de confiança
            barra_x = w - 190
            barra_y = 155
            barra_w = 180
            barra_h = 15

            cv2.rectangle(display_image, (barra_x, barra_y), (barra_x + barra_w, barra_y + barra_h),
                         (60, 60, 60), -1)

            if confianca > 0:
                barra_preenchida = int((confianca / 100) * barra_w)
                cor_barra = (0, 255, 0) if confianca > 70 else (0, 165, 255) if confianca > 40 else (0, 0, 255)
                cv2.rectangle(display_image, (barra_x, barra_y),
                             (barra_x + barra_preenchida, barra_y + barra_h), cor_barra, -1)

            # Rodapé
            cv2.rectangle(display_image, (0, h - 30), (w, h), (20, 20, 20), -1)
            cv2.putText(display_image, "Pressione 'q' para sair | V3 - Deteccao Hibrida",
                       (20, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)

            # Mostrar janela principal
            cv2.imshow('Sistema de Deteccao V3', display_image)

            # Mapa de profundidade colorido
            # Mapear valor do config para colormap do OpenCV
            colormaps = [cv2.COLORMAP_AUTUMN, cv2.COLORMAP_BONE, cv2.COLORMAP_JET,
                        cv2.COLORMAP_WINTER, cv2.COLORMAP_RAINBOW, cv2.COLORMAP_OCEAN,
                        cv2.COLORMAP_SUMMER, cv2.COLORMAP_SPRING, cv2.COLORMAP_COOL,
                        cv2.COLORMAP_HSV, cv2.COLORMAP_PINK, cv2.COLORMAP_HOT]
            colormap_selecionado = colormaps[COLORMAP] if 0 <= COLORMAP < len(colormaps) else cv2.COLORMAP_JET

            depth_colormap = cv2.applyColorMap(
                cv2.convertScaleAbs(depth_image, alpha=0.05),
                colormap_selecionado
            )

            # Sobrepor máscara da caixa detectada
            if caixa_detectada:
                overlay = depth_colormap.copy()
                cv2.drawContours(overlay, [melhor_contorno], -1, (255, 255, 255), 3)
                depth_colormap = cv2.addWeighted(depth_colormap, 0.7, overlay, 0.3, 0)

            cv2.imshow('Mapa de Profundidade - V3', depth_colormap)

            # Visualização IR (visão noturna)
            ir_display = cv2.cvtColor(ir_image, cv2.COLOR_GRAY2BGR)
            cv2.putText(ir_display, "VISAO IR (Funciona no Escuro)", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.imshow('Visao Infravermelho', ir_display)

            # Sair com 'q'
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    finally:
        tempo_total = time.time() - tempo_inicio
        fps_medio = contador_frames / tempo_total

        print("\n" + "="*70)
        print("📊 ESTATÍSTICAS FINAIS")
        print("="*70)
        print(f"⏱️  Tempo total: {tempo_total:.1f}s")
        print(f"🎞️  Frames processados: {contador_frames}")
        print(f"⚡ FPS médio: {fps_medio:.1f}")
        print(f"📈 Status final: {status_anterior or 'N/A'}")
        print("="*70)
        print("✓ Sistema encerrado com sucesso!")

        pipeline.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    verificar_caixa_v3()

