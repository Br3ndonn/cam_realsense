import pyrealsense2 as rs
import numpy as np
import cv2


def verificar_caixa_por_altura():
    """
    Algoritmo simplificado que verifica se a caixa está cheia ou vazia
    baseado APENAS na medição de altura (distância da câmera até a superfície).

    Configuração do teste:
    - Caixa de isopor: 20cm de altura
    - Câmera: 72.5cm do chão (posicionada acima da caixa)
    """

    # --- CONFIGURAÇÕES ---
    ALTURA_CAMERA_CHAO = 0.725  # 72.5cm em metros
    ALTURA_CAIXA = 0.20  # 20cm em metros

    # Distâncias de referência calculadas
    DISTANCIA_FUNDO_VAZIO = ALTURA_CAMERA_CHAO  # 0.725m quando vazia (vê o fundo)
    DISTANCIA_BORDA_CHEIA = ALTURA_CAMERA_CHAO - ALTURA_CAIXA  # 0.525m quando cheia até a borda

    # Tolerância para flutuações na medição (3cm)
    TOLERANCIA = 0.03

    # Limites de detecção com tolerância
    LIMITE_VAZIA = DISTANCIA_FUNDO_VAZIO - TOLERANCIA  # >= 0.695m = vazia
    LIMITE_CHEIA = DISTANCIA_BORDA_CHEIA + TOLERANCIA  # <= 0.555m = cheia

    # Configurações para detecção automática da caixa
    AREA_MINIMA_CAIXA = 3000  # Área mínima em pixels para considerar um contorno válido
    TAMANHO_KERNEL_BLUR = 7  # Tamanho do kernel para suavização

    # --- INICIALIZAÇÃO DA REALSENSE ---
    pipeline = rs.pipeline()
    config = rs.config()

    # Habilitar streams de profundidade e cor
    config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
    config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)

    print("="*70)
    print("SISTEMA DE DETECÇÃO DE NÍVEL DA CAIXA")
    print("="*70)
    print(f"Altura da câmera: {ALTURA_CAMERA_CHAO*100:.1f}cm")
    print(f"Altura da caixa: {ALTURA_CAIXA*100:.0f}cm")
    print(f"Distância esperada (vazia): ~{DISTANCIA_FUNDO_VAZIO:.3f}m")
    print(f"Distância esperada (cheia): ~{DISTANCIA_BORDA_CHEIA:.3f}m")
    print(f"Limite vazia: >= {LIMITE_VAZIA:.3f}m")
    print(f"Limite cheia: <= {LIMITE_CHEIA:.3f}m")
    print("="*70)
    print("\nIniciando câmera RealSense...")

    profile = pipeline.start(config)

    # Obter escala de profundidade
    depth_sensor = profile.get_device().first_depth_sensor()
    depth_scale = depth_sensor.get_depth_scale()

    # Alinhar frames
    align = rs.align(rs.stream.color)

    # Configurar filtros para melhorar precisão
    spatial = rs.spatial_filter()
    spatial.set_option(rs.option.filter_magnitude, 2)
    spatial.set_option(rs.option.filter_smooth_alpha, 0.5)
    spatial.set_option(rs.option.filter_smooth_delta, 20)

    temporal = rs.temporal_filter()

    print("\n✓ Câmera iniciada!")
    print("\nPosicione a caixa centralizada abaixo da câmera.")
    print("Pressione 'q' para sair.\n")

    try:
        while True:
            # Capturar frames
            frames = pipeline.wait_for_frames()
            aligned_frames = align.process(frames)

            depth_frame = aligned_frames.get_depth_frame()
            color_frame = aligned_frames.get_color_frame()

            if not depth_frame or not color_frame:
                continue

            # Aplicar filtros para reduzir ruído
            filtered_depth = spatial.process(depth_frame)
            filtered_depth = temporal.process(filtered_depth)

            # Converter para numpy
            depth_image = np.asanyarray(filtered_depth.get_data())
            color_image = np.asanyarray(color_frame.get_data())

            # Obter dimensões
            h, w = color_image.shape[:2]

            # --- DETECÇÃO AUTOMÁTICA DA CAIXA ---
            # Converter para escala de cinza para processamento
            gray = cv2.cvtColor(color_image, cv2.COLOR_BGR2GRAY)

            # Aplicar blur para reduzir ruído
            blurred = cv2.GaussianBlur(gray, (TAMANHO_KERNEL_BLUR, TAMANHO_KERNEL_BLUR), 0)

            # Detecção de bordas
            edges = cv2.Canny(blurred, 50, 150)

            # Dilatar as bordas para conectar linhas quebradas
            kernel = np.ones((3, 3), np.uint8)
            edges = cv2.dilate(edges, kernel, iterations=2)

            # Encontrar contornos
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            # Procurar o maior retângulo (que deve ser a caixa)
            melhor_contorno = None
            maior_area = 0
            caixa_detectada = False

            for contour in contours:
                area = cv2.contourArea(contour)
                if area > AREA_MINIMA_CAIXA:
                    # Aproximar para um polígono
                    perimeter = cv2.arcLength(contour, True)
                    approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)

                    # Verificar se é um retângulo (4 vértices)
                    if len(approx) >= 4:
                        if area > maior_area:
                            maior_area = area
                            melhor_contorno = approx
                            caixa_detectada = True

            # Se detectou a caixa, usar sua região; caso contrário, usar centro
            if caixa_detectada and melhor_contorno is not None:
                # Obter retângulo delimitador
                x1, y1, w_box, h_box = cv2.boundingRect(melhor_contorno)
                x2 = x1 + w_box
                y2 = y1 + h_box

                # Extrair região de profundidade dentro da caixa
                regiao_depth = depth_image[y1:y2, x1:x2]

                # Desenhar o contorno da caixa detectada
                cv2.drawContours(color_image, [melhor_contorno], -1, (0, 255, 255), 3)
                cv2.rectangle(color_image, (x1, y1), (x2, y2), (255, 0, 255), 2)

            else:
                # Fallback: usar região central se não detectar a caixa
                center_x, center_y = w // 2, h // 2
                regiao_size = 50
                x1 = max(0, center_x - regiao_size)
                x2 = min(w, center_x + regiao_size)
                y1 = max(0, center_y - regiao_size)
                y2 = min(h, center_y + regiao_size)

                regiao_depth = depth_image[y1:y2, x1:x2]

                # Desenhar cruz no centro como fallback
                cruz_tamanho = 30
                cv2.line(color_image, (center_x - cruz_tamanho, center_y),
                         (center_x + cruz_tamanho, center_y), (255, 255, 255), 2)
                cv2.line(color_image, (center_x, center_y - cruz_tamanho),
                         (center_x, center_y + cruz_tamanho), (255, 255, 255), 2)

            # Filtrar valores válidos (> 0)
            regiao_valida = regiao_depth[regiao_depth > 0]

            # Calcular distância mediana (mais robusta que média)
            if len(regiao_valida) > 10 and (caixa_detectada or True):  # Garantir mínimo de pontos válidos
                distancia_pixels = np.median(regiao_valida)
                distancia_metros = distancia_pixels * depth_scale

                # Calcular altura do conteúdo dentro da caixa
                altura_conteudo = ALTURA_CAMERA_CHAO - distancia_metros
                percentual_cheio = (altura_conteudo / ALTURA_CAIXA) * 100

                # Limitar percentual entre 0 e 100
                percentual_cheio = max(0, min(100, percentual_cheio))

                # --- LÓGICA DE DECISÃO BASEADA APENAS NA ALTURA ---
                if distancia_metros >= LIMITE_VAZIA:
                    # Distância grande = câmera vê o fundo
                    status = "VAZIA"
                    cor_status = (0, 0, 255)  # Vermelho
                    cor_regiao = (0, 0, 255)

                elif distancia_metros <= LIMITE_CHEIA:
                    # Distância pequena = objeto até a borda ou acima
                    status = "CHEIA"
                    cor_status = (0, 255, 0)  # Verde
                    cor_regiao = (0, 255, 0)

                else:
                    # Distância intermediária = parcialmente cheia
                    status = "PARCIAL"
                    cor_status = (0, 165, 255)  # Laranja
                    cor_regiao = (0, 165, 255)

                # Preparar textos informativos
                texto_status = f"STATUS: {status}"
                if caixa_detectada:
                    texto_distancia = f"Distancia: {distancia_metros:.3f}m | CAIXA DETECTADA"
                else:
                    texto_distancia = f"Distancia: {distancia_metros:.3f}m | Modo Centro"
                texto_altura = f"Altura conteudo: {altura_conteudo*100:.1f}cm"
                texto_percentual = f"Preenchimento: {percentual_cheio:.0f}%"
                texto_area = f"Area da caixa: {maior_area:.0f} px²" if caixa_detectada else ""

            else:
                # Medição inválida
                status = "SEM LEITURA"
                cor_status = (128, 128, 128)
                cor_regiao = (128, 128, 128)
                texto_status = "STATUS: SEM LEITURA"
                if caixa_detectada:
                    texto_distancia = "Caixa detectada | Aguardando medicao valida..."
                else:
                    texto_distancia = "Procurando caixa..."
                texto_altura = ""
                texto_percentual = ""
                texto_area = ""

            # --- DESENHAR VISUALIZAÇÃO ---

            # Desenhar região de medição
            cv2.rectangle(color_image, (x1, y1), (x2, y2), cor_regiao, 3)

            # Painel superior com informações
            cv2.rectangle(color_image, (0, 0), (w, 210), (0, 0, 0), -1)

            # Status grande
            cv2.putText(color_image, texto_status, (20, 50),
                       cv2.FONT_HERSHEY_SIMPLEX, 1.5, cor_status, 3)

            # Informações detalhadas
            y_offset = 90
            cv2.putText(color_image, texto_distancia, (20, y_offset),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            if texto_altura:
                cv2.putText(color_image, texto_altura, (20, y_offset + 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                cv2.putText(color_image, texto_percentual, (20, y_offset + 60),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, cor_status, 2)
                if texto_area:
                    cv2.putText(color_image, texto_area, (20, y_offset + 90),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 255, 255), 1)

            # Rodapé com instruções
            cv2.rectangle(color_image, (0, h - 40), (w, h), (0, 0, 0), -1)
            cv2.putText(color_image, "Pressione 'q' para sair", (20, h - 15),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

            # Exibir informações de configuração no canto direito
            info_config = [
                f"Camera: {ALTURA_CAMERA_CHAO*100:.0f}cm",
                f"Caixa: {ALTURA_CAIXA*100:.0f}cm",
                f"Fundo: {DISTANCIA_FUNDO_VAZIO:.3f}m",
                f"Borda: {DISTANCIA_BORDA_CHEIA:.3f}m"
            ]

            for i, info in enumerate(info_config):
                cv2.putText(color_image, info, (w - 200, 30 + i*25),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 180), 1)

            # Mostrar imagem
            cv2.imshow('Detector de Nivel da Caixa', color_image)

            # Criar mapa de calor da profundidade
            depth_colormap = cv2.applyColorMap(
                cv2.convertScaleAbs(depth_image, alpha=0.05),
                cv2.COLORMAP_JET
            )

            # Desenhar região no mapa de calor
            cv2.rectangle(depth_colormap, (x1, y1), (x2, y2), (255, 255, 255), 2)
            cv2.imshow('Mapa de Profundidade', depth_colormap)

            # Imprimir no console
            if status != "SEM LEITURA":
                if 'distancia_metros' in locals() and 'altura_conteudo' in locals() and 'percentual_cheio' in locals():
                    print(f"\r{status:8} | Dist: {distancia_metros:.3f}m | "
                          f"Alt: {altura_conteudo*100:5.1f}cm | {percentual_cheio:3.0f}%",
                          end='', flush=True)

            # Sair com 'q'
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    finally:
        print("\n\n" + "="*70)
        print("Encerrando sistema...")
        pipeline.stop()
        cv2.destroyAllWindows()
        print("✓ Câmera desligada. Sistema encerrado.")
        print("="*70)


if __name__ == "__main__":
    verificar_caixa_por_altura()

