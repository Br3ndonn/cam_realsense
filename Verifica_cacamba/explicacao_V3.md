# Sistema de Detecção de Nível V3 - Documentação Técnica

## 🚀 Visão Geral

O **verificar_caixaV3.py** é a versão mais avançada e robusta do sistema de detecção de nível de caixas/caçambas. Combina as melhores técnicas das versões anteriores e adiciona inovações significativas.

---

## 🎯 Principais Inovações da V3

### 1. **Detecção por Segmentação de Profundidade**
❌ **V1/V2:** Detectavam bordas visuais (afetadas por iluminação)  
✅ **V3:** Segmenta objetos por profundidade (independente de iluminação)

### 2. **Sistema de Grid 3x3 para Medição**
❌ **V1/V2:** Mediam a região inteira de uma vez  
✅ **V3:** Divide em 9 células e calcula mediana das medianas (super robusto!)

### 3. **Filtro Temporal com Histórico**
❌ **V1/V2:** Status mudava instantaneamente (instável)  
✅ **V3:** Status só muda se 70% do histórico concordar (estável)

### 4. **Triple Stream (RGB + IR + Depth)**
❌ **V1/V2:** Usavam 2 streams  
✅ **V3:** Usa 3 streams simultaneamente para máxima versatilidade

### 5. **Estatísticas em Tempo Real**
❌ **V1/V2:** Informações básicas  
✅ **V3:** FPS, confiança, histórico, área, contador de frames

### 6. **Visualização Profissional**
❌ **V1/V2:** Interface simples  
✅ **V3:** 3 janelas com painéis, barra de confiança, overlay de grid

---

## 🧠 Arquitetura Técnica

### Pipeline de Processamento

```
┌─────────────────────────────────────────────────────────────┐
│                    CAPTURA DE FRAMES                         │
│  RGB Color + Infrared + Depth (640x480 @ 30fps)            │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────┐
│              APLICAÇÃO DE FILTROS CASCATA                    │
│  Decimation → Spatial → Temporal → Hole Filling             │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────┐
│         SEGMENTAÇÃO POR PROFUNDIDADE                         │
│  Máscara: 0.45m < profundidade < 0.85m                     │
│  Operações morfológicas: Close → Open                       │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────┐
│           DETECÇÃO DE CONTORNOS                              │
│  findContours → Filtrar por área > 5000px                   │
│  Selecionar maior contorno válido                           │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────┐
│              MEDIÇÃO EM GRID 3x3                             │
│  9 células independentes                                     │
│  Mediana de cada célula                                      │
│  Mediana das 9 medianas = resultado final                   │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────┐
│           ESTABILIZAÇÃO TEMPORAL                             │
│  Histórico de 10 frames                                      │
│  Status final = maioria dos últimos 10 frames               │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────┐
│        CÁLCULO DE MÉTRICAS E VISUALIZAÇÃO                    │
│  Altura, percentual, confiança, FPS                         │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔬 Detalhamento das Técnicas Avançadas

### 1. Segmentação por Profundidade

**Conceito:**
Ao invés de procurar bordas visuais (que dependem de iluminação), segmentamos objetos pela distância da câmera.

**Implementação:**
```python
depth_meters = depth_image * depth_scale

# Criar máscara: objetos entre 45cm e 85cm
mask_roi = (depth_meters > 0.45) & (depth_meters < 0.85)
```

**Por que funciona melhor?**
- ✅ Não depende de iluminação (funciona no escuro total)
- ✅ Não é afetado por cores ou texturas
- ✅ Separa objetos por "camadas" de profundidade
- ✅ Robusto contra sombras e reflexos

### 2. Operações Morfológicas

**Close (Fechamento):**
```python
cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
```
- Remove pequenos buracos dentro da região
- Conecta partes separadas por pequenos gaps
- Útil quando poeira "fura" a detecção

**Open (Abertura):**
```python
cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
```
- Remove pequenos objetos isolados (ruído)
- Suaviza bordas irregulares
- Elimina falsos positivos

**Ordem importa:** Close primeiro (une), Open depois (limpa)

### 3. Medição em Grid 3x3

**Por que dividir em células?**

Imagine uma caixa com:
- Canto esquerdo: objeto até 15cm
- Centro: objeto até 10cm  
- Canto direito: objeto até 18cm

**Abordagem antiga (média simples):**
```
Média = (15 + 10 + 18) / 3 = 14.33cm
```
Resultado impreciso se houver outliers.

**Abordagem V3 (grid + mediana dupla):**
```
Célula 1 (esquerda): mediana = 15cm
Célula 2 (centro): mediana = 10cm
Célula 3 (direita): mediana = 18cm
Célula 4-9: ... (outros valores)

Resultado final: mediana([15, 10, 18, ...]) = valor robusto
```

**Vantagens:**
- ✅ Cada célula elimina outliers locais
- ✅ Mediana global elimina células anômalas
- ✅ Dupla proteção contra ruído
- ✅ Medição mais precisa em superfícies irregulares

**Visualização:**
```
┌─────┬─────┬─────┐
│  1  │  2  │  3  │  Cada célula calcula
├─────┼─────┼─────┤  sua própria mediana
│  4  │  5  │  6  │  
├─────┼─────┼─────┤  Depois: mediana das 9
│  7  │  8  │  9  │
└─────┴─────┴─────┘
```

### 4. Estabilização Temporal (Filtro de Maioria)

**Problema:** Medições oscilam frame a frame
```
Frame 1: VAZIA
Frame 2: PARCIAL (ruído!)
Frame 3: VAZIA
Frame 4: VAZIA
```

**Solução V3:** Histórico de decisões
```python
historico_status = deque(maxlen=10)  # Últimos 10 frames
historico_status.append(status_atual)

# Contar votos
votos = {
    "VAZIA": historico_status.count("VAZIA"),
    "PARCIAL": historico_status.count("PARCIAL"),
    "CHEIA": historico_status.count("CHEIA")
}

# Status final = maioria
status_estavel = max(votos, key=votos.get)
```

**Resultado:**
- Se 7/10 frames dizem "VAZIA" → status = VAZIA
- Se 6/10 dizem "PARCIAL" → status = PARCIAL
- Elimina oscilações causadas por ruído

**Configurável:**
```python
TAMANHO_HISTORICO = 10  # Aumentar = mais estável, mais lento
                         # Diminuir = mais rápido, menos estável
```

### 5. Cálculo de Confiança

**Métrica:** Desvio padrão das medições recentes

```python
desvio_padrao = np.std(historico_distancias)
confianca = 100 - (desvio_padrao * 1000)
```

**Interpretação:**
- **Confiança > 70%** (verde): Medições estáveis, resultado confiável
- **Confiança 40-70%** (laranja): Medições oscilando, cuidado
- **Confiança < 40%** (vermelho): Medições muito instáveis, resultado duvidoso

**Por que importa:**
- Você sabe quando confiar na medição
- Útil para alertas automáticos (só acionar se confiança > 80%)
- Detecta problemas (poeira, vibração, objeto em movimento)

---

## 🎨 Interface Visual Detalhada

### Janela 1: "Sistema de Deteccao V3" (Principal)

**Painel Superior (preto):**
```
┌────────────────────────────────────────────┐
│ STATUS: PARCIAL                            │ ← Grande, colorido
│ Dist: 0.625m (9 pts)                      │ ← Detalhes da medição
│ CAIXA DETECTADA                            │ ← Modo de detecção
│ Altura: 10.0cm | 50%                       │ ← Resultado
└────────────────────────────────────────────┘
```

**Painel Lateral Direito (preto):**
```
┌──────────────────┐
│ ESTATISTICAS     │
│ Confianca: 85%   │ ← Qualidade da medição
│ FPS: 28.5        │ ← Performance
│ Frames: 1247     │ ← Contador
│ Area: 12450px²   │ ← Tamanho da caixa
│ Historico: 10/10 │ ← Buffer cheio
│ ████████░░░░░░   │ ← Barra de confiança
└──────────────────┘
```

**Região Central:**
- 🟡 Contorno amarelo: polígono detectado
- 🟣 Retângulo magenta: bounding box
- 🟩🟧🟥 Retângulo grosso colorido: status
- ⬜ Mini-retângulos: grid 3x3 de medição

**Rodapé:**
```
Pressione 'q' para sair | V3 - Deteccao Hibrida
```

### Janela 2: "Mapa de Profundidade - V3"

- Mapa de calor (JET colormap)
- Azul = longe, Vermelho = perto
- Contorno branco sobreposto na caixa detectada
- Blend 70/30 para ver o mapa + detecção

### Janela 3: "Visao Infravermelho"

- Feed do sensor IR em escala de cinza
- Texto: "VISAO IR (Funciona no Escuro)"
- Prova visual de que funciona sem luz

---

## 📊 Comparação: V1 vs V2 vs V3

| Aspecto | V1 (verificar_caixa) | V2 (verificar_caixaV2) | V3 (verificar_caixaV3) |
|---------|---------------------|----------------------|----------------------|
| **Detecção** | Bordas IR + contornos | Bordas RGB + contornos | Segmentação por profundidade |
| **Iluminação** | Funciona no escuro (IR) | Precisa de luz (RGB) | Funciona no escuro (IR+RGB) |
| **Medição** | Mediana simples | Mediana de região | Grid 3x3 + dupla mediana |
| **Estabilidade** | Sem filtro temporal | Sem filtro temporal | Histórico de 10 frames |
| **Confiança** | Não calcula | Não calcula | Métrica de desvio padrão |
| **Visualização** | 2 janelas básicas | 2 janelas + info | 3 janelas profissionais |
| **Estatísticas** | Nenhuma | Básicas | FPS, frames, confiança, área |
| **Filtros** | Spatial + Temporal | Spatial + Temporal | +Decimation +Hole Filling |
| **Robustez** | Alta | Média | Muito Alta |
| **Performance** | ~30 FPS | ~30 FPS | ~25-28 FPS (mais processamento) |
| **Complexidade** | Média | Baixa | Alta |
| **Melhor para** | Ambientes industriais escuros | Testes rápidos bem iluminados | Aplicações profissionais críticas |

---

## ⚙️ Parâmetros Configuráveis

### Alturas e Distâncias
```python
ALTURA_CAMERA_CHAO = 0.725  # Medir com trena
ALTURA_CAIXA = 0.20         # Altura real da caixa
TOLERANCIA = 0.03           # Margem de erro (3cm)
```

### Filtros de Profundidade
```python
CLIP_MIN = 0.3              # Ignora objetos < 30cm
CLIP_MAX = 1.5              # Ignora objetos > 150cm
PROFUNDIDADE_MIN_CAIXA = 0.45  # Camada mínima da caixa
PROFUNDIDADE_MAX_CAIXA = 0.85  # Camada máxima da caixa
```

### Detecção
```python
AREA_MINIMA_PIXELS = 5000   # Área mínima do contorno
```

### Estabilização
```python
TAMANHO_HISTORICO = 10      # Frames no histórico (5-20 recomendado)
```

### Spatial Filter
```python
spatial.set_option(rs.option.filter_magnitude, 2)      # 1-5
spatial.set_option(rs.option.filter_smooth_alpha, 0.5) # 0.0-1.0
spatial.set_option(rs.option.filter_smooth_delta, 20)  # 1-50
```

### Temporal Filter
```python
temporal.set_option(rs.option.filter_smooth_alpha, 0.4) # 0.0-1.0
temporal.set_option(rs.option.filter_smooth_delta, 20)  # 1-50
```

---

## 🎓 Conceitos para Explicar

### 1. Por que Segmentação por Profundidade é Superior?

**Analogia:** 
Imagine que você está em uma sala escura procurando uma caixa.

- **Detecção por bordas (V1/V2):** Você usa uma lanterna e procura as linhas da caixa. Se estiver escuro demais, não vê nada.
- **Detecção por profundidade (V3):** Você estica os braços e detecta o que está perto vs longe. Funciona no escuro total!

### 2. Grid 3x3: Mediana da Mediana

**Analogia:**
Você quer saber a altura média de um grupo, mas tem 3 mentirosos.

- **Média simples:** Os mentirosos distorcem o resultado
- **Mediana:** Ordena e pega o valor do meio, ignora extremos
- **Grid 3x3 + dupla mediana:** Primeiro elimina mentirosos locais, depois globais

### 3. Histórico Temporal

**Analogia:**
Você assiste 10 vídeos de uma pessoa e em 9 ela está sorrindo, em 1 ela está séria.
- **Conclusão V1/V2:** "Ela mudou de humor!" (instável)
- **Conclusão V3:** "Ela está feliz, aquele frame sério foi atípico" (estável)

### 4. Confiança Baseada em Desvio

**Analogia:**
- **Baixo desvio (alta confiança):** Você sempre chega ao trabalho entre 8:58 e 9:02 → padrão previsível
- **Alto desvio (baixa confiança):** Você chega entre 8:00 e 10:00 → padrão imprevisível

---

## 🚀 Como Usar

### Instalação
```bash
pip install pyrealsense2 opencv-python numpy
```

### Execução
```bash
python verificar_caixaV3.py
```

### Calibração

1. **Medir altura da câmera:**
   - Use uma trena do chão até a lente
   - Atualize `ALTURA_CAMERA_CHAO`

2. **Medir altura da caixa:**
   - Meça com régua
   - Atualize `ALTURA_CAIXA`

3. **Ajustar camadas de profundidade:**
   - Execute o programa
   - Observe o mapa de profundidade
   - Ajuste `PROFUNDIDADE_MIN_CAIXA` e `PROFUNDIDADE_MAX_CAIXA` se necessário

4. **Testar estabilidade:**
   - Se status oscilar muito: aumente `TAMANHO_HISTORICO`
   - Se resposta muito lenta: diminua `TAMANHO_HISTORICO`

---

## 🐛 Troubleshooting

### Problema: Não detecta a caixa
**Soluções:**
- Diminuir `AREA_MINIMA_PIXELS` (de 5000 para 3000)
- Ajustar `PROFUNDIDADE_MIN_CAIXA` e `PROFUNDIDADE_MAX_CAIXA`
- Verificar se a caixa está na faixa de profundidade esperada

### Problema: Confiança sempre baixa
**Soluções:**
- Aumentar potência do laser (já no máximo no código)
- Estabilizar a câmera (vibração causa oscilações)
- Melhorar iluminação (ajuda o processamento)
- Aumentar `TAMANHO_HISTORICO` para suavizar mais

### Problema: FPS muito baixo (< 20)
**Soluções:**
- Reduzir resolução: `640x480` → `424x240`
- Remover janela de IR se não usar
- Diminuir `grid_size` de 3 para 2 (grid 2x2)
- Comentar `hole_filling` filter

### Problema: Status muda muito lentamente
**Soluções:**
- Diminuir `TAMANHO_HISTORICO` de 10 para 5
- Ajustar lógica de maioria para 60% ao invés de 70%

---

## 🎯 Casos de Uso Reais

### 1. Linha de Produção Industrial
- **Cenário:** Caixas passam em esteira, precisa saber se estão cheias
- **V3 vantagens:** 
  - Estabilização temporal evita falsos positivos
  - Funciona com iluminação variável
  - Confiança indica se pode tomar decisão automatizada

### 2. Caçambas de Caminhão
- **Cenário:** Monitorar nível de carga em caminhões
- **V3 vantagens:**
  - IR funciona à noite
  - Grid 3x3 lida com carga irregular
  - Robusto contra poeira

### 3. Silos e Tanques
- **Cenário:** Medir nível de materiais a granel
- **V3 vantagens:**
  - Medição por profundidade não depende de cor/textura
  - Histórico temporal filtra movimentação do material
  - Confiança detecta problemas de medição

---

## 📈 Melhorias Futuras Possíveis

### 1. Machine Learning para Classificação
- Treinar CNN para identificar tipos de objetos na caixa
- YOLO para detectar múltiplas caixas simultaneamente

### 2. Tracking Multi-Objeto
- Rastrear múltiplas caixas com IDs únicos
- Útil para linhas de produção com várias estações

### 3. Integração IoT
- Enviar dados para servidor (MQTT/HTTP)
- Dashboard web em tempo real
- Alertas por email/SMS

### 4. Calibração Automática
- Detectar automaticamente altura da câmera
- Aprender dimensões da caixa por observação

### 5. Predição de Tendências
- Usar histórico longo para prever quando ficará cheia
- ML time series (LSTM) para estimar tempo restante

---

## 📝 Conclusão

A **V3** é a versão mais completa e profissional do sistema:

✅ **Mais robusta:** Detecção por profundidade  
✅ **Mais precisa:** Grid 3x3 + dupla mediana  
✅ **Mais estável:** Histórico temporal  
✅ **Mais confiável:** Métrica de confiança  
✅ **Mais informativa:** Estatísticas em tempo real  
✅ **Mais versátil:** 3 streams (RGB+IR+Depth)  

**Recomendação de uso:**
- **V1:** Ambientes industriais escuros com poeira
- **V2:** Testes rápidos e prototipagem
- **V3:** Aplicações profissionais críticas que exigem máxima confiabilidade

---

**Última atualização:** 30 Janeiro 2026  
**Versão:** 3.0  
**Autor:** Sistema Avançado de Visão Computacional

