import pyrealsense2 as rs
import numpy as np
import cv2


def rastrear_cacamba_hostil():
    # --- CONFIGURAÇÕES ---
    AREA_MINIMA = 10000
    ALTURA_BORDA_CAMINHAO = 3.5

    # Filtro de Distância (Min/Max em metros)
    # Ignora poeira colada na lente (< 0.5m) e fundo infinito (> 6m)
    CLIP_MIN = 0.5
    CLIP_MAX = 6.0

    # --- INICIALIZAÇÃO DA REALSENSE ---
    pipeline = rs.pipeline()
    config = rs.config()

    # MUDANÇA 1: Não usamos mais .color. Usamos Infravermelho (IR) e Profundidade.
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

            # Melhora o contraste da imagem IR para destacar as bordas da caçamba no escuro
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
            status = "AGUARDANDO CAMINHAO..."
            cor_status = (0, 0, 255)  # Vermelho

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

                        if distancia_mediana < ALTURA_BORDA_CAMINHAO:
                            status = "CARGA DETECTADA"
                            cor_status = (0, 255, 0)  # Verde

                            # Cálculo de % de enchimento (estimativa simples)
                            # Assumindo que o chão da caçamba está a 4.0m e a borda a 3.5m
                            # E a carga sobe até 2.0m
                            # Isso é apenas um exemplo, você deve calibrar com seu caminhão real
                            chao_cacamba = 4.0
                            altura_carga = chao_cacamba - distancia_mediana
                            if altura_carga < 0: altura_carga = 0

                            texto_info = f"Altura Carga: {altura_carga:.2f}m"
                        else:
                            status = "CACAMBA VAZIA"
                            cor_status = (0, 165, 255)  # Laranja
                            texto_info = f"Profundidade: {distancia_mediana:.2f}m"

                        # Desenhar texto
                        x, y, w, h = cv2.boundingRect(melhor_retangulo)
                        cv2.putText(display_image, texto_info, (x, y + h + 25),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, cor_status, 2)

            # --- EXIBIÇÃO ---
            cv2.putText(display_image, f"MODO IR - {status}", (20, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, cor_status, 2)

            # Mostra a visão do sensor IR (que vê no escuro)
            cv2.imshow('Monitoramento Noturno/Poeira', display_image)

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