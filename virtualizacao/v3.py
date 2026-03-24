import datetime

import cv2
import numpy as np
from ultralytics import YOLO


WINDOW_NAME = "Scanner com Recorte IA - Webcam PCYes"


def _open_camera(camera_index):
    backend_candidates = [
        ("DirectShow", cv2.CAP_DSHOW),
        ("Media Foundation", cv2.CAP_MSMF),
        ("Default", cv2.CAP_ANY),
    ]

    last_error = None

    for backend_name, backend_flag in backend_candidates:
        try:
            cap = cv2.VideoCapture(camera_index, backend_flag)
        except Exception as exc:
            last_error = exc
            print(f"Aviso: backend {backend_name} falhou ao abrir a camera: {exc}")
            continue

        if cap.isOpened():
            print(f"Camera aberta com backend {backend_name} (indice {camera_index}).")
            return cap

        cap.release()

    if last_error is not None:
        print(f"Ultimo erro ao tentar abrir a camera: {last_error}")

    print(
        "Erro: nao foi possivel abrir a camera no indice "
        f"{camera_index}. Teste outro indice, por exemplo 1 ou 2."
    )
    return None


def scan_segmented_object_pcyes(camera_index=0):
    print("Carregando modelo de segmentacao (YOLOv8-seg)...")
    model = YOLO("yolov8n-seg.pt")

    cap = _open_camera(camera_index)
    if cap is None:
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)

    print("--- Iniciando scanner com webcam PCYes ---")
    print("Aponte para o objeto. Pressione 's' para salvar o recorte.")
    print("Pressione 'q' ou ESC para sair.")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Falha ao capturar frame da camera.")
                continue

            color_image = frame.copy()
            display_image = color_image.copy()

            target_object = None
            best_area = 0

            results = model(color_image, stream=True, verbose=False, retina_masks=True)

            for result in results:
                if result.boxes is None or result.masks is None:
                    continue

                for i, box in enumerate(result.boxes):
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    label = model.names[int(box.cls[0])]
                    conf = float(box.conf[0])

                    if conf < 0.5:
                        continue

                    mask_raw = result.masks.data[i].cpu().numpy()

                    h, w = color_image.shape[:2]
                    if mask_raw.shape[:2] != (h, w):
                        mask_resized = cv2.resize(mask_raw, (w, h))
                    else:
                        mask_resized = mask_raw

                    binary_mask = (mask_resized > 0.5).astype(np.uint8) * 255
                    area = cv2.countNonZero(binary_mask)

                    color_contour = (0, 255, 255)
                    if area > best_area:
                        best_area = area
                        target_object = {
                            "label": label,
                            "conf": conf,
                            "mask": binary_mask,
                            "bbox": (x1, y1, x2, y2),
                            "area": area,
                        }
                        color_contour = (0, 255, 0)

                    contours, _ = cv2.findContours(
                        binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
                    )
                    cv2.drawContours(display_image, contours, -1, color_contour, 2)
                    cv2.putText(
                        display_image,
                        f"{label} {conf:.2f}",
                        (x1, max(20, y1 - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        color_contour,
                        2,
                    )

            cv2.imshow(WINDOW_NAME, display_image)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break

            if key != ord("s"):
                continue

            if target_object is None:
                print("Nenhum objeto detectado.")
                continue

            print(f"Salvando recorte de: {target_object['label']}...")

            mask = target_object["mask"]
            segmented = cv2.bitwise_and(color_image, color_image, mask=mask)

            x1, y1, x2, y2 = target_object["bbox"]
            crop_bbox = color_image[y1:y2, x1:x2]

            ys, xs = np.where(mask > 0)
            if len(xs) == 0 or len(ys) == 0:
                print("Mascara vazia, nada para salvar.")
                continue

            x_min, x_max = xs.min(), xs.max()
            y_min, y_max = ys.min(), ys.max()
            crop_masked = segmented[y_min:y_max + 1, x_min:x_max + 1]
            crop_mask = mask[y_min:y_max + 1, x_min:x_max + 1]

            timestamp = datetime.datetime.now().strftime("%H%M%S")
            file_segmented = f"recorte_segmentado_{target_object['label']}_{timestamp}.png"
            file_mask = f"mascara_{target_object['label']}_{timestamp}.png"
            file_bbox = f"bbox_{target_object['label']}_{timestamp}.png"

            cv2.imwrite(file_segmented, crop_masked)
            cv2.imwrite(file_mask, crop_mask)
            cv2.imwrite(file_bbox, crop_bbox)

            print(f"Salvo: {file_segmented}")
            print(f"Salvo: {file_mask}")
            print(f"Salvo: {file_bbox}")

            preview = display_image.copy()
            cv2.putText(
                preview,
                "SALVO!",
                (200, 240),
                cv2.FONT_HERSHEY_SIMPLEX,
                2,
                (255, 255, 255),
                3,
            )
            cv2.imshow(WINDOW_NAME, preview)
            cv2.waitKey(500)

    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    scan_segmented_object_pcyes(camera_index=0)
