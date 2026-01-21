import pyrealsense2 as rs
import numpy as np
import open3d as o3d
import cv2
import datetime
from ultralytics import YOLO


def scan_recognized_object():
    # --- 1. Inicializa YOLO e RealSense ---
    print("Carregando modelo de IA (YOLOv8)...")
    # Usa o modelo nano (mais leve para CPU)
    model = YOLO("yolov8n.pt")

    pipeline = rs.pipeline()
    config = rs.config()

    # 640x480 equilibra bem precisão da IA e performance
    config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
    config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)

    print("--- Iniciando Câmera ---")
    profile = pipeline.start(config)

    # Escala de profundidade
    depth_sensor = profile.get_device().first_depth_sensor()
    depth_scale = depth_sensor.get_depth_scale()

    align_to = rs.stream.color
    align = rs.align(align_to)

    try:
        while True:
            frames = pipeline.wait_for_frames()
            aligned_frames = align.process(frames)

            aligned_depth_frame = aligned_frames.get_depth_frame()
            color_frame = aligned_frames.get_color_frame()

            if not aligned_depth_frame or not color_frame:
                continue

            # Imagens para processamento
            depth_image = np.asanyarray(aligned_depth_frame.get_data())
            color_image = np.asanyarray(color_frame.get_data())

            # Cópia para desenhar na tela (display)
            display_image = color_image.copy()

            # --- 2. Detecção de Objetos com YOLO ---
            # stream=True torna mais rápido para vídeo; verbose=False limpa o terminal
            results = model(color_image, stream=True, verbose=False)

            target_object = None  # Vai guardar os dados do objeto escolhido para scan
            min_dist_detected = float('inf')

            # Processar resultados da IA
            for r in results:
                boxes = r.boxes
                for box in boxes:
                    # Coordenadas da caixa (Bounding Box)
                    x1, y1, x2, y2 = map(int, box.xyxy[0])

                    # Nome da classe (ex: cup, bottle, person)
                    cls_id = int(box.cls[0])
                    label = model.names[cls_id]
                    confidence = float(box.conf[0])

                    # Filtra confiança baixa
                    if confidence < 0.5: continue

                    # --- 3. Calcular distância do objeto específico ---
                    # Recorta a profundidade apenas na área da caixa detectada
                    object_depth_roi = depth_image[y1:y2, x1:x2]

                    if object_depth_roi.size == 0: continue

                    # Converte para metros
                    dist_meters = object_depth_roi * depth_scale

                    # Pega a mediana (ignora zeros/ruído) dos pontos > 0
                    valid_pixels = dist_meters[dist_meters > 0]
                    if len(valid_pixels) == 0: continue

                    # Distância estimada do objeto
                    obj_dist = np.median(valid_pixels)

                    # Desenhar na tela
                    # Se este for o objeto mais próximo até agora, marcamos ele como ALVO
                    color_box = (0, 255, 255)  # Amarelo padrão
                    thickness = 2

                    if obj_dist < min_dist_detected:
                        min_dist_detected = obj_dist
                        target_object = {
                            "label": label,
                            "box": (x1, y1, x2, y2),
                            "dist": obj_dist,
                            "roi_depth": object_depth_roi
                        }
                        color_box = (0, 255, 0)  # VERDE para o alvo principal (mais próximo)
                        thickness = 3

                    cv2.rectangle(display_image, (x1, y1), (x2, y2), color_box, thickness)
                    cv2.putText(display_image, f"{label} {obj_dist:.2f}m", (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color_box, 2)

            # Instruções na tela
            cv2.imshow('YOLO + RealSense Scanner', display_image)

            # --- 4. Comandos ---
            key = cv2.waitKey(1)

            if key & 0xFF == ord('q') or key == 27:
                break

            elif key & 0xFF == ord('s'):
                if target_object is None:
                    print("Nenhum objeto reconhecido para escanear!")
                    continue

                print(f"Escaneando: {target_object['label']} a {target_object['dist']:.2f}m")

                # --- Criação da Nuvem de Pontos Filtrada ---

                # Definir corte: Objeto + 50cm de margem traseira
                # Isso remove a parede atrás do objeto
                clipping_distance = target_object['dist'] + 0.5

                intrinsics = color_frame.profile.as_video_stream_profile().intrinsics
                o3d_intrinsics = o3d.camera.PinholeCameraIntrinsic(
                    intrinsics.width, intrinsics.height,
                    intrinsics.fx, intrinsics.fy,
                    intrinsics.ppx, intrinsics.ppy
                )

                # Converter cor para RGB
                color_rgb = color_image[:, :, ::-1].copy()

                # MÁSCARA INTELIGENTE:
                # Vamos zerar (preto) tudo na imagem que NÃO for o objeto alvo (bounding box)
                # Assim a nuvem de pontos só terá pixels daquele objeto.
                mask = np.zeros_like(color_rgb)
                tx1, ty1, tx2, ty2 = target_object['box']
                mask[ty1:ty2, tx1:tx2] = color_rgb[ty1:ty2, tx1:tx2]

                # Criar imagens Open3D usando a máscara em vez da imagem cheia
                o3d_color = o3d.geometry.Image(mask)
                o3d_depth = o3d.geometry.Image(depth_image)

                rgbd_image = o3d.geometry.RGBDImage.create_from_color_and_depth(
                    o3d_color,
                    o3d_depth,
                    depth_scale=1.0 / depth_scale,
                    depth_trunc=clipping_distance,
                    convert_rgb_to_intensity=False
                )

                pcd = o3d.geometry.PointCloud.create_from_rgbd_image(
                    rgbd_image,
                    o3d_intrinsics
                )

                pcd.transform([[1, 0, 0, 0], [0, -1, 0, 0], [0, 0, -1, 0], [0, 0, 0, 1]])

                # Nome do arquivo inclui o nome do objeto reconhecido
                timestamp = datetime.datetime.now().strftime("%H%M%S")
                filename = f"scan_{target_object['label']}_{timestamp}.ply"
                o3d.io.write_point_cloud(filename, pcd)

                print(f"Arquivo salvo: {filename}")

                # Feedback visual
                cv2.putText(display_image, "SALVO!", (320, 240), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 255), 3)
                cv2.imshow('YOLO + RealSense Scanner', display_image)
                cv2.waitKey(500)

    finally:
        pipeline.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    scan_recognized_object()