# 🏃 Body Tracking - Algoritmos Avançados

## 📦 Novos Algoritmos Criados

### 1. 🧍 **postura_analyzer.py** - Analisador de Postura Corporal

Sistema avançado de análise de postura em tempo real.

#### 🎯 Funcionalidades

✅ **Detecção de Má Postura**
- Costas curvadas
- Ombros desalinhados
- Cabeça projetada para frente
- Inclinação corporal

✅ **Análise de Simetria**
- Compara altura dos ombros
- Detecta desalinhamentos > 30 pixels
- Calcula ângulo de inclinação das costas

✅ **Detecção de Quedas**
- Alerta quando cabeça está abaixo do quadril
- Notificação visual grande e vermelha
- Útil para monitoramento de idosos

✅ **Contador de Exercícios**
- Conta flexões automaticamente
- Detecta movimento de braços (ângulo do cotovelo)
- Reset manual com tecla 'r'

✅ **Rastreamento de Velocidade**
- Calcula velocidade média de movimento
- Histórico dos últimos 10 frames
- Útil para análise de movimentos rápidos

✅ **Interface Profissional**
- Painel superior com status da postura
- Painel lateral com estatísticas
- Alertas visuais coloridos
- Screenshots com tecla 's'

#### 🎬 Como Usar

```bash
python postura_analyzer.py
```

**Teclas:**
- `q` - Sair
- `r` - Resetar contador de flexões
- `s` - Salvar screenshot

#### 📊 Métricas Analisadas

| Métrica | Descrição | Limites |
|---------|-----------|---------|
| Simetria ombros | Diferença de altura em pixels | Alerta > 30px |
| Inclinação costas | Ângulo de desvio da vertical | Alerta > 15° |
| Projeção cabeça | Distância horizontal nariz-ombros | Alerta > 60px |
| Ângulo cotovelo | Para contagem de flexões | DOWN < 90°, UP > 160° |

#### 🔬 Algoritmos Implementados

**1. Cálculo de Ângulo entre 3 Pontos**
```python
def calcular_angulo(a, b, c):
    # Produto escalar entre vetores ba e bc
    # Retorna ângulo em graus
```

**2. Análise de Postura**
```python
def analisar_postura(landmarks, h, w):
    # Verifica simetria dos ombros
    # Calcula inclinação das costas
    # Detecta cabeça projetada
    # Identifica quedas
```

**3. Detecção de Exercício**
```python
def detectar_exercicio(landmarks, h, w):
    # Calcula ângulo do cotovelo
    # Máquina de estados: UP/DOWN
    # Incrementa contador na transição
```

---

### 2. 🚧 **safety_zone_tracker.py** - Sistema de Zona de Segurança

Sistema de monitoramento de áreas permitidas/proibidas.

#### 🎯 Funcionalidades

✅ **Definição de Zonas Interativa**
- Desenhe zonas proibidas (vermelho) com o mouse
- Desenhe zonas permitidas (verde) com o mouse
- Clique e arraste para criar retângulos

✅ **Detecção de Violações**
- Verifica 5 pontos-chave do corpo
- Alerta visual grande e vermelho
- Alerta sonoro (beep) a cada segundo
- Contador de violações

✅ **Mapa de Calor**
- Registra áreas visitadas pela pessoa
- Visualização colorida (azul → vermelho)
- Toggle on/off com tecla 'h'
- Útil para análise de padrões de movimento

✅ **Histórico de Violações**
- Registra timestamp de cada violação
- Identifica quais zonas foram violadas
- Exibe últimas 10 violações ao finalizar

✅ **Múltiplas Zonas**
- Suporte para N zonas proibidas
- Suporte para N zonas permitidas
- Limpeza de todas as zonas com 'c'

✅ **Screenshots e Estatísticas**
- Salvar evidências com 's'
- Estatísticas em tempo real
- Relatório final ao sair

#### 🎬 Como Usar

```bash
python safety_zone_tracker.py
```

**Fluxo de uso:**
1. Execute o programa
2. Pressione `p` para modo "zona proibida"
3. Clique e arraste na imagem para desenhar retângulo
4. Repita para adicionar mais zonas
5. Pressione `a` para criar zonas permitidas
6. Movimente-se e observe os alertas

**Teclas:**
- `p` - Adicionar zona PROIBIDA (clique e arraste)
- `a` - Adicionar zona PERMITIDA (clique e arraste)
- `c` - Limpar todas as zonas
- `h` - Toggle mapa de calor
- `s` - Screenshot
- `q` - Sair

#### 📊 Casos de Uso

**1. Segurança Industrial**
- Definir áreas perigosas perto de máquinas
- Alertar quando operador se aproxima demais
- Registrar violações para auditoria

**2. Controle de Acesso**
- Zonas restritas em armazéns
- Áreas VIP em eventos
- Monitoramento de perímetro

**3. Análise de Comportamento**
- Mapa de calor mostra áreas mais visitadas
- Otimização de layout de loja
- Análise ergonômica de estação de trabalho

**4. Monitoramento de Pacientes**
- Zona permitida: área segura
- Zona proibida: escadas, saídas
- Alerta se paciente sair da área segura

#### 🔬 Algoritmos Implementados

**1. Verificação de Ponto em Zona**
```python
def ponto_em_zona(ponto, zona):
    # Verifica se (x,y) está dentro do retângulo
    # x1 <= x <= x2 and y1 <= y <= y2
```

**2. Detecção de Violação Multi-Ponto**
```python
def verificar_violacao(landmarks, h, w):
    # Testa 5 pontos do corpo (nariz, ombros, quadril)
    # Se qualquer um está em zona proibida → violação
    # Retorna: bool e lista de zonas violadas
```

**3. Mapa de Calor Gaussiano**
```python
def atualizar_mapa_calor(landmarks, h, w):
    # Calcula centro do corpo (entre ombros)
    # Adiciona círculo gaussiano no mapa
    # Acumula ao longo do tempo
```

**4. Callback de Mouse**
```python
def mouse_callback(event, x, y, flags, param):
    # LBUTTONDOWN: inicia zona
    # LBUTTONUP: finaliza zona
    # Normaliza coordenadas e adiciona à lista
```

---

## 🔥 Comparação com Arquivos Existentes

| Aspecto | body_track.py | debug_version.py | **postura_analyzer.py** | **safety_zone_tracker.py** |
|---------|---------------|------------------|------------------------|---------------------------|
| **Objetivo** | Demo básico | Alta performance | Análise de postura | Monitoramento de zona |
| **Complexidade** | Baixa | Média | Alta | Alta |
| **Funcionalidades** | 1 (distância) | 2 (tracking + CSV) | 7+ recursos | 6+ recursos |
| **Interface** | Básica | Simples | Profissional | Profissional |
| **Interatividade** | Nenhuma | Teclas básicas | Teclas + reset | Mouse + teclas |
| **Alertas** | Nenhum | Nenhum | Visual + queda | Visual + sonoro |
| **Análise** | Nenhuma | Velocidade | Postura completa | Violações + calor |
| **Estatísticas** | Não | CSV | Tempo real | Tempo real + histórico |
| **Casos de uso** | Aprendizado | Debug/análise | Fisioterapia/Ergonomia | Segurança/Controle |

---

## 🎓 Conceitos Técnicos Novos

### 1. Análise de Geometria Corporal

**Ângulo entre Pontos:**
```python
# Útil para detectar flexão de articulações
angulo = calcular_angulo(ombro, cotovelo, pulso)
if angulo < 90:  # Braço flexionado
    estado = "DOWN"
```

**Distância Euclidiana:**
```python
# Medir deslocamento entre frames
dist = sqrt((x2-x1)² + (y2-y1)²)
velocidade = dist / delta_time
```

### 2. Máquina de Estados

**Contador de Exercícios:**
```
Estado: UP → angulo < 90° → Estado: DOWN
Estado: DOWN → angulo > 160° → Estado: UP (contador++)
```

Evita contar múltiplas vezes o mesmo movimento.

### 3. Detecção de Eventos

**Queda:**
```python
if nariz_y > quadril_y + threshold:
    evento = "QUEDA_DETECTADA"
```

**Violação de Zona:**
```python
for ponto in pontos_chave:
    if ponto in zona_proibida:
        evento = "VIOLACAO"
```

### 4. Mapa de Calor Acumulativo

```python
# A cada frame, adiciona gaussiana no mapa
cv2.circle(mapa_calor, centro, raio, valor, -1)

# Normalizar para visualização
mapa_norm = cv2.normalize(mapa, None, 0, 255, NORM_MINMAX)
mapa_color = cv2.applyColorMap(mapa_norm, COLORMAP_JET)
```

### 5. Callback de Mouse

```python
cv2.setMouseCallback('janela', funcao_callback)

def funcao_callback(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        # Mouse pressionado
    elif event == cv2.EVENT_LBUTTONUP:
        # Mouse solto
```

---

## 🚀 Instalação e Dependências

### Dependências Comuns
```bash
pip install pyrealsense2 opencv-python mediapipe numpy
```

### Dependência Extra (safety_zone_tracker)
```bash
# winsound já vem com Python no Windows
# Para alertas sonoros
```

---

## 🎯 Guia de Uso Rápido

### Para Análise de Postura (Fisioterapia/Ergonomia)

```bash
# 1. Executar
python postura_analyzer.py

# 2. Posicionar-se na frente da câmera
# 3. Observar alertas de postura
# 4. Fazer flexões para testar contador
# 5. Pressionar 's' para screenshot de evidência
```

**Dica:** Coloque a câmera na lateral para melhor análise de costas.

### Para Monitoramento de Zona (Segurança)

```bash
# 1. Executar
python safety_zone_tracker.py

# 2. Pressionar 'p' e desenhar zona proibida
# 3. Adicionar mais zonas conforme necessário
# 4. Movimentar-se e observar alertas
# 5. Pressionar 'h' para ver mapa de calor
# 6. Pressionar 'q' para ver relatório final
```

**Dica:** Defina múltiplas zonas pequenas para maior precisão.

---

## 📊 Exemplos de Saída

### postura_analyzer.py
```
======================================================================
ANALISADOR DE POSTURA CORPORAL
======================================================================
✓ Detecção de má postura
✓ Análise de simetria
✓ Detecção de quedas
✓ Contador de exercícios
======================================================================

[Ao finalizar]
======================================================================
ESTATÍSTICAS FINAIS
======================================================================
⏱️  Tempo total: 125.3s
🏋️  Flexões detectadas: 23
📊 Frames processados: 3759
======================================================================
```

### safety_zone_tracker.py
```
======================================================================
SISTEMA DE ZONA DE SEGURANÇA
======================================================================
✓ Defina zonas proibidas (vermelho) e permitidas (verde)
✓ Alertas visuais e sonoros
✓ Mapa de calor de movimento
✓ Histórico de violações
======================================================================

Modo: Desenhar zona PROIBIDA (clique e arraste)
✓ Zona proibida adicionada: (150, 200, 400, 450)
⚠️ Violação #1 detectada!
⚠️ Violação #2 detectada!

[Ao finalizar]
======================================================================
ESTATÍSTICAS FINAIS
======================================================================
⏱️  Tempo total: 245.7s
⚠️  Total de violações: 12
👤 Pessoas detectadas: 2456
🚫 Zonas proibidas definidas: 3
✅ Zonas permitidas definidas: 1

Histórico de violações:
  1. T=12.3s - Zonas: [0]
  2. T=45.1s - Zonas: [0, 2]
  3. T=78.9s - Zonas: [1]
  ...
======================================================================
```

---

## 🐛 Solução de Problemas

### Problema: FPS muito baixo

**Solução para postura_analyzer:**
```python
# Reduzir model_complexity
model_complexity=0  # Ao invés de 1
```

**Solução para safety_zone_tracker:**
```python
# Desabilitar mapa de calor por padrão
mostrar_mapa_calor = False
```

### Problema: Alerta sonoro não funciona

**Causa:** `winsound` só funciona no Windows

**Solução:**
```python
# Comente a linha do beep
# winsound.Beep(1000, 200)

# Ou use alternativa multiplataforma:
import os
os.system('beep')  # Linux
os.system('say beep')  # Mac
```

### Problema: Contador de flexões não funciona

**Causa:** Ângulo dos braços não varia suficiente

**Solução:**
```python
# Ajustar thresholds
if angulo < 100:  # Ao invés de 90
    ...
elif angulo > 150:  # Ao invés de 160
    ...
```

### Problema: Zonas não ficam persistentes

**Causa:** Clique muito rápido (click ao invés de drag)

**Solução:**
- Pressione, segure, arraste, solte o mouse
- Evite apenas clicar

---

## 🎓 Sugestões de Melhorias Futuras

### Para postura_analyzer.py

1. **Exportar relatório PDF**
   - Gráficos de evolução da postura ao longo do tempo
   - Screenshots timestamped
   - Recomendações personalizadas

2. **Perfis de usuário**
   - Salvar dados históricos por pessoa
   - Comparar sessões
   - Metas de correção postural

3. **Exercícios guiados**
   - Sequências de alongamento
   - Feedback em tempo real
   - Contador de séries e repetições

4. **Integração com wearables**
   - Combinar com dados de smartwatch
   - Alertas no celular
   - Sincronização com apps de saúde

### Para safety_zone_tracker.py

1. **Zonas circulares e polígonos**
   - Além de retângulos
   - Desenho livre
   - Importar de imagem

2. **Rastreamento multi-pessoa**
   - Identificar cada pessoa com ID
   - Estatísticas por pessoa
   - Alertas personalizados

3. **Integração com alarmes**
   - Enviar email/SMS
   - Acionar sirene
   - Registro em banco de dados

4. **Replay e análise offline**
   - Gravar vídeo com violações
   - Revisão frame-a-frame
   - Geração de relatórios

---

## 📚 Recursos Adicionais

### Documentação MediaPipe
- [Pose Landmarks](https://google.github.io/mediapipe/solutions/pose.html)
- [Drawing Utils](https://google.github.io/mediapipe/solutions/drawing_utils.html)

### Intel RealSense
- [Python API](https://intelrealsense.github.io/librealsense/python_docs/_generated/pyrealsense2.html)
- [Alignment](https://dev.intelrealsense.com/docs/projection-in-intel-realsense-sdk-20)

### OpenCV
- [Mouse Events](https://docs.opencv.org/4.x/d7/dfc/group__highgui.html)
- [Color Maps](https://docs.opencv.org/4.x/d3/d50/group__imgproc__colormap.html)

---

## ✅ Checklist de Validação

### postura_analyzer.py
- [x] Detecta pessoa
- [x] Calcula ângulos corretamente
- [x] Identifica má postura
- [x] Conta flexões
- [x] Detecta quedas
- [x] Interface funcional
- [x] Screenshots salvam

### safety_zone_tracker.py
- [x] Desenha zonas com mouse
- [x] Detecta violações
- [x] Emite alertas
- [x] Mapa de calor funciona
- [x] Histórico registrado
- [x] Estatísticas corretas
- [x] Limpar zonas funciona

---

**Desenvolvido com ❤️ usando Python, RealSense e MediaPipe**

*Perfeito para aplicações de saúde, segurança e monitoramento!* 🎯

