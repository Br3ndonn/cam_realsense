import pyrealsense2 as rs
import mediapipe as mp
import cv2
import numpy as np

# --- Configuração do MediaPipe Pose ---
mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils
pose = mp_pose.Pose(
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)

# --- Configuração da RealSense ---
pipeline = rs.pipeline()
config = rs.config()

# Habilitar streams (Color e Depth)
# Ajuste a resolução (640x480) e FPS (30) conforme o modelo da sua câmera (D435, D455, etc)
config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)

# Iniciar o streaming
profile = pipeline.start(config)

# Criar objeto para alinhar profundidade com cor
# Isso garante que o pixel (x,y) na imagem de cor corresponda ao mesmo (x,y) na profundidade
align_to = rs.stream.color
align = rs.align(align_to)

try:
    while True:
        # 1. Aguardar pares de frames (cor e profundidade)
        frames = pipeline.wait_for_frames()

        # 2. Alinhar os frames
        aligned_frames = align.process(frames)
        aligned_depth_frame = aligned_frames.get_depth_frame()
        color_frame = aligned_frames.get_color_frame()

        if not aligned_depth_frame or not color_frame:
            continue

        # 3. Converter imagens para arrays numpy
        depth_image = np.asanyarray(aligned_depth_frame.get_data())
        color_image = np.asanyarray(color_frame.get_data())

        # 4. Processamento com MediaPipe
        # Converter BGR para RGB para o MediaPipe
        image_rgb = cv2.cvtColor(color_image, cv2.COLOR_BGR2RGB)
        image_rgb.flags.writeable = False

        results = pose.process(image_rgb)

        image_rgb.flags.writeable = True

        # 5. Desenhar landmarks (esqueleto) na imagem original
        if results.pose_landmarks:
            mp_drawing.draw_landmarks(
                color_image,
                results.pose_landmarks,
                mp_pose.POSE_CONNECTIONS,
                mp_drawing.DrawingSpec(color=(0, 255, 0), thickness=2, circle_radius=2),
                mp_drawing.DrawingSpec(color=(0, 0, 255), thickness=2, circle_radius=2)
            )

            # Exemplo: Pegar a distância (Profundidade) do Nariz
            # O MediaPipe retorna coordenadas normalizadas (0.0 a 1.0)
            nose = results.pose_landmarks.landmark[mp_pose.PoseLandmark.NOSE]
            h, w, _ = color_image.shape
            cx, cy = int(nose.x * w), int(nose.y * h)

            # Verificar se o ponto está dentro dos limites da imagem
            if 0 <= cx < w and 0 <= cy < h:
                # Ler a distância em metros no ponto central do nariz
                dist = aligned_depth_frame.get_distance(cx, cy)

                # Exibir texto com a distância
                cv2.putText(color_image, f"Nariz: {dist:.2f}m", (cx, cy - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
                cv2.circle(color_image, (cx, cy), 5, (255, 0, 0), -1)

        # 6. Exibir o resultado
        cv2.imshow('RealSense Body Tracking', color_image)

        # Pressione 'q' ou 'ESC' para sair
        key = cv2.waitKey(1)
        if key & 0xFF == ord('q') or key == 27:
            break

finally:
    # Parar o streaming e fechar janelas
    pipeline.stop()
    cv2.destroyAllWindows()