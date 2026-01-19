import pyrealsense2 as rs
import numpy as np
import cv2


def monitoramento_calibravel():
    # --- CONFIGURAÇÕES ---
    # Margem de segurança: Quanto de altura a carga precisa ter para ser detectada?
    # Ex: 0.5m significa que só avisa que está cheio se a carga subir 50cm do fundo.
    MARGEM_SEGURANCA = 0.50  # Metros
    TAMANHO_ROI = 200  # Tamanho do quadrado central (pixels)

    # Variáveis de Estado
    distancia_fundo_vazio = 0.0
    limite_deteccao = 0.0
    sistema_calibrado = False

    # --- INICIALIZAÇÃO ---
    print("[INFO] Iniciando câmera...")
    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
    config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)

    try:
        profile = pipeline.start(config)
    except Exception as e:
        print(f"Erro ao abrir câmera: {e}")
        return

    depth_scale = profile.get_device().first_depth_sensor().get_depth_scale()

    print("--- INSTRUÇÕES ---")
    print("1. Aponte para o caminhão VAZIO.")
    print("2. Pressione a tecla 'c' para CALIBRAR o fundo.")
    print("3. O sistema definirá o limite automaticamente.")
    print("4. Pressione 'q' para sair.")

    try:
        while True:
            frames = pipeline.wait_for_frames()
            depth_frame = frames.get_depth_frame()
            color_frame = frames.get_color_frame()

            if not depth_frame or not color_frame:
                continue

            # Processamento de Imagem
            depth_image = np.asanyarray(depth_frame.get_data())
            color_image = np.asanyarray(color_frame.get_data())

            # Definir ROI (Centro)
            h, w = depth_image.shape
            cx, cy = int(w / 2), int(h / 2)
            x1, y1 = cx - int(TAMANHO_ROI / 2), cy - int(TAMANHO_ROI / 2)
            x2, y2 = cx + int(TAMANHO_ROI / 2), cy + int(TAMANHO_ROI / 2)

            roi = depth_image[y1:y2, x1:x2]

            # Calcular distância atual
            validos = roi[roi > 0]
            distancia_atual = 0.0

            if len(validos) > 0:
                distancia_atual = np.mean(validos) * depth_scale

            # --- LÓGICA DE DETECÇÃO ---
            status = "AGUARDANDO CALIBRACAO"
            cor_status = (0, 255, 255)  # Amarelo
            msg_extra = "Pressione 'c' com caminhao vazio"

            if sistema_calibrado:
                # Se a distância atual for MENOR que o limite, a carga subiu -> CHEIO
                if distancia_atual < limite_deteccao:
                    status = "CARGA DETECTADA (CHEIO)"
                    cor_status = (0, 255, 0)  # Verde
                else:
                    status = "CAMINHAO VAZIO"
                    cor_status = (0, 0, 255)  # Vermelho

                msg_extra = f"Ref: {distancia_fundo_vazio:.2f}m | Limite: {limite_deteccao:.2f}m"

            # --- VISUALIZAÇÃO ---
            cv2.rectangle(color_image, (x1, y1), (x2, y2), cor_status, 3)

            # Painel de Texto
            cv2.putText(color_image, f"Distancia Atual: {distancia_atual:.2f} m", (20, 40), cv2.FONT_HERSHEY_SIMPLEX,
                        0.8, (255, 255, 255), 2)
            cv2.putText(color_image, status, (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 1, cor_status, 3)
            cv2.putText(color_image, msg_extra, (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

            cv2.imshow('Monitoramento Inteligente', color_image)

            # --- CONTROLE DE TECLAS ---
            key = cv2.waitKey(1) & 0xFF

            if key == ord('q'):  # Sair
                break

            elif key == ord('c'):  # Calibrar
                if distancia_atual > 0:
                    distancia_fundo_vazio = distancia_atual
                    # O limite é a altura do vazio MENOS a margem (mais perto da câmera)
                    limite_deteccao = distancia_fundo_vazio - MARGEM_SEGURANCA
                    sistema_calibrado = True
                    print(f"[CALIBRADO] Fundo: {distancia_fundo_vazio:.2f}m | Trigger em: {limite_deteccao:.2f}m")
                else:
                    print("[ERRO] Leitura inválida, não foi possível calibrar.")

    finally:
        pipeline.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    monitoramento_calibravel()