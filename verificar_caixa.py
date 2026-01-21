import pyrealsense2 as rs
import numpy as np
import cv2


def rastrear_cacamba():
    # --- CONFIGURAÇÕES ---
    # Área mínima para considerar que achou uma caçamba (evita detectar caixas pequenas)
    AREA_MINIMA = 10000

    # Altura (em metros) onde consideramos que a caçamba começa
    # Tudo que estiver acima dessa altura (mais perto da camera) será considerado carga
    ALTURA_BORDA_CAMINHAO = 3.5  # Exemplo: Borda está a 3.5m da câmera

    # --- INICIALIZAÇÃO ---
    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
    config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)

    print("[INFO] Iniciando rastreamento de geometria...")
    profile = pipeline.start(config)
    depth_scale = profile.get_device().first_depth_sensor().get_depth_scale()

    try:
        while True:
            frames = pipeline.wait_for_frames()
            depth_frame = frames.get_depth_frame()
            color_frame = frames.get_color_frame()

            if not depth_frame or not color_frame:
                continue

            # Converter para Numpy
            depth_image = np.asanyarray(depth_frame.get_data())
            color_image = np.asanyarray(color_frame.get_data())

            # --- PROCESSAMENTO DE VISÃO COMPUTACIONAL ---

            # 1. Converter para Cinza e aplicar Blur (suavizar ruído)
            gray = cv2.cvtColor(color_image, cv2.COLOR_BGR2GRAY)
            blur = cv2.GaussianBlur(gray, (5, 5), 0)

            # 2. Detectar Bordas (Canny Edge Detection)
            # Os valores 50 e 150 são limiares de contraste. Ajuste conforme a iluminação.
            edges = cv2.Canny(blur, 50, 150)

            # 3. Encontrar Contornos nas bordas detectadas
            contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

            melhor_retangulo = None
            maior_area = 0

            for cnt in contours:
                area = cv2.contourArea(cnt)

                # Ignorar contornos pequenos (ruído)
                if area > AREA_MINIMA:
                    # 4. Simplificar a forma geométrica (Aproximação Poligonal)
                    perimetro = cv2.arcLength(cnt, True)
                    approx = cv2.approxPolyDP(cnt, 0.02 * perimetro, True)

                    # Se a forma tem 4 pontas, é provavelmente um retângulo (caçamba)
                    if len(approx) == 4:
                        if area > maior_area:
                            maior_area = area
                            melhor_retangulo = approx

            # --- LÓGICA DE PROFUNDIDADE DENTRO DO RETÂNGULO ---
            status = "PROCURANDO CAÇAMBA..."
            distancia_media = 0.0

            if melhor_retangulo is not None:
                # Desenhar o retângulo detectado na imagem
                cv2.drawContours(color_image, [melhor_retangulo], -1, (0, 255, 255), 3)

                # CRIAR UMA MÁSCARA: Queremos analisar APENAS o que está dentro do retângulo
                mascara = np.zeros(depth_image.shape, dtype=np.uint8)
                cv2.drawContours(mascara, [melhor_retangulo], -1, 255, -1)  # Preenche de branco

                # Pegar os dados de profundidade usando a máscara
                # mean retorna (media, 0, 0, 0), pegamos o índice [0]
                media_depth_value = cv2.mean(depth_image, mask=mascara)[0]
                distancia_media = media_depth_value * depth_scale

                # Decisão
                if distancia_media > 0:
                    # Se a distância média for MENOR que a altura da borda, tem carga dentro
                    # (Lembre-se: Menor distância = Mais perto da câmera = Mais alto)
                    if distancia_media < ALTURA_BORDA_CAMINHAO:
                        status = "CAMINHAO CHEIO"
                        cor_status = (0, 255, 0)
                    else:
                        status = "CAMINHAO VAZIO"
                        cor_status = (0, 0, 255)

                    # Colocar texto perto do retângulo
                    x, y, w, h = cv2.boundingRect(melhor_retangulo)
                    cv2.putText(color_image, f"{distancia_media:.2f}m", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                                cor_status, 2)

            else:
                cor_status = (0, 0, 0)

            # --- VISUALIZAÇÃO ---
            cv2.putText(color_image, f"STATUS: {status}", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, cor_status, 2)

            # Mostra também a visão das bordas para você entender o que o computador vê
            cv2.imshow('Detector de Bordas (Debug)', edges)
            cv2.imshow('Monitoramento de Carga', color_image)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    finally:
        pipeline.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    rastrear_cacamba()