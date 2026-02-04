# Sistema de Monitoramento de Caçamba com Visão Noturna

## 📋 Visão Geral
Este código implementa um sistema de monitoramento inteligente para detectar e medir o nível de carga em caçambas de caminhão utilizando uma câmera Intel RealSense. O sistema foi especialmente desenvolvido para funcionar em **condições adversas**: ambientes escuros e com presença de poeira.

## 🎯 Objetivo Principal
Detectar automaticamente quando uma caçamba de caminhão está vazia, parcialmente carregada ou completamente carregada, mesmo em condições de:
- ✅ Escuridão total (ambiente noturno)
- ✅ Presença de poeira suspensa no ar
- ✅ Partículas coladas na lente da câmera

---

## 🔧 Tecnologias Utilizadas

### Hardware
- **Intel RealSense D435/D455**: Câmera de profundidade com sensor infravermelho
- **Projetor Laser**: Emissor de padrão IR para cálculo de profundidade

### Software
- **PyRealSense2**: Interface Python para câmeras RealSense
- **OpenCV**: Processamento de imagem e visão computacional
- **NumPy**: Manipulação eficiente de arrays numéricos

---

## 🏗️ Arquitetura do Sistema

### 1️⃣ Configuração Inicial
```python
AREA_MINIMA = 10000              # Área mínima para considerar um contorno válido (pixels)
ALTURA_BORDA_CAMINHAO = 3.5      # Distância da câmera até a borda da caçamba (metros)
CLIP_MIN = 0.5                   # Ignora objetos muito próximos (poeira na lente)
CLIP_MAX = 6.0                   # Ignora leituras muito distantes (fundo infinito)
```

### 2️⃣ Inicialização da Câmera RealSense

**Diferencial Importante:** O código utiliza **sensor infravermelho (IR)** ao invés de câmera RGB colorida.

**Por quê?**
- 🌙 O IR funciona perfeitamente no escuro graças ao projetor laser
- 💨 Menos afetado por poeira que câmeras coloridas
- 🎯 Alto contraste em bordas físicas dos objetos

```python
config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)     # Profundidade
config.enable_stream(rs.stream.infrared, 1, 640, 480, rs.format.y8, 30) # Infravermelho
```

---

## 🛡️ Sistema de Filtragem Anti-Poeira

A "mágica" do código está na aplicação de **três filtros em sequência** para eliminar ruídos causados por poeira:

### Filtro 1: Decimation
- **Função:** Reduz a resolução da imagem de profundidade
- **Benefício:** Diminui ruído granulado e aumenta performance
- **Configuração:** `filter_magnitude = 1` (sem redução, aumentar se necessário)

### Filtro 2: Spatial
- **Função:** Suaviza a superfície da medição de profundidade
- **Benefício:** "Tapa buracos" na nuvem de pontos causados por partículas de poeira
- **Parâmetros:**
  - `filter_magnitude = 2`: Intensidade da suavização
  - `filter_smooth_alpha = 0.5`: Peso da suavização
  - `filter_smooth_delta = 20`: Limite de diferença entre pixels

### Filtro 3: Temporal ⭐ (Mais Importante)
- **Função:** Compara o frame atual com frames anteriores
- **Benefício:** Remove objetos que aparecem e desaparecem rapidamente (poeira flutuando)
- **Lógica:** Se um pixel muda drasticamente entre frames, provavelmente é ruído transitório

### Otimização do Laser
```python
depth_sensor.set_option(rs.option.emitter_enabled, 1.0)  # Liga o projetor laser
depth_sensor.set_option(rs.option.laser_power, max_laser) # Potência máxima para penetrar poeira
```

---

## 👁️ Processamento de Visão Computacional

### Etapa 1: Melhoria de Contraste
```python
ir_enhanced = cv2.equalizeHist(ir_image)
```
- Equalização de histograma para destacar detalhes mesmo com pouca luz
- Melhora a visibilidade das bordas da caçamba

### Etapa 2: Remoção de Ruído
```python
blur = cv2.GaussianBlur(ir_enhanced, (5, 5), 0)
```
- Remove ruído granulado do sensor IR
- Prepara a imagem para detecção de bordas

### Etapa 3: Detecção de Bordas
```python
edges = cv2.Canny(blur, 50, 150)
edges = cv2.dilate(edges, None, iterations=1)
```
- Algoritmo Canny identifica bordas na imagem
- Dilatação conecta linhas quebradas pela poeira

### Etapa 4: Identificação da Caçamba
```python
contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
```
- Encontra todos os contornos na imagem
- Filtra apenas formas retangulares grandes (4 vértices)
- Seleciona o maior retângulo válido (provavelmente a caçamba)

---

## 📏 Medição de Profundidade Robusta

### Técnica Anti-Poeira para Medição

Ao invés de calcular a **média** simples da profundidade (que seria afetada por partículas de poeira), o código usa:

1. **Filtragem de valores absurdos:**
   ```python
   distancias_reais = distancias_metros[
       (distancias_metros > CLIP_MIN) & (distancias_metros < CLIP_MAX)
   ]
   ```
   - Remove leituras de poeira a 10cm da câmera
   - Remove leituras de fundo infinito

2. **Uso da MEDIANA ao invés de MÉDIA:**
   ```python
   distancia_mediana = np.median(distancias_reais)
   ```
   - A mediana é resistente a outliers (picos causados por poeira)
   - Valores extremos não afetam o resultado final

---

## 🚦 Lógica de Detecção de Carga

### Estados do Sistema

| Estado | Condição | Cor | Descrição |
|--------|----------|-----|-----------|
| **AGUARDANDO CAMINHÃO** | Nenhum retângulo detectado | 🔴 Vermelho | Sistema ativo, aguardando entrada de caminhão |
| **CAÇAMBA VAZIA** | Distância > 3.5m | 🟠 Laranja | Caçamba detectada mas sem carga |
| **CARGA DETECTADA** | Distância < 3.5m | 🟢 Verde | Carga presente na caçamba |

### Cálculo de Altura da Carga
```python
chao_cacamba = 4.0  # Distância da câmera ao fundo da caçamba vazia
altura_carga = chao_cacamba - distancia_mediana
```

**Exemplo:**
- Câmera está a 4.0m do fundo da caçamba vazia
- Sensor mede 2.5m até a superfície da carga
- Altura da carga = 4.0 - 2.5 = **1.5m de material**

---

## 🖥️ Interface Visual

### Janela Principal: "Monitoramento Noturno/Poeira"
- Mostra a imagem do sensor IR (visão noturna)
- Desenha o retângulo da caçamba detectada
- Exibe status e informações de medição

### Janela Secundária: "Depth Map Filtrado"
- Mapa de calor colorido da profundidade
- Visualização dos filtros aplicados
- Útil para debug e calibração

### Controles
- Pressione **'q'** para sair do sistema

---

## 🎓 Conceitos Principais para Explicar ao Orientando

### 1. Por que Infravermelho ao invés de RGB?
- Funciona no escuro total
- Não depende de iluminação ambiente
- Maior contraste em bordas físicas

### 2. Por que Filtros Temporais são importantes?
- Poeira se move rapidamente entre frames
- Objetos sólidos (caçamba) permanecem estáveis
- Comparar frames elimina "fantasmas" de poeira

### 3. Por que Mediana ao invés de Média?
- Média é sensível a valores extremos (outliers)
- Se 5% dos pixels tiverem poeira próxima, a média fica errada
- Mediana sempre retorna o "valor do meio", ignorando extremos

### 4. Calibração é Essencial
- Os valores 3.5m e 4.0m devem ser medidos no cenário real
- Cada instalação terá distâncias diferentes
- AREA_MINIMA depende da resolução e distância da câmera

---

## 🔄 Fluxo de Execução (Resumo)

```
1. Inicializa câmera RealSense em modo IR + Depth
   ↓
2. Configura filtros anti-poeira (Spatial + Temporal)
   ↓
3. Loop principal:
   ├─ Captura frame IR e Depth
   ├─ Aplica filtros de profundidade
   ├─ Melhora contraste da imagem IR
   ├─ Detecta bordas (Canny)
   ├─ Encontra contornos retangulares
   ├─ Seleciona maior retângulo (caçamba)
   ├─ Calcula mediana de profundidade na região
   ├─ Determina estado (vazia/carregada)
   └─ Exibe resultado visual
   ↓
4. Pressionar 'q' para finalizar
```

---

## ⚠️ Limitações e Melhorias Futuras

### Limitações Atuais
- Assume que a caçamba é sempre o maior retângulo na cena
- Calibração manual das distâncias (3.5m, 4.0m)
- Não diferencia tipos de material na carga

### Possíveis Melhorias
- 🤖 Machine Learning para identificar forma da caçamba
- 📊 Cálculo automático de volume de carga
- 📱 Interface web para monitoramento remoto
- 💾 Registro em banco de dados com timestamp
- 📧 Alertas automáticos quando caçamba estiver cheia

---

## 🚀 Como Usar

### Pré-requisitos
```bash
pip install pyrealsense2 opencv-python numpy
```

### Execução
```bash
python verificar_caixa.py
```

### Calibração Inicial
1. Posicione a câmera apontando para a caçamba
2. Com caçamba vazia, anote a distância medida
3. Ajuste `ALTURA_BORDA_CAMINHAO` para este valor
4. Com caçamba cheia no fundo, anote a distância
5. Ajuste `chao_cacamba` para este valor

---

## 📚 Referências Técnicas

- **Intel RealSense SDK**: https://github.com/IntelRealSense/librealsense
- **OpenCV Documentation**: https://docs.opencv.org/
- **Filtros RealSense**: https://dev.intelrealsense.com/docs/post-processing-filters

---

**Última atualização:** Janeiro 2026  
**Autor:** Sistema de Monitoramento Industrial
