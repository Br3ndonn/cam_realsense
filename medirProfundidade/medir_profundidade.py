import pyrealsense2 as rs
import numpy as np
import cv2

"""
Algoritmo para medir a altura da câmera RealSense até o chão.
Pressione 'ESC' para sair.
"""

# --- Configuração da RealSense ---
pipeline = rs.pipeline()
config = rs.config()

# Habilitar streams de profundidade e cor
config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)

print("Iniciando câmera RealSense...")
profile = pipeline.start(config)

# Obter escala de profundidade
depth_sensor = profile.get_device().first_depth_sensor()
depth_scale = depth_sensor.get_depth_scale()

# Alinhar frames de profundidade com cor
align_to = rs.stream.color
align = rs.align(align_to)

print("\n" + "="*60)
print("MEDIDOR DE ALTURA DA CÂMERA ATÉ O CHÃO")
print("="*60)
print("\nAponte a câmera para o chão diretamente abaixo dela.")
print("A medição será feita no centro da imagem (cruz verde).")
print("\nPressione 'ESC' para sair.\n")

try:
    while True:
        # Capturar frames
        frames = pipeline.wait_for_frames()
        aligned_frames = align.process(frames)

        aligned_depth_frame = aligned_frames.get_depth_frame()
        color_frame = aligned_frames.get_color_frame()

        if not aligned_depth_frame or not color_frame:
            continue

        # Converter para numpy arrays
        depth_image = np.asanyarray(aligned_depth_frame.get_data())
        color_image = np.asanyarray(color_frame.get_data())

        # Obter dimensões da imagem
        h, w = color_image.shape[:2]
        center_x, center_y = w // 2, h // 2

        # Medir distância no ponto central
        distancia_centro = aligned_depth_frame.get_distance(center_x, center_y)

        # Calcular média de uma região 10x10 pixels no centro para maior precisão
        regiao_size = 10
        x1 = max(0, center_x - regiao_size)
        x2 = min(w, center_x + regiao_size)
        y1 = max(0, center_y - regiao_size)
        y2 = min(h, center_y + regiao_size)

        regiao_depth = depth_image[y1:y2, x1:x2]
        # Filtrar valores zero (medições inválidas)
        regiao_valida = regiao_depth[regiao_depth > 0]

        if len(regiao_valida) > 0:
            distancia_media = np.mean(regiao_valida) * depth_scale
        else:
            distancia_media = 0.0

        # Desenhar cruz no centro da imagem
        cruz_tamanho = 20
        cor_cruz = (0, 255, 0)  # Verde
        cv2.line(color_image, (center_x - cruz_tamanho, center_y),
                 (center_x + cruz_tamanho, center_y), cor_cruz, 2)
        cv2.line(color_image, (center_x, center_y - cruz_tamanho),
                 (center_x, center_y + cruz_tamanho), cor_cruz, 2)

        # Desenhar retângulo da região de medição
        cv2.rectangle(color_image, (x1, y1), (x2, y2), (255, 255, 0), 2)

        # Exibir informações na imagem
        if distancia_media > 0:
            texto_altura = f"ALTURA DA CAMERA: {distancia_media:.3f} m ({distancia_media*100:.1f} cm)"
            cor_texto = (0, 255, 0)
        else:
            texto_altura = "SEM MEDICAO VALIDA"
            cor_texto = (0, 0, 255)

        # Fundo para o texto (melhor legibilidade)
        cv2.rectangle(color_image, (10, 10), (w - 10, 80), (0, 0, 0), -1)

        # Textos informativos
        cv2.putText(color_image, texto_altura, (20, 40),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, cor_texto, 2)
        cv2.putText(color_image, f"Centro: {distancia_centro:.3f} m", (20, 65),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        # Exibir a imagem
        cv2.imshow('Medidor de Altura da Camera', color_image)

        # Imprimir no console
        if distancia_media > 0:
            print(f"\rAltura: {distancia_media:.3f} m ({distancia_media*100:.1f} cm) | "
                  f"Centro: {distancia_centro:.3f} m", end='', flush=True)

        # Sair com ESC
        key = cv2.waitKey(1)
        if key == 27:  # ESC
            break

finally:
    print("\n\nEncerrando...")
    pipeline.stop()
    cv2.destroyAllWindows()
    print("Câmera desligada.")

