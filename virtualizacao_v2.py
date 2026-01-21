import pyrealsense2 as rs
import numpy as np
import open3d as o3d
import cv2
import datetime
from ultralytics import YOLO


def scan_segmented_object():
    # --- 1. Inicializa Modelo de Segmentação ---
    print("Carregando modelo de Segmentação (YOLOv8-seg)...")
    # O sufixo '-seg' indica que ele gera máscaras, não apenas caixas
    model = YOLO("yolov8n-seg.pt")

    pipeline = rs.pipeline()
    config = rs.config()

    # Configuração de stream
    config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
    config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)

    print("--- Iniciando Scanner com Recorte ---")
    print("Aponte para o objeto. A máscara colorida indica o recorte exato.")
    profile = pipeline.start(config)

    # Sensores e escala
    depth_sensor = profile.get_device().first_depth_sensor()
    depth_scale = depth_sensor.get_depth_scale()

    align_to = rs.stream.color
    align = rs.align(align_to)

    try:
        while True:
            # Captura de frames
            frames = pipeline.wait_for_frames()
            aligned_frames = align.process(frames)

            aligned_depth_frame = aligned_frames.get_depth_frame()
            color_frame = aligned_frames.get_color_frame()

            if not aligned_depth_frame or not color_frame:
                continue

            # Conversão para numpy
            depth_image = np.asanyarray(aligned_depth_frame.get_data())
            color_image = np.asanyarray(color_frame.get_data())

            # Imagem para exibição
            display_image = color_image.copy()

            # --- 2. Inferência (Detectar e Segmentar) ---
            # retina_masks=True garante que a máscara venha na resolução original da imagem
            results = model(color_image, stream=True, verbose=False, retina_masks=True)

            target_object = None
            min_dist_detected = float('inf')

            for r in results:
                # Verifica se detectou algo e se tem máscaras
                if r.boxes and r.masks:
                    for i, box in enumerate(r.boxes):
                        # Dados da caixa
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        label = model.names[int(box.cls[0])]
                        conf = float(box.conf[0])

                        if conf < 0.5: continue

                        # --- Processamento da Máscara ---
                        # A máscara vem como um array de pontos (polígono) ou bitmap
                        # Aqui acessamos o bitmap direto
                        mask_raw = r.masks.data[i].cpu().numpy()

                        # A máscara pode vir em tamanho diferente, redimensionamos para 640x480
                        # (A YOLO as vezes processa em tamanho menor para ser rápida)
                        if mask_raw.shape[:2] != (480, 640):
                            mask_resized = cv2.resize(mask_raw, (640, 480))
                        else:
                            mask_resized = mask_raw

                        # Criar máscara binária (0 ou 255)
                        binary_mask = (mask_resized > 0.5).astype(np.uint8) * 255

                        # --- Calcular Distância ---
                        # Usamos a máscara para pegar SOMENTE a profundidade do objeto
                        # Isso ignora o fundo que estaria dentro da "caixa" mas fora do objeto
                        masked_depth = depth_image.copy()
                        masked_depth[binary_mask == 0] = 0  # Zera tudo fora da máscara

                        valid_pixels = masked_depth[masked_depth > 0]
                        if len(valid_pixels) == 0: continue

                        # Mediana da profundidade (em metros)
                        dist_meters = np.median(valid_pixels) * depth_scale

                        # Lógica do "Mais Próximo"
                        color_contour = (0, 255, 255)  # Amarelo
                        if dist_meters < min_dist_detected:
                            min_dist_detected = dist_meters
                            target_object = {
                                "label": label,
                                "dist": dist_meters,
                                "mask": binary_mask  # Guardamos a máscara exata
                            }
                            color_contour = (0, 255, 0)  # Verde (Target)

                        # Desenhar contorno do objeto na tela (Overlay)
                        contours, _ = cv2.findContours(binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                        cv2.drawContours(display_image, contours, -1, color_contour, 2)

                        # Texto
                        cv2.putText(display_image, f"{label} {dist_meters:.2f}m", (x1, y1 - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color_contour, 2)

            # Mostra preview
            cv2.imshow('Scanner com Recorte IA', display_image)

            # --- 3. Comandos ---
            key = cv2.waitKey(1)
            if key & 0xFF == ord('q') or key == 27:
                break

            elif key & 0xFF == ord('s'):
                if target_object is None:
                    print("Nenhum objeto detectado.")
                    continue

                print(f"Salvando recorte perfeito de: {target_object['label']}...")

                # --- Geração da Nuvem de Pontos "Cirúrgica" ---

                # 1. Aplicar máscara na COR (fundo vira preto)
                color_rgb = color_image[:, :, ::-1].copy()  # BGR -> RGB
                final_color = cv2.bitwise_and(color_rgb, color_rgb, mask=target_object['mask'])

                # 2. Aplicar máscara na PROFUNDIDADE (fundo vira 0)
                final_depth = depth_image.copy()
                final_depth[target_object['mask'] == 0] = 0

                # 3. Criar Open3D Images
                o3d_color = o3d.geometry.Image(final_color)
                o3d_depth = o3d.geometry.Image(final_depth)

                # Intrínsecos
                intrinsics = color_frame.profile.as_video_stream_profile().intrinsics
                o3d_intrinsics = o3d.camera.PinholeCameraIntrinsic(
                    intrinsics.width, intrinsics.height,
                    intrinsics.fx, intrinsics.fy,
                    intrinsics.ppx, intrinsics.ppy
                )

                # Criar RGBD
                # Como já mascaramos tudo, o depth_trunc pode ser bem alto,
                # pois o que é fundo já virou 0 na máscara.
                rgbd_image = o3d.geometry.RGBDImage.create_from_color_and_depth(
                    o3d_color,
                    o3d_depth,
                    depth_scale=1.0 / depth_scale,
                    depth_trunc=10.0,
                    convert_rgb_to_intensity=False
                )

                pcd = o3d.geometry.PointCloud.create_from_rgbd_image(
                    rgbd_image,
                    o3d_intrinsics
                )

                # Orientação
                pcd.transform([[1, 0, 0, 0], [0, -1, 0, 0], [0, 0, -1, 0], [0, 0, 0, 1]])

                # Salvar
                timestamp = datetime.datetime.now().strftime("%H%M%S")
                filename = f"recorte_{target_object['label']}_{timestamp}.ply"
                o3d.io.write_point_cloud(filename, pcd)

                print(f"Salvo: {filename}")
                cv2.putText(display_image, "SALVO!", (200, 240), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 3)
                cv2.imshow('Scanner com Recorte IA', display_image)
                cv2.waitKey(500)

    finally:
        pipeline.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    scan_segmented_object()