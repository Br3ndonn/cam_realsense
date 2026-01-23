# Scanner 3D com Segmentação por IA

## 📋 Visão Geral
Este código implementa um **scanner 3D inteligente** que utiliza Inteligência Artificial para identificar, segmentar e digitalizar objetos específicos em uma cena. O sistema combina visão computacional (YOLOv8) com sensores de profundidade (Intel RealSense) para criar modelos 3D precisos de objetos individuais, ignorando completamente o fundo.

## 🎯 Objetivo Principal
Criar **nuvens de pontos 3D** (point clouds) de objetos específicos com recorte perfeito, eliminando automaticamente o fundo e outros elementos indesejados da cena. O sistema:
- ✅ Detecta múltiplos objetos simultaneamente
- ✅ Identifica automaticamente o objeto mais próximo
- ✅ Cria máscaras precisas pixel a pixel
- ✅ Gera arquivo 3D (.ply) apenas do objeto selecionado

---

## 🔧 Tecnologias Utilizadas

### Hardware
- **Intel RealSense D435/D455**: Câmera RGB-D (cor + profundidade)
- **Sensores sincronizados**: Captura alinhada de cor e profundidade

### Software
- **YOLOv8-Segmentation**: Modelo de IA para detecção e segmentação de objetos
- **Ultralytics**: Framework para modelos YOLO
- **Open3D**: Biblioteca para processamento de nuvens de pontos 3D
- **PyRealSense2**: Interface Python para câmeras RealSense
- **OpenCV**: Processamento de imagem
- **NumPy**: Manipulação de arrays

---

## 🧠 O Diferencial: Segmentação vs Detecção

### Detecção Tradicional (Bounding Box)
```
┌─────────────────┐
│  🏠             │  ← Caixa retangular
│     Pessoa      │     Inclui fundo
│                 │     Recorte impreciso
└─────────────────┘
```

### Segmentação por IA (Este Sistema)
```
    ╱╲
   │👤│  ← Máscara pixel-perfeita
   ╱  ╲     Apenas o objeto
  ╱────╲    Sem fundo!
```

O modelo **YOLOv8-seg** (sufixo 'seg') gera **máscaras binárias** que identificam exatamente quais pixels pertencem ao objeto, permitindo um recorte cirúrgico.

---

## 🏗️ Arquitetura do Sistema

### Fluxo de Dados
```
Câmera RealSense
    ↓
[Imagem RGB] + [Mapa de Profundidade]
    ↓
YOLOv8-seg (Inteligência Artificial)
    ↓
Máscara Binária do Objeto
    ↓
Aplicação da Máscara em RGB e Depth
    ↓
Nuvem de Pontos 3D (Point Cloud)
    ↓
Arquivo .ply (Modelo 3D)
```

---

## 📦 Componentes Principais

### 1️⃣ Inicialização do Modelo de IA

```python
model = YOLO("yolov8n-seg.pt")
```

**O que é?**
- Modelo de deep learning pré-treinado
- Reconhece 80 classes de objetos (pessoa, carro, cadeira, etc.)
- Gera máscaras de segmentação em tempo real
- Versão 'n' (nano) = mais rápida, ideal para tempo real

**Configuração Importante:**
```python
results = model(color_image, stream=True, verbose=False, retina_masks=True)
```
- `stream=True`: Processa frame a frame eficientemente
- `retina_masks=True`: Máscaras na resolução original (640x480), não reduzidas
- `verbose=False`: Não imprime logs a cada frame

---

### 2️⃣ Configuração da Câmera RealSense

```python
config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
```

**Streams Capturados:**
- **Depth (z16)**: Profundidade de cada pixel em milímetros (16 bits)
- **Color (bgr8)**: Imagem RGB colorida (formato BGR do OpenCV)
- **30 FPS**: Taxa de atualização para fluidez

**Alinhamento Crítico:**
```python
align = rs.align(rs.stream.color)
aligned_frames = align.process(frames)
```
- Alinha o mapa de profundidade com a imagem RGB
- Garante que cada pixel de cor corresponda exatamente ao pixel de profundidade
- Essencial para criar nuvem de pontos colorida precisa

---

## 🎭 Processamento da Máscara (Núcleo do Sistema)

### Etapa 1: Inferência da IA
```python
for r in results:
    if r.boxes and r.masks:
        # Modelo detectou objetos com máscaras
```

A IA retorna:
- **Boxes**: Caixas delimitadoras (x1, y1, x2, y2)
- **Masks**: Máscaras de segmentação (formato bitmap)
- **Classes**: Tipo do objeto (pessoa=0, carro=2, cadeira=56, etc.)
- **Confidence**: Confiança da detecção (0.0 a 1.0)

### Etapa 2: Redimensionamento da Máscara
```python
mask_raw = r.masks.data[i].cpu().numpy()

if mask_raw.shape[:2] != (480, 640):
    mask_resized = cv2.resize(mask_raw, (640, 480))
```

**Por que redimensionar?**
- A YOLO processa internamente em tamanhos variados para otimização
- Precisamos que a máscara tenha exatamente 640x480 pixels
- Cada pixel da máscara deve corresponder a um pixel da imagem

### Etapa 3: Binarização
```python
binary_mask = (mask_resized > 0.5).astype(np.uint8) * 255
```

**Transforma máscara de probabilidade em máscara binária:**
- Valores > 0.5 → 255 (branco = objeto)
- Valores ≤ 0.5 → 0 (preto = fundo)

### Etapa 4: Aplicação Seletiva
```python
masked_depth = depth_image.copy()
masked_depth[binary_mask == 0] = 0  # Zera profundidade do fundo
```

**Mágica do recorte:**
- Copia o mapa de profundidade completo
- Onde a máscara é preta (fundo), zera a profundidade
- Resultado: apenas o objeto tem valores de profundidade válidos

---

## 📏 Cálculo de Distância Preciso

### Técnica: Profundidade Mascarada

```python
masked_depth = depth_image.copy()
masked_depth[binary_mask == 0] = 0

valid_pixels = masked_depth[masked_depth > 0]
dist_meters = np.median(valid_pixels) * depth_scale
```

**Vantagens sobre caixa retangular:**

| Método | Problema | Este Sistema |
|--------|----------|--------------|
| Caixa Retangular | Inclui profundidade do fundo | ✅ Ignora fundo completamente |
| Média Simples | Afetada por outliers | ✅ Usa mediana (robusto) |
| Ponto Central | Pode estar fora do objeto | ✅ Considera todos os pixels do objeto |

---

## 🎯 Lógica de Seleção: "Objeto Mais Próximo"

```python
min_dist_detected = float('inf')

for i, box in enumerate(r.boxes):
    dist_meters = np.median(valid_pixels) * depth_scale
    
    if dist_meters < min_dist_detected:
        min_dist_detected = dist_meters
        target_object = {
            "label": label,
            "dist": dist_meters,
            "mask": binary_mask
        }
        color_contour = (0, 255, 0)  # Verde = Alvo selecionado
```

**Funcionamento:**
1. Sistema detecta múltiplos objetos na cena
2. Calcula distância de cada um usando máscara
3. Marca em **verde** o mais próximo (alvo do scan)
4. Marca em **amarelo** os demais (apenas informação)
5. Ao pressionar 'S', salva apenas o objeto verde

---

## 🎨 Visualização em Tempo Real

### Overlay Colorido
```python
contours, _ = cv2.findContours(binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
cv2.drawContours(display_image, contours, -1, color_contour, 2)
```

**O que o usuário vê:**
- Contorno colorido ao redor de cada objeto detectado
- 🟢 **Verde**: Objeto alvo (será salvo ao pressionar 'S')
- 🟡 **Amarelo**: Outros objetos detectados
- Texto com classe e distância em metros

---

## 🗂️ Geração da Nuvem de Pontos 3D

### Processo "Cirúrgico" em 7 Etapas

#### Etapa 1: Mascarar a Imagem Colorida
```python
color_rgb = color_image[:, :, ::-1].copy()  # BGR -> RGB
final_color = cv2.bitwise_and(color_rgb, color_rgb, mask=target_object['mask'])
```
- Converte BGR (OpenCV) para RGB (Open3D)
- Aplica máscara: pixels do fundo viram pretos
- Resultado: apenas o objeto mantém cor

#### Etapa 2: Mascarar a Profundidade
```python
final_depth = depth_image.copy()
final_depth[target_object['mask'] == 0] = 0
```
- Copia mapa de profundidade
- Zera profundidade onde máscara é preta
- Resultado: apenas o objeto tem valores de distância

#### Etapa 3: Converter para Open3D
```python
o3d_color = o3d.geometry.Image(final_color)
o3d_depth = o3d.geometry.Image(final_depth)
```
- Converte arrays NumPy para formato Open3D
- Prepara para criar geometria 3D

#### Etapa 4: Obter Parâmetros Intrínsecos
```python
intrinsics = color_frame.profile.as_video_stream_profile().intrinsics
o3d_intrinsics = o3d.camera.PinholeCameraIntrinsic(
    intrinsics.width, intrinsics.height,
    intrinsics.fx, intrinsics.fy,
    intrinsics.ppx, intrinsics.ppy
)
```

**O que são intrínsecos?**
- **fx, fy**: Distância focal (zoom) em pixels
- **ppx, ppy**: Centro óptico (onde o eixo da lente cruza o sensor)
- Necessários para converter pixels 2D → pontos 3D
- Cada câmera tem valores únicos (calibração de fábrica)

#### Etapa 5: Criar Imagem RGBD
```python
rgbd_image = o3d.geometry.RGBDImage.create_from_color_and_depth(
    o3d_color,
    o3d_depth,
    depth_scale=1.0 / depth_scale,
    depth_trunc=10.0,
    convert_rgb_to_intensity=False
)
```

**Parâmetros importantes:**
- `depth_scale`: Converte valores brutos para metros
- `depth_trunc=10.0`: Ignora pontos além de 10 metros (ruído)
- `convert_rgb_to_intensity=False`: Mantém cores RGB originais

#### Etapa 6: Gerar Point Cloud
```python
pcd = o3d.geometry.PointCloud.create_from_rgbd_image(
    rgbd_image,
    o3d_intrinsics
)
```

**O que acontece internamente:**
- Para cada pixel não-zero na profundidade:
  - Calcula posição (X, Y, Z) no espaço 3D
  - Atribui cor RGB do pixel correspondente
- Resultado: milhares de pontos coloridos no espaço 3D

#### Etapa 7: Correção de Orientação
```python
pcd.transform([[1, 0, 0, 0], [0, -1, 0, 0], [0, 0, -1, 0], [0, 0, 0, 1]])
```

**Por que transformar?**
- RealSense usa coordenadas: X=direita, Y=baixo, Z=frente
- Convenção 3D padrão: X=direita, Y=cima, Z=fundo
- Matriz inverte Y e Z para alinhamento correto

#### Etapa 8: Salvar Arquivo
```python
timestamp = datetime.datetime.now().strftime("%H%M%S")
filename = f"recorte_{target_object['label']}_{timestamp}.ply"
o3d.io.write_point_cloud(filename, pcd)
```

**Formato PLY:**
- Formato aberto para nuvens de pontos
- Pode ser aberto em: MeshLab, CloudCompare, Blender
- Contém posições (x,y,z) e cores (r,g,b) de cada ponto

---

## 🎮 Controles do Sistema

| Tecla | Ação | Descrição |
|-------|------|-----------|
| **S** | Salvar | Captura e salva nuvem de pontos 3D do objeto verde |
| **Q** ou **ESC** | Sair | Encerra o scanner |

---

## 📊 Exemplo de Uso Prático

### Cenário: Digitalizar uma Cadeira

1. **Sistema Iniciado**
   ```
   ┌──────────────────────┐
   │ 🪑 Cadeira (1.2m)   │ ← Verde (alvo)
   │ 👤 Pessoa (2.5m)    │ ← Amarelo
   │ 🚪 Porta (3.0m)     │ ← Amarelo
   └──────────────────────┘
   ```

2. **Usuário pressiona 'S'**
   - Sistema processa apenas a cadeira (objeto verde)
   - Aplica máscara de segmentação
   - Gera nuvem de pontos 3D

3. **Arquivo Salvo**
   ```
   recorte_chair_143052.ply
   ```
   - Contém apenas a cadeira
   - Pessoa e porta não estão no arquivo
   - Fundo completamente removido

4. **Visualização no MeshLab**
   ```
        ╱╲
       ╱  ╲
      │ 🪑 │  ← Modelo 3D limpo
      ╱────╲    Sem fundo!
     ╱      ╲
   ```

---

## 🎓 Conceitos para Explicar ao Orientando

### 1. O que é Segmentação Semântica?
- **Classificação pixel a pixel** de uma imagem
- Cada pixel recebe um rótulo (pessoa, carro, fundo, etc.)
- Diferente de detecção (caixas) ou classificação (imagem inteira)

### 2. Por que YOLOv8 e não outro modelo?
- ⚡ **Velocidade**: Processa 30+ FPS em tempo real
- 🎯 **Precisão**: Estado da arte em segmentação
- 📦 **Facilidade**: Uma linha de código para inferência
- 🌍 **Versatilidade**: 80 classes pré-treinadas

### 3. O que é uma Nuvem de Pontos?
- Conjunto de pontos (x, y, z) no espaço 3D
- Cada ponto pode ter cor (r, g, b)
- Representa a superfície de um objeto
- Pode ser convertida em malha (mesh) depois

### 4. Por que Alinhar Depth com Color?
- Sensores RGB e Depth são físicos diferentes
- Estão em posições ligeiramente diferentes na câmera
- Alinhamento garante: pixel[100,100] na cor = pixel[100,100] na profundidade
- Sem alinhamento: cores aparecem deslocadas no modelo 3D

### 5. Intrínsecos vs Extrínsecos
- **Intrínsecos**: Propriedades internas da câmera (focal, centro óptico)
- **Extrínsecos**: Posição/rotação da câmera no mundo
- Este código usa apenas intrínsecos (câmera é referência)

---

## 🔄 Fluxo Completo (Diagrama Detalhado)

```
┌─────────────────────────────────────────────────────────┐
│ 1. CAPTURA                                              │
│    RealSense → [RGB 640x480] + [Depth 640x480]         │
└──────────────────┬──────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────┐
│ 2. ALINHAMENTO                                          │
│    Sincroniza RGB com Depth pixel a pixel               │
└──────────────────┬──────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────┐
│ 3. SEGMENTAÇÃO IA                                       │
│    YOLOv8 → Detecta objetos + Gera máscaras binárias    │
└──────────────────┬──────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────┐
│ 4. SELEÇÃO                                              │
│    Calcula distância de cada objeto → Escolhe o +próximo│
└──────────────────┬──────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────┐
│ 5. VISUALIZAÇÃO                                         │
│    Desenha contornos coloridos + Aguarda comando        │
└──────────────────┬──────────────────────────────────────┘
                   ↓ (Usuário pressiona 'S')
┌─────────────────────────────────────────────────────────┐
│ 6. APLICAÇÃO DE MÁSCARA                                 │
│    RGB mascarado + Depth mascarado                      │
└──────────────────┬──────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────┐
│ 7. GERAÇÃO 3D                                           │
│    Intrínsecos + RGBD → Point Cloud                     │
└──────────────────┬──────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────┐
│ 8. EXPORTAÇÃO                                           │
│    Arquivo .ply salvo no disco                          │
└─────────────────────────────────────────────────────────┘
```

---

## ⚠️ Limitações e Considerações

### Limitações Atuais
1. **Classes Fixas**: Reconhece apenas 80 classes do COCO dataset
2. **Distância Limitada**: Depth funciona melhor até 5 metros
3. **Superfícies Reflexivas**: Vidro/espelhos causam ruído na profundidade
4. **Objetos Pequenos**: Objetos < 5cm podem não ser detectados
5. **Um Objeto por Vez**: Salva apenas o objeto mais próximo

### Boas Práticas
- ✅ Iluminação adequada melhora detecção da IA
- ✅ Mantenha objetos entre 0.5m e 4m da câmera
- ✅ Evite movimentos rápidos durante captura
- ✅ Capture múltiplos ângulos para reconstrução completa

---

## 🚀 Aplicações Práticas

### 1. E-commerce
- Digitalização automática de produtos
- Criação de catálogos 3D
- Visualização AR para clientes

### 2. Manufatura
- Inspeção de qualidade dimensional
- Comparação com modelos CAD
- Documentação de peças

### 3. Arqueologia
- Digitalização de artefatos
- Preservação digital de patrimônio
- Análise não-invasiva

### 4. Educação
- Criação de bibliotecas 3D
- Material didático interativo
- Ensino de modelagem 3D

---

## 🛠️ Possíveis Melhorias

### Nível Iniciante
- [ ] Adicionar contador de objetos detectados
- [ ] Salvar também imagem 2D do objeto
- [ ] Adicionar filtro por classe (só cadeiras, só pessoas)

### Nível Intermediário
- [ ] Captura multi-ângulo automática (360°)
- [ ] Fusão de múltiplas capturas em um modelo único
- [ ] Interface gráfica (GUI) para seleção de objetos

### Nível Avançado
- [ ] Treinar modelo customizado para classes específicas
- [ ] Reconstrução de malha (mesh) completa
- [ ] Texturização UV para realismo
- [ ] Integração com CAD para medições precisas

---

## 🔗 Dependências e Instalação

### Pré-requisitos
```bash
pip install pyrealsense2
pip install open3d
pip install opencv-python
pip install ultralytics
pip install numpy
```

### Modelo YOLO
```bash
# O modelo será baixado automaticamente na primeira execução
# Ou baixe manualmente de: https://github.com/ultralytics/assets/releases
```

### Execução
```bash
python virtualizacao_v2.py
```

---

## 🤖 Integração com SAM (Segment Anything Model) da Meta

### O que é o SAM?

**SAM (Segment Anything Model)** é um modelo revolucionário de segmentação desenvolvido pela Meta AI que pode segmentar **qualquer objeto** em uma imagem, sem necessidade de treinamento prévio para classes específicas.

### SAM vs YOLOv8: Comparação

| Característica | YOLOv8-seg | SAM (Meta) |
|----------------|------------|------------|
| **Classes** | 80 classes pré-definidas | Qualquer objeto |
| **Treinamento** | Necessário para novas classes | Zero-shot (funciona direto) |
| **Prompt** | Automático | Requer interação (clique/caixa) |
| **Velocidade** | Muito rápido (30+ FPS) | Mais lento (~5 FPS) |
| **Precisão** | Boa para classes conhecidas | Excelente para qualquer objeto |
| **Uso Ideal** | Detecção automática em tempo real | Segmentação interativa precisa |

### Quando Usar SAM no Sistema?

✅ **Use SAM quando:**
- Precisa segmentar objetos únicos/incomuns (não nas 80 classes do YOLO)
- Quer controle manual sobre o que segmentar (clique do usuário)
- Precisão é mais importante que velocidade
- Trabalha com objetos complexos ou parcialmente ocultos

❌ **Mantenha YOLOv8 quando:**
- Precisa de detecção automática sem interação humana
- Velocidade em tempo real é crítica
- Objetos são de classes comuns (pessoa, carro, cadeira, etc.)
- Quer processar múltiplos objetos simultaneamente

---

## 🔧 Como Integrar SAM ao Sistema Atual

### Passo 1: Instalação

```bash
# Instalar SAM
pip install segment-anything

# Baixar modelo (escolha um):
# - sam_vit_h (Huge): Mais preciso, mais lento
# - sam_vit_l (Large): Balanceado
# - sam_vit_b (Base): Mais rápido, menos preciso

# Baixar de: https://github.com/facebookresearch/segment-anything
```

### Passo 2: Código de Integração

Aqui está a versão **híbrida** que combina YOLOv8 (detecção automática) + SAM (refinamento preciso):

```python
import pyrealsense2 as rs
import numpy as np
import open3d as o3d
import cv2
import datetime
from ultralytics import YOLO
from segment_anything import sam_model_registry, SamPredictor


def scan_with_sam():
    """
    Sistema Híbrido:
    1. YOLO detecta objetos automaticamente
    2. Usuário clica para refinar com SAM
    3. SAM gera máscara perfeita
    """
    
    # --- INICIALIZAÇÃO ---
    print("Carregando YOLOv8 (detecção rápida)...")
    yolo_model = YOLO("yolov8n-seg.pt")
    
    print("Carregando SAM (segmentação precisa)...")
    sam_checkpoint = "sam_vit_b_01ec64.pth"  # Ajuste o caminho
    model_type = "vit_b"
    device = "cuda"  # ou "cpu" se não tiver GPU
    
    sam = sam_model_registry[model_type](checkpoint=sam_checkpoint)
    sam.to(device=device)
    sam_predictor = SamPredictor(sam)
    
    # Configuração RealSense (igual ao código original)
    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
    config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
    
    profile = pipeline.start(config)
    depth_sensor = profile.get_device().first_depth_sensor()
    depth_scale = depth_sensor.get_depth_scale()
    
    align = rs.align(rs.stream.color)
    
    # Variáveis de controle
    modo_sam = False  # True = SAM ativo, False = YOLO ativo
    pontos_clicados = []
    cor_image_atual = None
    
    def mouse_callback(event, x, y, flags, param):
        """Captura cliques do mouse para SAM"""
        nonlocal pontos_clicados, modo_sam
        
        if modo_sam and event == cv2.EVENT_LBUTTONDOWN:
            pontos_clicados.append([x, y])
            print(f"Ponto adicionado: ({x}, {y})")
    
    cv2.namedWindow('Scanner Hibrido')
    cv2.setMouseCallback('Scanner Hibrido', mouse_callback)
    
    try:
        while True:
            frames = pipeline.wait_for_frames()
            aligned_frames = align.process(frames)
            aligned_depth_frame = aligned_frames.get_depth_frame()
            color_frame = aligned_frames.get_color_frame()
            
            if not aligned_depth_frame or not color_frame:
                continue
            
            depth_image = np.asanyarray(aligned_depth_frame.get_data())
            color_image = np.asanyarray(color_frame.get_data())
            cor_image_atual = color_image.copy()
            
            display_image = color_image.copy()
            
            # --- MODO 1: YOLO (Detecção Automática) ---
            if not modo_sam:
                results = yolo_model(color_image, stream=True, verbose=False, retina_masks=True)
                
                for r in results:
                    if r.boxes and r.masks:
                        for i, box in enumerate(r.boxes):
                            x1, y1, x2, y2 = map(int, box.xyxy[0])
                            label = yolo_model.names[int(box.cls[0])]
                            conf = float(box.conf[0])
                            
                            if conf < 0.5: continue
                            
                            # Desenhar detecções
                            cv2.rectangle(display_image, (x1, y1), (x2, y2), (0, 255, 0), 2)
                            cv2.putText(display_image, f"{label} {conf:.2f}", 
                                       (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 2)
                
                cv2.putText(display_image, "MODO YOLO - Pressione 'M' para SAM", 
                           (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
            
            # --- MODO 2: SAM (Segmentação Interativa) ---
            else:
                # Preparar imagem para SAM (RGB)
                sam_predictor.set_image(cv2.cvtColor(cor_image_atual, cv2.COLOR_BGR2RGB))
                
                # Se houver pontos clicados, gerar máscara
                if len(pontos_clicados) > 0:
                    input_points = np.array(pontos_clicados)
                    input_labels = np.ones(len(pontos_clicados))  # 1 = foreground
                    
                    # Gerar máscara com SAM
                    masks, scores, logits = sam_predictor.predict(
                        point_coords=input_points,
                        point_labels=input_labels,
                        multimask_output=True  # Gera 3 opções
                    )
                    
                    # Pegar a melhor máscara (maior score)
                    best_mask = masks[np.argmax(scores)]
                    
                    # Overlay colorido da máscara
                    overlay = display_image.copy()
                    overlay[best_mask] = overlay[best_mask] * 0.5 + np.array([0, 255, 0]) * 0.5
                    display_image = overlay.astype(np.uint8)
                    
                    # Desenhar contorno
                    mask_uint8 = (best_mask * 255).astype(np.uint8)
                    contours, _ = cv2.findContours(mask_uint8, cv2.RETR_EXTERNAL, 
                                                   cv2.CHAIN_APPROX_SIMPLE)
                    cv2.drawContours(display_image, contours, -1, (0, 255, 255), 2)
                
                # Desenhar pontos clicados
                for pt in pontos_clicados:
                    cv2.circle(display_image, tuple(pt), 5, (255, 0, 0), -1)
                
                cv2.putText(display_image, f"MODO SAM - Clique no objeto ({len(pontos_clicados)} pontos)", 
                           (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,255), 2)
                cv2.putText(display_image, "'S'=Salvar | 'C'=Limpar | 'M'=YOLO", 
                           (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)
            
            cv2.imshow('Scanner Hibrido', display_image)
            
            # --- CONTROLES ---
            key = cv2.waitKey(1)
            
            if key & 0xFF == ord('q') or key == 27:
                break
            
            elif key & 0xFF == ord('m'):
                # Alternar entre YOLO e SAM
                modo_sam = not modo_sam
                pontos_clicados = []
                print(f"Modo alterado para: {'SAM' if modo_sam else 'YOLO'}")
            
            elif key & 0xFF == ord('c'):
                # Limpar pontos
                pontos_clicados = []
                print("Pontos limpos")
            
            elif key & 0xFF == ord('s'):
                if modo_sam and len(pontos_clicados) > 0:
                    print("Salvando com máscara SAM...")
                    
                    # Gerar máscara final
                    sam_predictor.set_image(cv2.cvtColor(cor_image_atual, cv2.COLOR_BGR2RGB))
                    input_points = np.array(pontos_clicados)
                    input_labels = np.ones(len(pontos_clicados))
                    
                    masks, scores, _ = sam_predictor.predict(
                        point_coords=input_points,
                        point_labels=input_labels,
                        multimask_output=True
                    )
                    
                    best_mask = masks[np.argmax(scores)]
                    binary_mask = (best_mask * 255).astype(np.uint8)
                    
                    # Aplicar máscara (igual ao código original)
                    color_rgb = cor_image_atual[:, :, ::-1].copy()
                    final_color = cv2.bitwise_and(color_rgb, color_rgb, mask=binary_mask)
                    
                    final_depth = depth_image.copy()
                    final_depth[binary_mask == 0] = 0
                    
                    # Criar Point Cloud
                    o3d_color = o3d.geometry.Image(final_color)
                    o3d_depth = o3d.geometry.Image(final_depth)
                    
                    intrinsics = color_frame.profile.as_video_stream_profile().intrinsics
                    o3d_intrinsics = o3d.camera.PinholeCameraIntrinsic(
                        intrinsics.width, intrinsics.height,
                        intrinsics.fx, intrinsics.fy,
                        intrinsics.ppx, intrinsics.ppy
                    )
                    
                    rgbd_image = o3d.geometry.RGBDImage.create_from_color_and_depth(
                        o3d_color, o3d_depth,
                        depth_scale=1.0/depth_scale,
                        depth_trunc=10.0,
                        convert_rgb_to_intensity=False
                    )
                    
                    pcd = o3d.geometry.PointCloud.create_from_rgbd_image(
                        rgbd_image, o3d_intrinsics
                    )
                    
                    pcd.transform([[1,0,0,0], [0,-1,0,0], [0,0,-1,0], [0,0,0,1]])
                    
                    timestamp = datetime.datetime.now().strftime("%H%M%S")
                    filename = f"sam_scan_{timestamp}.ply"
                    o3d.io.write_point_cloud(filename, pcd)
                    
                    print(f"✓ Salvo: {filename}")
                    pontos_clicados = []
                    
                else:
                    print("Use modo SAM e clique no objeto primeiro!")
    
    finally:
        pipeline.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    scan_with_sam()
```

### Passo 3: Modos de Uso

#### Modo 1: SAM com Prompts de Ponto (Clique)
```python
# Usuário clica em pontos do objeto
# SAM segmenta automaticamente
# Ideal para: Objetos claros com bordas definidas
```

#### Modo 2: SAM com Bounding Box
```python
# Modificação do código:
def mouse_callback_box(event, x, y, flags, param):
    global bbox_start, bbox_end, drawing
    
    if event == cv2.EVENT_LBUTTONDOWN:
        drawing = True
        bbox_start = (x, y)
    
    elif event == cv2.EVENT_MOUSEMOVE and drawing:
        bbox_end = (x, y)
    
    elif event == cv2.EVENT_LBUTTONUP:
        drawing = False
        bbox_end = (x, y)
        
        # Usar caixa como prompt para SAM
        input_box = np.array([bbox_start[0], bbox_start[1], 
                             bbox_end[0], bbox_end[1]])
        
        masks, scores, _ = sam_predictor.predict(
            box=input_box,
            multimask_output=False
        )
```

#### Modo 3: SAM Automático (com YOLO)
```python
# Use detecções do YOLO como prompts para SAM
# Melhor dos dois mundos:
# - YOLO detecta automaticamente
# - SAM refina a máscara com precisão

for box in yolo_detections:
    x1, y1, x2, y2 = box
    input_box = np.array([x1, y1, x2, y2])
    
    masks, _, _ = sam_predictor.predict(
        box=input_box,
        multimask_output=False
    )
    # Usa máscara do SAM em vez da máscara YOLO
```

---

## 🎯 Estratégias de Integração

### Estratégia 1: YOLO + SAM (Recomendado)
```
YOLO (rápido) → Detecta objetos
    ↓
SAM (preciso) → Refina máscaras
    ↓
Point Cloud 3D
```

**Vantagens:**
- Automático + Preciso
- Sem necessidade de interação do usuário
- Funciona para classes conhecidas e desconhecidas

### Estratégia 2: SAM Puro (Interativo)
```
Usuário clica → SAM segmenta → Point Cloud 3D
```

**Vantagens:**
- Funciona com qualquer objeto
- Controle total do usuário
- Melhor para objetos únicos/artísticos

### Estratégia 3: Seleção Adaptativa
```python
if objeto in classes_yolo:
    usar_yolo()  # Rápido
else:
    usar_sam()   # Preciso mas mais lento
```

---

## ⚡ Otimizações de Performance

### 1. Cache do Encoder SAM
```python
# Processar imagem uma vez, usar múltiplos prompts
sam_predictor.set_image(image)  # Computacionalmente caro

# Agora pode fazer múltiplas predições rapidamente
mask1 = sam_predictor.predict(point1)
mask2 = sam_predictor.predict(point2)
mask3 = sam_predictor.predict(box1)
```

### 2. Usar SAM Mobile (FastSAM)
```bash
pip install ultralytics  # Já tem FastSAM integrado

# No código:
from ultralytics import FastSAM

model = FastSAM('FastSAM-x.pt')
results = model(image, device='cuda', retina_masks=True)
```

**FastSAM vs SAM:**
- 10x mais rápido
- Baseado em YOLOv8
- Qualidade 95% do SAM original

### 3. Redução de Resolução
```python
# Processar em resolução menor, depois redimensionar máscara
image_small = cv2.resize(image, (320, 240))
sam_predictor.set_image(image_small)
# ... gerar máscara
mask_full = cv2.resize(mask, (640, 480))
```

---

## 📊 Exemplo Prático: Segmentar Objeto Irregular

### Cenário: Digitalizar uma escultura complexa

**Problema com YOLO:**
```
❌ Classe "escultura" não existe no COCO dataset
❌ Formato irregular confunde detecção de caixas
❌ Máscara imprecisa em detalhes finos
```

**Solução com SAM:**
```
✅ Usuário clica em 3-4 pontos na escultura
✅ SAM gera máscara perfeita (bordas suaves)
✅ Point Cloud captura todos os detalhes
✅ Resultado: Modelo 3D preciso
```

### Código Específico:
```python
# Usuário clica em pontos da escultura
pontos = [[320, 240], [350, 200], [300, 280], [340, 260]]
labels = [1, 1, 1, 1]  # Todos foreground

masks, scores, _ = sam_predictor.predict(
    point_coords=np.array(pontos),
    point_labels=np.array(labels),
    multimask_output=True
)

# Escolher máscara com maior score
melhor_mascara = masks[np.argmax(scores)]
```

---

## 🔄 Fluxo Completo com SAM

```
┌─────────────────────────────────────────┐
│ Captura: RealSense RGB + Depth          │
└──────────────┬──────────────────────────┘
               ↓
┌─────────────────────────────────────────┐
│ Detecção Inicial (Opcional):           │
│ YOLO identifica área de interesse       │
└──────────────┬──────────────────────────┘
               ↓
┌─────────────────────────────────────────┐
│ Interação Usuário:                      │
│ - Cliques em pontos do objeto           │
│ - OU desenho de caixa                   │
│ - OU automático via YOLO box            │
└──────────────┬──────────────────────────┘
               ↓
┌─────────────────────────────────────────┐
│ Segmentação SAM:                        │
│ - Encoder processa imagem               │
│ - Decoder gera máscara do prompt        │
│ - Retorna 3 opções (melhor score)       │
└──────────────┬──────────────────────────┘
               ↓
┌─────────────────────────────────────────┐
│ Refinamento (Opcional):                 │
│ - Usuário adiciona mais pontos          │
│ - SAM regenera máscara                  │
└──────────────┬──────────────────────────┘
               ↓
┌─────────────────────────────────────────┐
│ Aplicação de Máscara:                   │
│ - RGB mascarado                         │
│ - Depth mascarado                       │
└──────────────┬──────────────────────────┘
               ↓
┌─────────────────────────────────────────┐
│ Geração 3D: Point Cloud → .ply          │
└─────────────────────────────────────────┘
```

---

## 📚 Referências e Recursos

### SAM (Meta AI)
- **Paper**: "Segment Anything" (Kirillov et al., 2023)
- **GitHub**: https://github.com/facebookresearch/segment-anything
- **Demo Online**: https://segment-anything.com/
- **Modelos**: https://github.com/facebookresearch/segment-anything#model-checkpoints

### Documentação
- **YOLOv8**: https://docs.ultralytics.com/
- **Open3D**: http://www.open3d.org/docs/
- **RealSense**: https://dev.intelrealsense.com/docs/

### Papers Relevantes
- SAM: Kirillov et al. (2023)
- YOLOv8: Ultralytics (2023)
- Open3D: Zhou et al. (2018)
- COCO Dataset: Lin et al. (2014)

### Ferramentas de Visualização
- **MeshLab**: Viewer gratuito de nuvens de pontos
- **CloudCompare**: Análise avançada de point clouds
- **Blender**: Edição e renderização 3D

---

## 💡 Resumo em 3 Pontos

1. **Segmentação por IA**: YOLOv8 identifica objetos e cria máscaras perfeitas
2. **Recorte Cirúrgico**: Máscara remove fundo de RGB e Depth simultaneamente
3. **Modelo 3D Limpo**: Open3D gera arquivo .ply apenas do objeto desejado

---

**Última atualização:** Janeiro 2026  
**Tecnologia:** YOLOv8 + RealSense + Open3D  
**Autor:** Sistema de Digitalização 3D com IA
