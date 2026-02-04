import pyrealsense2 as rs
import numpy as np
import cv2


def rastrear_cacamba_hostil():
    # --- CONFIGURAÇÕES PARA TESTE COM CACAMBA DE ISOPOR ---
    # Cacamba: 20cm de altura
    # Câmera: 72.5cm (0.725m) do chão

    AREA_MINIMA = 5000  # Reduzido para detectar cacamba menor

    # Distâncias de referência (em metros)
    ALTURA_CAMERA_CHAO = 0.725  # 72.5cm
    ALTURA_CACAMBA = 0.20  # 20cm
    ALTURA_BORDA_CACAMBA = ALTURA_CAMERA_CHAO - ALTURA_CACAMBA  # 0.525m até a borda
    ALTURA_FUNDO_CACAMBA = ALTURA_CAMERA_CHAO  # 0.725m até o fundo da cacamba

    # Tolerância para detecção (em metros)
    TOLERANCIA = 0.03  # 3cm de margem

    # Filtro de Distância (Min/Max em metros)
    CLIP_MIN = 0.3  # Reduzido para detectar objetos mais próximos
    CLIP_MAX = 1.5  # Ajustado para o ambiente de teste

    # --- INICIALIZAÇÃO DA REALSENSE ---
    pipeline = rs.pipeline()
    config = rs.config()

    # Usamos Infravermelho (IR) e Profundidade.
    # O IR funciona no escuro total graças ao projetor laser da câmera.
    config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
    config.enable_stream(rs.stream.infrared, 1, 640, 480, rs.format.y8, 30)

    print("[INFO] Iniciando rastreamento IR (Visão Noturna)...")
    profile = pipeline.start(config)

    # --- CONFIGURAÇÃO DE FILTROS (A "Mágica" contra Poeira) ---
    # 1. Decimation: Reduz resolução para diminuir ruído e aumentar performance
    decimation = rs.decimation_filter()
    decimation.set_option(rs.option.filter_magnitude, 1)  # 1 = sem redução, aumente se tiver muito ruído

    # 2. Spatial: Suaviza a superfície (tapa buracos na profundidade causados por poeira)
    spatial = rs.spatial_filter()
    spatial.set_option(rs.option.filter_magnitude, 2)
    spatial.set_option(rs.option.filter_smooth_alpha, 0.5)
    spatial.set_option(rs.option.filter_smooth_delta, 20)

    # 3. Temporal: O MAIS IMPORTANTE PARA POEIRA.
    # Ele compara o frame atual com os anteriores. Se um pixel (poeira) aparece e some rápido, ele é removido.
    temporal = rs.temporal_filter()

    # Forçar o projetor laser a ligar (caso esteja desligado)
    device = profile.get_device()
    depth_sensor = device.first_depth_sensor()
    if depth_sensor.supports(rs.option.emitter_enabled):
        depth_sensor.set_option(rs.option.emitter_enabled, 1.0)  # 1 = Ligado
        # Aumentar a potência do laser para penetrar poeira (máximo costuma ser 360)
        if depth_sensor.supports(rs.option.laser_power):
            max_laser = depth_sensor.get_option_range(rs.option.laser_power).max
            depth_sensor.set_option(rs.option.laser_power, max_laser)

    depth_scale = depth_sensor.get_depth_scale()

    try:
        while True:
            frames = pipeline.wait_for_frames()

            # Alinhamento não é estritamente necessário se usarmos IR e Depth do mesmo sensor,
            # mas garante precisão pixel-a-pixel.
            # Nas D435/D455, o IR Esquerdo (index 1) é perfeitamente alinhado com o Depth.
            ir_frame = frames.get_infrared_frame(1)
            depth_frame = frames.get_depth_frame()

            if not depth_frame or not ir_frame:
                continue

            # --- APLICAÇÃO DOS FILTROS (Limpeza da Imagem) ---
            # A ordem importa: Decimation -> Spatial -> Temporal
            filtered_depth = spatial.process(depth_frame)
            filtered_depth = temporal.process(filtered_depth)

            # Converter para Numpy
            # A imagem IR já vem em tons de cinza (Y8), perfeita para processar
            ir_image = np.asanyarray(ir_frame.get_data())
            depth_image = np.asanyarray(filtered_depth.get_data())

            # --- PROCESSAMENTO DE VISÃO (Agora no Espectro IR) ---

            # Melhora o contraste da imagem IR para destacar as bordas da cacamba no escuro
            # Equalização de histograma ajuda a ver detalhes mesmo com pouca luz refletida
            ir_enhanced = cv2.equalizeHist(ir_image)

            # Blur para remover ruído granulado do sensor IR
            blur = cv2.GaussianBlur(ir_enhanced, (5, 5), 0)

            # Detecção de Bordas
            # O IR tem alto contraste nas bordas físicas, funciona muito bem
            edges = cv2.Canny(blur, 50, 150)

            # Dilatar as bordas ajuda a conectar linhas quebradas pela poeira
            edges = cv2.dilate(edges, None, iterations=1)

            contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

            melhor_retangulo = None
            maior_area = 0

            # Como vamos desenhar informações coloridas para o humano ver,
            # convertemos o IR de volta para BGR apenas para visualização
            display_image = cv2.cvtColor(ir_image, cv2.COLOR_GRAY2BGR)

            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area > AREA_MINIMA:
                    perimetro = cv2.arcLength(cnt, True)
                    approx = cv2.approxPolyDP(cnt, 0.02 * perimetro, True)

                    if len(approx) == 4:
                        if area > maior_area:
                            maior_area = area
                            melhor_retangulo = approx

            # --- ANÁLISE DE PROFUNDIDADE ---
            status = "AGUARDANDO CACAMBA..."
            cor_status = (128, 128, 128)  # Cinza

            if melhor_retangulo is not None:
                cv2.drawContours(display_image, [melhor_retangulo], -1, (0, 255, 255), 2)

                # Criar máscara
                mascara = np.zeros(depth_image.shape, dtype=np.uint8)
                cv2.drawContours(mascara, [melhor_retangulo], -1, 255, -1)

                # --- TRUQUE CONTRA POEIRA NA MEDIÇÃO ---
                # Em vez de pegar a média simples (que pode ser afetada por poeira flutuando),
                # pegamos a MEDIANA ou filtramos pixels muito pertos (ruído)

                # Extrair apenas os pixels de profundidade dentro do retângulo
                pixels_validos = depth_image[mascara == 255]

                if len(pixels_validos) > 0:
                    # Converter para metros
                    distancias_metros = pixels_validos * depth_scale

                    # Remover leituras absurdas (filtros de clip)
                    # Ex: Se a poeira refletiu a 10cm da câmera, ignoramos
                    distancias_reais = distancias_metros[
                        (distancias_metros > CLIP_MIN) & (distancias_metros < CLIP_MAX)
                        ]

                    if len(distancias_reais) > 0:
                        # Usamos a mediana para evitar outliers (picos de poeira)
                        distancia_mediana = np.median(distancias_reais)

                        # Calcular a altura do conteúdo dentro da cacamba
                        altura_conteudo = ALTURA_FUNDO_CACAMBA - distancia_mediana
                        percentual_cheio = (altura_conteudo / ALTURA_CACAMBA) * 100

                        # Limitar percentual entre 0 e 100
                        if percentual_cheio < 0:
                            percentual_cheio = 0
                        elif percentual_cheio > 100:
                            percentual_cheio = 100

                        # Classificar estado da cacamba
                        if distancia_mediana >= (ALTURA_FUNDO_CACAMBA - TOLERANCIA):
                            # Distância próxima ao fundo = cacamba vazia
                            status = "CACAMBA VAZIA"
                            cor_status = (0, 0, 255)  # Vermelho
                            texto_info = f"Vazia | Dist: {distancia_mediana:.3f}m"

                        elif distancia_mediana <= (ALTURA_BORDA_CACAMBA + TOLERANCIA):
                            # Objeto até a borda ou acima
                            status = "CACAMBA CHEIA"
                            cor_status = (0, 255, 0)  # Verde
                            texto_info = f"Cheia {percentual_cheio:.0f}% | Alt: {altura_conteudo*100:.1f}cm"

                        else:
                            # Objeto no meio da cacamba
                            status = "PARCIALMENTE CHEIA"
                            cor_status = (0, 165, 255)  # Laranja
                            texto_info = f"Parcial {percentual_cheio:.0f}% | Alt: {altura_conteudo*100:.1f}cm"

                        # Desenhar texto com informações detalhadas
                        x, y, w, h = cv2.boundingRect(melhor_retangulo)
                        cv2.putText(display_image, texto_info, (x, y + h + 25),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, cor_status, 2)

                        # Informação adicional de debug
                        texto_debug = f"Medida: {distancia_mediana:.3f}m | Fundo: {ALTURA_FUNDO_CACAMBA:.3f}m | Borda: {ALTURA_BORDA_CACAMBA:.3f}m"
                        cv2.putText(display_image, texto_debug, (x, y + h + 50),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

            # --- EXIBIÇÃO ---
            # Informações no topo da tela
            cv2.rectangle(display_image, (0, 0), (640, 100), (0, 0, 0), -1)
            cv2.putText(display_image, f"MODO IR - {status}", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, cor_status, 2)
            cv2.putText(display_image, f"Camera: {ALTURA_CAMERA_CHAO*100:.1f}cm | Cacamba: {ALTURA_CACAMBA*100:.0f}cm",
                        (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            cv2.putText(display_image, "Pressione 'q' para sair",
                        (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)

            # Mostra a visão do sensor IR (que vê no escuro)
            cv2.imshow('Monitor Deteccao Cacamba', display_image)

            # Opcional: ver o mapa de calor da profundidade filtrada
            depth_colormap = cv2.applyColorMap(cv2.convertScaleAbs(depth_image, alpha=0.03), cv2.COLORMAP_JET)
            cv2.imshow('Depth Map Filtrado', depth_colormap)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    finally:
        pipeline.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    rastrear_cacamba_hostil()