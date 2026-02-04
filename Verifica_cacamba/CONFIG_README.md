# 📋 Documentação do Arquivo de Configuração

O arquivo `config.json` contém todas as configurações do sistema de detecção V3. Este arquivo permite ajustar os parâmetros sem modificar o código.

---

## 🎥 Seção: camera

Configurações da câmera RealSense.

```json
"camera": {
  "resolucao_largura": 640,
  "resolucao_altura": 480,
  "fps": 30,
  "clip_min": 0.1,
  "clip_max": 2.0,
  "laser_potencia": 360
}
```

| Parâmetro | Tipo | Descrição | Valor Padrão | Recomendado |
|-----------|------|-----------|--------------|-------------|
| `resolucao_largura` | int | Largura da imagem em pixels | 640 | 640-1280 |
| `resolucao_altura` | int | Altura da imagem em pixels | 480 | 480-720 |
| `fps` | int | Quadros por segundo | 30 | 30 (melhor estabilidade) |
| `clip_min` | float | Distância mínima de leitura (metros) | 0.1 | 0.1-0.3 |
| `clip_max` | float | Distância máxima de leitura (metros) | 2.0 | 1.5-3.0 |
| `laser_potencia` | int | Potência do laser IR (0=automático) | 360 | 300-360 (máximo) |

**💡 Dica:** Para ambientes com muita poeira, aumente `laser_potencia` para 360 (máximo).

---

## 📏 Seção: medicoes

Parâmetros físicos da instalação.

```json
"medicoes": {
  "altura_camera_chao": 0.725,
  "altura_caixa": 0.20,
  "profundidade_min_caixa": 0.45,
  "profundidade_max_caixa": 0.85,
  "area_minima_pixels": 5000
}
```

| Parâmetro | Tipo | Descrição | Valor Padrão | Como Medir |
|-----------|------|-----------|--------------|------------|
| `altura_camera_chao` | float | Altura da câmera ao chão (metros) | 0.725 | **Meça com trena!** |
| `altura_caixa` | float | Altura da caixa/caçamba (metros) | 0.20 | Altura da borda da caixa |
| `profundidade_min_caixa` | float | Profundidade mínima para detectar caixa | 0.45 | `altura_camera_chao - 0.30` |
| `profundidade_max_caixa` | float | Profundidade máxima para detectar caixa | 0.85 | `altura_camera_chao + 0.15` |
| `area_minima_pixels` | int | Área mínima em pixels para considerar detecção | 5000 | 3000-10000 |

**⚠️ IMPORTANTE:** 
- Meça `altura_camera_chao` com precisão usando uma trena
- `altura_caixa` deve ser a altura da borda (não do conteúdo)
- Ajuste `profundidade_min/max_caixa` se a detecção não funcionar

---

## 🛡️ Seção: protecao_pessoa

Parâmetros para evitar detectar pessoas como conteúdo da caixa.

```json
"protecao_pessoa": {
  "profundidade_minima_corpo": 0.20,
  "area_maxima_corpo": 200000,
  "velocidade_max_mudanca": 0.05,
  "tempo_minimo_entre_mudancas": 1.0
}
```

| Parâmetro | Tipo | Descrição | Valor Padrão | Ajustar Se... |
|-----------|------|-----------|--------------|---------------|
| `profundidade_minima_corpo` | float | Rejeita objetos mais próximos que X metros | 0.20 | Pessoas ainda são detectadas: **AUMENTE** (ex: 0.30) |
| `area_maxima_corpo` | int | Rejeita áreas maiores que X pixels² | 200000 | Pessoas são detectadas: **DIMINUA** (ex: 100000) |
| `velocidade_max_mudanca` | float | Rejeita mudanças maiores que X metros/frame | 0.05 | Sistema oscila muito: **DIMINUA** (ex: 0.03) |
| `tempo_minimo_entre_mudancas` | float | Tempo mínimo entre mudanças de status (segundos) | 1.0 | Muito lento: **DIMINUA** (ex: 0.5) |

**💡 Dica:** Se pessoas na frente ainda são detectadas:
1. Aumente `profundidade_minima_corpo` para 0.25-0.30
2. Diminua `area_maxima_corpo` para 150000

---

## 🎯 Seção: roi

Define a região de interesse (ROI) onde a caixa deve estar localizada.

```json
"roi": {
  "x_min": 0.25,
  "x_max": 0.75,
  "y_min": 0.25,
  "y_max": 0.85
}
```

| Parâmetro | Tipo | Descrição | Valor Padrão | Range |
|-----------|------|-----------|--------------|-------|
| `x_min` | float | Borda esquerda da ROI (0.0 = esquerda total) | 0.25 | 0.0-1.0 |
| `x_max` | float | Borda direita da ROI (1.0 = direita total) | 0.75 | 0.0-1.0 |
| `y_min` | float | Borda superior da ROI (0.0 = topo) | 0.25 | 0.0-1.0 |
| `y_max` | float | Borda inferior da ROI (1.0 = fundo) | 0.85 | 0.0-1.0 |

**📐 Valores são proporcionais:**
- `0.0` = borda esquerda/superior
- `0.5` = centro
- `1.0` = borda direita/inferior

**Exemplo:**
```json
// Caixa no canto inferior esquerdo
"x_min": 0.0,  "x_max": 0.4,
"y_min": 0.6,  "y_max": 1.0

// Caixa centralizada (padrão)
"x_min": 0.25, "x_max": 0.75,
"y_min": 0.25, "y_max": 0.85
```

---

## 🎚️ Seção: thresholds

Limites para determinar quando a caixa está vazia/cheia.

```json
"thresholds": {
  "limite_vazia": 0.70,
  "limite_cheia": 0.55,
  "threshold_binary": 127
}
```

| Parâmetro | Tipo | Descrição | Valor Padrão | Cálculo |
|-----------|------|-----------|--------------|---------|
| `limite_vazia` | float | Distância acima = VAZIA (metros) | 0.70 | `altura_camera_chao - 0.02` |
| `limite_cheia` | float | Distância abaixo = CHEIA (metros) | 0.55 | `(altura_camera_chao - altura_caixa) + 0.02` |
| `threshold_binary` | int | Limite para binarização (0-255) | 127 | 100-150 (meio termo) |

**📊 Como Funciona:**
```
Distância medida >= limite_vazia (0.70m)  → STATUS: VAZIA
Distância medida <= limite_cheia (0.55m)  → STATUS: CHEIA
Entre os dois valores                      → STATUS: PARCIAL
```

**Ajustar:**
- Se detecta VAZIA quando tem pouco conteúdo: **DIMINUA** `limite_vazia`
- Se detecta CHEIA quando tem pouco conteúdo: **DIMINUA** `limite_cheia`

---

## 🔧 Seção: filtros

Parâmetros dos filtros de processamento.

```json
"filtros": {
  "tamanho_historico": 10,
  "historico_distancias": 30,
  "kernel_morph_size": 5,
  "grid_medicao_size": 3
}
```

| Parâmetro | Tipo | Descrição | Valor Padrão | Ajustar Se... |
|-----------|------|-----------|--------------|---------------|
| `tamanho_historico` | int | Quantidade de status armazenados | 10 | Mais estável: **AUMENTE** (15-20) |
| `historico_distancias` | int | Quantidade de distâncias armazenadas | 30 | Mais suave: **AUMENTE** (40-50) |
| `kernel_morph_size` | int | Tamanho do kernel morfológico (pixels) | 5 | Ruído demais: **AUMENTE** (7-9) |
| `grid_medicao_size` | int | Tamanho do grid de medição (NxN) | 3 | Mais preciso: **AUMENTE** (5x5) |

**💡 Explicação:**
- **tamanho_historico:** Quantos frames considerar para estabilizar status
- **historico_distancias:** Histórico de medições de distância
- **kernel_morph_size:** Filtro para limpar ruído na máscara (maior = menos ruído)
- **grid_medicao_size:** Grid 3x3 = 9 pontos de medição, 5x5 = 25 pontos

---

## 🎨 Seção: visualizacao

Configurações da interface visual.

```json
"visualizacao": {
  "mostrar_fps": true,
  "mostrar_grid": true,
  "mostrar_ir": true,
  "colormap": 2
}
```

| Parâmetro | Tipo | Descrição | Valor Padrão | Opções |
|-----------|------|-----------|--------------|--------|
| `mostrar_fps` | bool | Mostra FPS na tela | true | true/false |
| `mostrar_grid` | bool | Mostra grid de medição | true | true/false |
| `mostrar_ir` | bool | Mostra janela IR | true | true/false |
| `colormap` | int | Esquema de cores do mapa de profundidade | 2 | 0-11 (veja tabela) |

**🎨 Colormaps Disponíveis:**

| Valor | Nome | Aparência |
|-------|------|-----------|
| 0 | AUTUMN | 🍂 Laranja/Vermelho |
| 1 | BONE | 💀 Cinza/Branco |
| **2** | **JET** | 🌈 **Azul→Verde→Vermelho (Padrão)** |
| 3 | WINTER | ❄️ Azul/Ciano |
| 4 | RAINBOW | 🌈 Arco-íris |
| 5 | OCEAN | 🌊 Azul oceano |
| 6 | SUMMER | ☀️ Verde/Amarelo |
| 7 | SPRING | 🌸 Rosa/Amarelo |
| 8 | COOL | 🧊 Ciano/Rosa |
| 9 | HSV | 🎨 Matiz saturada |
| 10 | PINK | 💗 Rosa |
| 11 | HOT | 🔥 Preto→Vermelho→Amarelo |

---

## 🔊 Seção: sons

Configurações de alertas sonoros (atualmente não implementado).

```json
"sons": {
  "beep_mudanca_status": true,
  "beep_frequencia": 1000,
  "beep_duracao": 200
}
```

| Parâmetro | Tipo | Descrição | Valor Padrão |
|-----------|------|-----------|--------------|
| `beep_mudanca_status` | bool | Emitir beep ao mudar status | true |
| `beep_frequencia` | int | Frequência do beep (Hz) | 1000 |
| `beep_duracao` | int | Duração do beep (ms) | 200 |

**⚠️ Nota:** Recurso reservado para implementação futura.

---

## 🚀 Exemplos de Configuração

### Cenário 1: Câmera Alta (1.5m) com Caixa Grande (50cm)

```json
{
  "medicoes": {
    "altura_camera_chao": 1.50,
    "altura_caixa": 0.50,
    "profundidade_min_caixa": 1.20,
    "profundidade_max_caixa": 1.65
  },
  "thresholds": {
    "limite_vazia": 1.48,
    "limite_cheia": 1.02
  }
}
```

### Cenário 2: Ambiente com Muita Interferência

```json
{
  "camera": {
    "laser_potencia": 360
  },
  "protecao_pessoa": {
    "profundidade_minima_corpo": 0.30,
    "velocidade_max_mudanca": 0.03
  },
  "filtros": {
    "tamanho_historico": 20,
    "kernel_morph_size": 7
  }
}
```

### Cenário 3: Detecção Ultra-Rápida

```json
{
  "protecao_pessoa": {
    "tempo_minimo_entre_mudancas": 0.3
  },
  "filtros": {
    "tamanho_historico": 5
  }
}
```

---

## 🛠️ Solução de Problemas

### Problema: Pessoas são detectadas como caixa cheia

**Solução:**
```json
"protecao_pessoa": {
  "profundidade_minima_corpo": 0.30,  // ← AUMENTAR
  "area_maxima_corpo": 150000,        // ← DIMINUIR
  "velocidade_max_mudanca": 0.03      // ← DIMINUIR
}
```

### Problema: Status oscila muito (instável)

**Solução:**
```json
"protecao_pessoa": {
  "tempo_minimo_entre_mudancas": 2.0  // ← AUMENTAR
},
"filtros": {
  "tamanho_historico": 20,            // ← AUMENTAR
  "historico_distancias": 50          // ← AUMENTAR
}
```

### Problema: Não detecta a caixa

**Solução:**
```json
"medicoes": {
  "profundidade_min_caixa": 0.30,     // ← Ajustar range
  "profundidade_max_caixa": 1.00,
  "area_minima_pixels": 3000          // ← DIMINUIR
},
"roi": {
  "x_min": 0.0,                       // ← Expandir ROI
  "x_max": 1.0,
  "y_min": 0.0,
  "y_max": 1.0
}
```

### Problema: Muitos falsos positivos (ruído)

**Solução:**
```json
"filtros": {
  "kernel_morph_size": 9,             // ← AUMENTAR
  "grid_medicao_size": 5              // ← AUMENTAR (mais pontos)
},
"medicoes": {
  "area_minima_pixels": 8000          // ← AUMENTAR
}
```

---

## 📝 Como Editar o Arquivo

1. **Abra** `config.json` com qualquer editor de texto
2. **Modifique** os valores desejados
3. **Salve** o arquivo
4. **Reinicie** o programa para aplicar as mudanças

**⚠️ Atenção:** 
- Use ponto (`.`) para decimais, não vírgula
- Booleanos: `true` ou `false` (minúsculas)
- Não remova vírgulas ou chaves `{}`

---

## 🔄 Restaurar Configurações Padrão

Se algo der errado, simplesmente **delete** o arquivo `config.json`. O programa criará um novo com valores padrão na próxima execução.

---

**📅 Última atualização:** 2026-02-03  
**🔖 Versão:** V3

