import pyrealsense2 as rs
import mediapipe as mp
import cv2
import numpy as np
import csv
import time
import os
from collections import deque

# --- CONFIGURAÇÕES DE ALTA PERFORMANCE ---
ARQUIVO_SAIDA = 'movimento_rapido.csv'
GRAVAR_DADOS = True
SHOW_IMAGE = True  # Mude para False para MAXIMA velocidade (sem janela)
MODEL_COMPLEXITY = 0  # 0=Lite (Rápido), 1=Full (Médio), 2=Heavy (Preciso)
TARGET_FPS = 60  # Tentar 60 FPS (Verifique se sua USB 3.0 suporta)

# --- Inicialização do MediaPipe (Otimizado) ---
mp_pose = mp.solutions.pose
# Note: static_image_mode=False deixa o tracking mais rápido pois usa info do frame anterior
pose = mp_pose.Pose(
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5,
    model_complexity=MODEL_COMPLEXITY,
    static_image_mode=False
)

# --- Inicialização da RealSense ---
print(f"Iniciando RealSense a {TARGET_FPS} FPS...")
pipeline = rs.pipeline()
config = rs.config()

# Resolução 640x480 é ideal para 60FPS na maioria das portas USB 3.0
# Se tiver problemas, tente 424x240
config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, TARGET_FPS)
config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, TARGET_FPS)

# Iniciar
profile = pipeline.start(config)

# --- AJUSTE DE EXPOSIÇÃO (Crucial para movimento rápido) ---
# Obtém o sensor de profundidade e cor para desligar auto-exposure se necessário
depth_sensor = profile.get_device().first_depth_sensor()
color_sensor = profile.get_device().query_sensors()[1]

# Dica: Para movimento MUITO rápido, desligue a auto-exposição e fixe um valor baixo
# color_sensor.set_option(rs.option.enable_auto_exposure, 0)
# color_sensor.set_option(rs.option.exposure, 100) # Valor baixo reduz motion blur

align_to = rs.stream.color
align = rs.align(align_to)

# Buffer para escrita em lote (melhora I/O)
data_buffer = []
BUFFER_SIZE = 100  # Escreve no disco a cada 100 frames

# Prepara CSV
if GRAVAR_DADOS:
    with open(ARQUIVO_SAIDA, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Timestamp', 'FPS_Atual', 'Landmark', 'X', 'Y', 'Z_meters'])

print("Rastreamento iniciado! Pressione 'q' na janela (ou Ctrl+C no terminal) para parar.")

start_time = time.time()
frame_count = 0
fps_start_time = time.time()
current_fps = 0

try:
    while True:
        # 1. Captura
        frames = pipeline.wait_for_frames()
        aligned_frames = align.process(frames)

        depth_frame = aligned_frames.get_depth_frame()
        color_frame = aligned_frames.get_color_frame()

        if not depth_frame or not color_frame:
            continue

        # Processamento de imagem (Somente o necessário)
        # Usamos array numpy diretamente, sem cópias desnecessárias
        color_image = np.asanyarray(color_frame.get_data())

        # O MediaPipe exige RGB. A conversão consome um pouco de CPU.
        # flag writeable=False é uma pequena otimização do MediaPipe
        image_rgb = cv2.cvtColor(color_image, cv2.COLOR_BGR2RGB)
        image_rgb.flags.writeable = False

        # --- INFERÊNCIA (A parte pesada) ---
        results = pose.process(image_rgb)

        # Calculo de FPS Real
        frame_count += 1
        if frame_count % 30 == 0:
            end_time = time.time()
            current_fps = 30 / (end_time - fps_start_time)
            fps_start_time = end_time
            if not SHOW_IMAGE:
                print(f"FPS Atual: {current_fps:.2f}")

        # --- EXTRAÇÃO DE DADOS ---
        if results.pose_landmarks and GRAVAR_DADOS:
            h, w, _ = color_image.shape
            timestamp = time.time() - start_time

            # Capturando apenas pontos essenciais para velocidade (ex: pulsos e nariz)
            # Adicione mais se precisar, mas quanto menos pontos, menor o overhead de loop
            pontos_chave = [
                mp_pose.PoseLandmark.NOSE,
                mp_pose.PoseLandmark.RIGHT_WRIST,
                mp_pose.PoseLandmark.LEFT_WRIST
            ]

            for lm_id in pontos_chave:
                lm = results.pose_landmarks.landmark[lm_id]
                cx, cy = int(lm.x * w), int(lm.y * h)

                # Leitura de profundidade rápida
                if 0 <= cx < w and 0 <= cy < h:
                    dist = depth_frame.get_distance(cx, cy)
                    if dist > 0:
                        name = mp_pose.PoseLandmark(lm_id).name
                        # Adiciona ao buffer em memória
                        data_buffer.append([
                            f"{timestamp:.4f}",
                            f"{current_fps:.1f}",
                            name, cx, cy, f"{dist:.3f}"
                        ])

        # --- DESCARGA DO BUFFER (Batch Write) ---
        if len(data_buffer) >= BUFFER_SIZE:
            with open(ARQUIVO_SAIDA, mode='a', newline='') as f:
                writer = csv.writer(f)
                writer.writerows(data_buffer)
            data_buffer = []  # Limpa buffer

        # --- VISUALIZAÇÃO (Opcional) ---
        if SHOW_IMAGE:
            # Desenhar é lento. Só desenhamos se necessário.
            if results.pose_landmarks:
                mp.solutions.drawing_utils.draw_landmarks(
                    color_image, results.pose_landmarks, mp_pose.POSE_CONNECTIONS
                )

            cv2.putText(color_image, f"FPS: {current_fps:.1f}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

            cv2.imshow('High Speed Tracking', color_image)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

except KeyboardInterrupt:
    print("Interrompido pelo usuário.")

finally:
    # Gravar o restante do buffer antes de sair
    if data_buffer:
        print("Salvando dados restantes...")
        with open(ARQUIVO_SAIDA, mode='a', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(data_buffer)

    pipeline.stop()
    if SHOW_IMAGE:
        cv2.destroyAllWindows()
    print(f"Finalizado. Dados salvos em {ARQUIVO_SAIDA}")