import pyrealsense2 as rs
import mediapipe as mp
import cv2
import numpy as np
import time
from collections import deque
import math


class PosturaAnalyzer:
    """
    Analisador avançado de postura corporal usando RealSense + MediaPipe

    Funcionalidades:
    - Detecção de má postura (costas curvadas)
    - Análise de simetria corporal
    - Detecção de quedas
    - Rastreamento de velocidade de movimentos
    - Contador de repetições (exercícios)
    - Alertas visuais e sonoros
    - Estatísticas em tempo real
    """

    def __init__(self):
        # Configuração MediaPipe
        self.mp_pose = mp.solutions.pose
        self.mp_drawing = mp.solutions.drawing_utils
        self.mp_drawing_styles = mp.solutions.drawing_styles

        self.pose = self.mp_pose.Pose(
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7,
            model_complexity=1
        )

        # Configuração RealSense
        self.pipeline = rs.pipeline()
        self.config = rs.config()
        self.config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
        self.config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)

        # Alinhamento
        self.align = rs.align(rs.stream.color)

        # Histórico para análise temporal
        self.historico_ombros = deque(maxlen=30)
        self.historico_quadril = deque(maxlen=30)
        self.historico_velocidade = deque(maxlen=10)

        # Contador de repetições
        self.contador_flexoes = 0
        self.estado_flexao = "UP"  # UP ou DOWN

        # Alertas
        self.alerta_postura = False
        self.tempo_alerta_postura = 0
        self.alerta_queda = False

        # Estatísticas
        self.tempo_inicio = time.time()
        self.frame_count = 0
        self.tempo_sentado = 0
        self.tempo_em_pe = 0
        self.ultima_posicao = None

    def calcular_angulo(self, a, b, c):
        """
        Calcula o ângulo entre três pontos (em graus)
        a, b, c são tuplas (x, y)
        b é o vértice do ângulo
        """
        a = np.array(a)
        b = np.array(b)
        c = np.array(c)

        ba = a - b
        bc = c - b

        cosine_angle = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-6)
        angle = np.arccos(np.clip(cosine_angle, -1.0, 1.0))

        return np.degrees(angle)

    def calcular_distancia(self, p1, p2):
        """Distância euclidiana entre dois pontos"""
        return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

    def analisar_postura(self, landmarks, h, w):
        """
        Analisa a postura do corpo
        Retorna: dict com informações da análise
        """
        resultado = {
            'postura_boa': True,
            'simetria_ombros': 0,
            'inclinacao_costas': 0,
            'alertas': []
        }

        try:
            # Pontos-chave
            ombro_esq = landmarks[self.mp_pose.PoseLandmark.LEFT_SHOULDER.value]
            ombro_dir = landmarks[self.mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
            quadril_esq = landmarks[self.mp_pose.PoseLandmark.LEFT_HIP.value]
            quadril_dir = landmarks[self.mp_pose.PoseLandmark.RIGHT_HIP.value]
            nariz = landmarks[self.mp_pose.PoseLandmark.NOSE.value]

            # Converter para coordenadas de pixel
            ombro_esq_px = (int(ombro_esq.x * w), int(ombro_esq.y * h))
            ombro_dir_px = (int(ombro_dir.x * w), int(ombro_dir.y * h))
            quadril_esq_px = (int(quadril_esq.x * w), int(quadril_esq.y * h))
            quadril_dir_px = (int(quadril_dir.x * w), int(quadril_dir.y * h))
            nariz_px = (int(nariz.x * w), int(nariz.y * h))

            # 1. ANÁLISE DE SIMETRIA DOS OMBROS
            dif_altura_ombros = abs(ombro_esq_px[1] - ombro_dir_px[1])
            resultado['simetria_ombros'] = dif_altura_ombros

            if dif_altura_ombros > 30:  # Mais de 30 pixels de diferença
                resultado['postura_boa'] = False
                resultado['alertas'].append('Ombros desalinhados')

            # 2. ANÁLISE DE INCLINAÇÃO DAS COSTAS
            # Calcular centro dos ombros e centro do quadril
            centro_ombros = (
                (ombro_esq_px[0] + ombro_dir_px[0]) // 2,
                (ombro_esq_px[1] + ombro_dir_px[1]) // 2
            )
            centro_quadril = (
                (quadril_esq_px[0] + quadril_dir_px[0]) // 2,
                (quadril_esq_px[1] + quadril_dir_px[1]) // 2
            )

            # Ângulo de inclinação
            if centro_quadril[1] != centro_ombros[1]:
                angulo_inclinacao = math.degrees(
                    math.atan2(
                        centro_ombros[0] - centro_quadril[0],
                        centro_quadril[1] - centro_ombros[1]
                    )
                )
                resultado['inclinacao_costas'] = abs(angulo_inclinacao)

                # Inclinação > 15 graus = má postura
                if abs(angulo_inclinacao) > 15:
                    resultado['postura_boa'] = False
                    resultado['alertas'].append('Costas inclinadas')

            # 3. ANÁLISE DE POSTURA CURVADA (cabeça muito à frente)
            # Se o nariz está muito à frente do centro dos ombros
            distancia_horizontal = abs(nariz_px[0] - centro_ombros[0])
            if distancia_horizontal > 60:  # pixels
                resultado['postura_boa'] = False
                resultado['alertas'].append('Cabeca muito a frente')

            # 4. DETECÇÃO DE QUEDA
            # Se o nariz está abaixo do quadril, pessoa pode ter caído
            if nariz_px[1] > centro_quadril[1] + 50:
                resultado['alertas'].append('⚠️ POSSIVEL QUEDA!')
                self.alerta_queda = True
            else:
                self.alerta_queda = False

        except Exception as e:
            print(f"Erro na análise de postura: {e}")

        return resultado

    def detectar_exercicio(self, landmarks, h, w):
        """
        Detecta e conta repetições de exercícios (ex: flexões)
        """
        try:
            # Pontos para detectar flexão de braço
            ombro = landmarks[self.mp_pose.PoseLandmark.LEFT_SHOULDER.value]
            cotovelo = landmarks[self.mp_pose.PoseLandmark.LEFT_ELBOW.value]
            pulso = landmarks[self.mp_pose.PoseLandmark.LEFT_WRIST.value]

            # Converter para pixels
            ombro_px = (ombro.x * w, ombro.y * h)
            cotovelo_px = (cotovelo.x * w, cotovelo.y * h)
            pulso_px = (pulso.x * w, pulso.y * h)

            # Calcular ângulo do cotovelo
            angulo = self.calcular_angulo(ombro_px, cotovelo_px, pulso_px)

            # Lógica de contagem de flexões
            if angulo < 90 and self.estado_flexao == "UP":
                self.estado_flexao = "DOWN"
            elif angulo > 160 and self.estado_flexao == "DOWN":
                self.estado_flexao = "UP"
                self.contador_flexoes += 1

            return angulo

        except:
            return None

    def calcular_velocidade(self, landmarks_atual, landmarks_anterior, delta_time):
        """
        Calcula a velocidade média de movimento do corpo
        """
        if landmarks_anterior is None or delta_time == 0:
            return 0

        try:
            # Pontos principais para calcular movimento
            pontos_chave = [
                self.mp_pose.PoseLandmark.LEFT_WRIST.value,
                self.mp_pose.PoseLandmark.RIGHT_WRIST.value,
                self.mp_pose.PoseLandmark.NOSE.value
            ]

            velocidades = []
            for idx in pontos_chave:
                p_atual = landmarks_atual[idx]
                p_anterior = landmarks_anterior[idx]

                distancia = math.sqrt(
                    (p_atual.x - p_anterior.x)**2 +
                    (p_atual.y - p_anterior.y)**2
                )

                velocidade = distancia / delta_time
                velocidades.append(velocidade)

            return np.mean(velocidades)

        except:
            return 0

    def desenhar_interface(self, image, analise, fps, angulo_braco):
        """
        Desenha interface visual com informações
        """
        h, w = image.shape[:2]

        # Painel superior
        overlay = image.copy()
        cv2.rectangle(overlay, (0, 0), (w, 120), (20, 20, 20), -1)
        cv2.addWeighted(overlay, 0.7, image, 0.3, 0, image)

        # Título
        cv2.putText(image, "ANALISADOR DE POSTURA", (20, 35),
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

        # Status da postura
        if analise['postura_boa']:
            texto_postura = "POSTURA BOA ✓"
            cor_postura = (0, 255, 0)
        else:
            texto_postura = "MA POSTURA ✗"
            cor_postura = (0, 0, 255)

        cv2.putText(image, texto_postura, (20, 70),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, cor_postura, 2)

        # FPS
        cv2.putText(image, f"FPS: {fps:.1f}", (w - 150, 35),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        # Alertas
        if analise['alertas']:
            y_offset = 100
            for alerta in analise['alertas']:
                cv2.putText(image, f"⚠ {alerta}", (20, y_offset),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 1)
                y_offset += 25

        # Painel lateral direito - Estatísticas
        overlay = image.copy()
        cv2.rectangle(overlay, (w - 250, 140), (w, h - 120), (20, 20, 20), -1)
        cv2.addWeighted(overlay, 0.7, image, 0.3, 0, image)

        stats_y = 170
        cv2.putText(image, "ESTATISTICAS", (w - 240, stats_y),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        stats_y += 30
        cv2.putText(image, f"Simetria: {analise['simetria_ombros']:.0f}px",
                   (w - 240, stats_y), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)

        stats_y += 25
        cv2.putText(image, f"Inclinacao: {analise['inclinacao_costas']:.1f}°",
                   (w - 240, stats_y), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)

        stats_y += 25
        cv2.putText(image, f"Flexoes: {self.contador_flexoes}",
                   (w - 240, stats_y), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 255, 100), 1)

        if angulo_braco:
            stats_y += 25
            cv2.putText(image, f"Angulo braco: {angulo_braco:.0f}°",
                       (w - 240, stats_y), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)

        # Tempo decorrido
        tempo_total = time.time() - self.tempo_inicio
        stats_y += 35
        cv2.putText(image, f"Tempo: {int(tempo_total)}s",
                   (w - 240, stats_y), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)

        # Painel inferior
        overlay = image.copy()
        cv2.rectangle(overlay, (0, h - 80), (w, h), (20, 20, 20), -1)
        cv2.addWeighted(overlay, 0.7, image, 0.3, 0, image)

        cv2.putText(image, "Pressione 'q' para sair | 'r' para resetar contador | 's' para screenshot",
                   (20, h - 50), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)

        # Alerta de queda (grande e chamativo)
        if self.alerta_queda:
            overlay = image.copy()
            cv2.rectangle(overlay, (50, h//2 - 60), (w - 50, h//2 + 60), (0, 0, 255), -1)
            cv2.addWeighted(overlay, 0.8, image, 0.2, 0, image)

            cv2.putText(image, "⚠️ QUEDA DETECTADA! ⚠️", (w//2 - 200, h//2),
                       cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 3)

        return image

    def run(self):
        """
        Executa o analisador de postura
        """
        print("="*70)
        print("ANALISADOR DE POSTURA CORPORAL")
        print("="*70)
        print("✓ Detecção de má postura")
        print("✓ Análise de simetria")
        print("✓ Detecção de quedas")
        print("✓ Contador de exercícios")
        print("="*70)

        profile = self.pipeline.start(self.config)

        landmarks_anterior = None
        tempo_anterior = time.time()
        fps_time = time.time()
        fps_counter = 0
        fps_atual = 0

        try:
            while True:
                # Captura
                frames = self.pipeline.wait_for_frames()
                aligned_frames = self.align.process(frames)

                depth_frame = aligned_frames.get_depth_frame()
                color_frame = aligned_frames.get_color_frame()

                if not depth_frame or not color_frame:
                    continue

                # Converter para numpy
                color_image = np.asanyarray(color_frame.get_data())
                h, w, _ = color_image.shape

                # MediaPipe
                image_rgb = cv2.cvtColor(color_image, cv2.COLOR_BGR2RGB)
                image_rgb.flags.writeable = False
                results = self.pose.process(image_rgb)
                image_rgb.flags.writeable = True

                # FPS
                fps_counter += 1
                if fps_counter % 30 == 0:
                    tempo_fps = time.time() - fps_time
                    fps_atual = 30 / tempo_fps
                    fps_time = time.time()

                # Processar landmarks
                if results.pose_landmarks:
                    landmarks = results.pose_landmarks.landmark

                    # Desenhar esqueleto
                    self.mp_drawing.draw_landmarks(
                        color_image,
                        results.pose_landmarks,
                        self.mp_pose.POSE_CONNECTIONS,
                        landmark_drawing_spec=self.mp_drawing_styles.get_default_pose_landmarks_style()
                    )

                    # Análise de postura
                    analise = self.analisar_postura(landmarks, h, w)

                    # Detecção de exercício
                    angulo_braco = self.detectar_exercicio(landmarks, h, w)

                    # Calcular velocidade
                    tempo_atual = time.time()
                    delta_time = tempo_atual - tempo_anterior
                    velocidade = self.calcular_velocidade(landmarks, landmarks_anterior, delta_time)
                    self.historico_velocidade.append(velocidade)

                    landmarks_anterior = landmarks
                    tempo_anterior = tempo_atual

                    # Desenhar interface
                    color_image = self.desenhar_interface(
                        color_image, analise, fps_atual, angulo_braco
                    )

                else:
                    # Sem pessoa detectada
                    analise = {
                        'postura_boa': True,
                        'simetria_ombros': 0,
                        'inclinacao_costas': 0,
                        'alertas': ['Nenhuma pessoa detectada']
                    }
                    color_image = self.desenhar_interface(
                        color_image, analise, fps_atual, None
                    )

                # Mostrar
                cv2.imshow('Analisador de Postura', color_image)

                # Teclas
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('r'):
                    self.contador_flexoes = 0
                    print("Contador resetado!")
                elif key == ord('s'):
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    filename = f"postura_{timestamp}.jpg"
                    cv2.imwrite(filename, color_image)
                    print(f"Screenshot salvo: {filename}")

        except KeyboardInterrupt:
            print("\nInterrompido pelo usuário.")

        finally:
            tempo_total = time.time() - self.tempo_inicio

            print("\n" + "="*70)
            print("ESTATÍSTICAS FINAIS")
            print("="*70)
            print(f"⏱️  Tempo total: {tempo_total:.1f}s")
            print(f"🏋️  Flexões detectadas: {self.contador_flexoes}")
            print(f"📊 Frames processados: {self.frame_count}")
            print("="*70)

            self.pipeline.stop()
            cv2.destroyAllWindows()


if __name__ == "__main__":
    analyzer = PosturaAnalyzer()
    analyzer.run()

