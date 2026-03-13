# Avanços da Versão 5 em relação à Versão 4
## Sistema de Detecção de Nível da Caçamba — Câmera RealSense D4xx

---

## 1. Contexto

A Versão 4 (V4) introduziu uma interface gráfica completa com Tkinter e processamento em background via threads, representando um grande salto em usabilidade em relação às versões anteriores baseadas em terminal. No entanto, a análise do código-fonte revelou falhas críticas de corretude e de desempenho que comprometiam a confiabilidade do sistema em uso real. A Versão 5 (V5) foi desenvolvida com o objetivo de corrigir essas falhas de forma estrutural, antes de adicionar novas funcionalidades.

---

## 2. Correções de Bugs Críticos

### 2.1 Violação de Thread Safety (bug crítico)

**Problema na V4:**  
A thread de processamento da câmera acessava diretamente os widgets da interface gráfica Tkinter para ler os parâmetros de configuração:

```python
# V4 — executado dentro da thread da câmera (incorreto)
ALTURA_CAMERA_CHAO = float(self.config_widgets['altura_camera_chao'].get())
LIMITE_VAZIA = float(self.config_widgets['limite_vazia'].get())
```

O Tkinter **não é thread-safe**: acessar widgets fora da thread principal produz comportamento indefinido, podendo causar travamentos silenciosos, crashes ou leituras corrompidas de parâmetros.

Além disso, variáveis de estado compartilhadas entre as threads (`frame_atual`, `status_atual`, `distancia_atual`) eram escritas pela thread da câmera e lidas pela thread da GUI **sem nenhum mecanismo de sincronização**.

**Solução na V5:**  
Toda a comunicação entre threads é feita exclusivamente via `queue.Queue`, que é a única estrutura de dados thread-safe nativa do Python para esse fim:

- `data_queue` (câmera → GUI): transporta frames processados, logs e eventos de controle.
- `cmd_queue` (GUI → câmera): transporta atualizações de configuração em tempo real.

A thread da câmera nunca acessa nenhum widget. Os parâmetros são lidos de um snapshot do dicionário de configuração (`copy.deepcopy`), atualizado com lock explícito (`threading.Lock`) somente pela thread da GUI.

---

### 2.2 Proteções contra Detecção de Pessoas — Implementação Ausente na V4

**Problema na V4:**  
A documentação da V4 descreve 6 proteções contra falsos positivos causados pela presença de pessoas no campo de visão (ROI, aspect ratio, profundidade mínima, área máxima, velocidade de mudança e filtro temporal). Porém, o código-fonte da V4 **não implementava essas validações** no loop principal. A seleção do contorno era feita apenas por área:

```python
# V4 — sem validação de ROI, aspect ratio ou profundidade
if area > AREA_MINIMA_PIXELS and area > maior_area:
    maior_area = area
    melhor_contorno = contour
    caixa_detectada = True
```

Isso tornava o sistema suscetível a detectar membros do corpo humano como se fossem a caçamba.

**Solução na V5:**  
O método `_validar_deteccao()` foi reintroduzido e integrado ao loop de seleção de contornos, aplicando 4 filtros em cascata antes de aceitar qualquer candidato:

| Filtro | Critério | Objetivo |
|--------|----------|----------|
| Aspect ratio | `max(w,h) / min(w,h) < 5` | Rejeita braços e pernas (objetos alongados) |
| ROI normalizada | Centro do contorno dentro de `[x_min, x_max] × [y_min, y_max]` | Rejeita detecções fora da área esperada da caçamba |
| Profundidade mínima | Mediana dos pixels > `profundidade_minima_corpo` (0,20 m) | Rejeita objetos muito próximos da câmera |
| Área máxima | `area < area_maxima_corpo` (200.000 px²) | Rejeita corpos humanos inteiros |

---

### 2.3 Cálculo de Confiança Incorreto

**Problema na V4:**  
A confiança média era calculada como:

```python
confianca_media = np.mean([self.confianca_atual])  # lista com 1 elemento
```

Isso sempre retornava o valor instantâneo do frame atual, não uma média real ao longo do tempo.

**Solução na V5:**  
Um `deque(maxlen=30)` mantém o histórico das últimas 30 leituras de confiança. O método `confianca_media()` retorna `np.mean` sobre esse histórico, refletindo a estabilidade real da detecção ao longo do tempo.

---

### 2.4 Contaminação do Histórico de Distâncias

**Problema na V4/V5 inicial:**  
Quando nenhuma caçamba era detectada, o sistema media a região central do frame como fallback e adicionava esse valor ao histórico de distâncias. Isso distorcia o desvio padrão usado no cálculo de confiança.

**Solução na V5:**  
O método `processar_frame()` retorna imediatamente com `ResultadoDeteccao(status="SEM LEITURA")` quando nenhum contorno válido é encontrado, **sem adicionar nenhum valor ao histórico**. A confiança reflete apenas frames em que a caçamba foi efetivamente detectada.

---

## 3. Melhorias de Desempenho

A V4 apresentava travamentos frequentes da interface. Quatro causas foram identificadas e corrigidas:

### 3.1 Sobrecarga da Thread da GUI

**V4:** `root.after(0, atualizar_gui)` era chamado a cada frame (30 vezes/segundo), incluindo o redesenho completo do gráfico Canvas a cada chamada. A fila de eventos do Tkinter saturava progressivamente.

**V5:** A GUI é atualizada a no máximo 15 FPS via `root.after(66ms, _poll_queue)`. Adicionalmente, `_poll_queue` processa no máximo **1 mensagem de frame por tick** — mensagens leves (logs, controle) são drenadas normalmente, mas o trabalho pesado (resize de imagem, redesenho de canvas) é limitado a 1 execução por ciclo de 66ms.

### 3.2 Processamento de Frames Descartados

**V4/V5 inicial:** Os overlays visuais (cvtColor, applyColorMap, resize) eram calculados para todos os frames, mesmo aqueles que seriam descartados por fila cheia.

**V5:** Antes de qualquer processamento visual, a thread da câmera verifica `data_queue.full()`. Se a fila já está cheia, o frame é descartado imediatamente, sem computar overlays.

### 3.3 Filtro de Redimensionamento de Imagem

**V4/V5 inicial:** `Image.Resampling.LANCZOS` (o filtro de maior qualidade do PIL) era aplicado 2 vezes por frame para redimensionar os painéis de vídeo.

**V5:** Substituído por `Image.Resampling.BILINEAR`, aproximadamente 4× mais rápido, sem diferença visual perceptível em vídeo ao vivo.

### 3.4 Gráfico Canvas com N Chamadas Individuais

**V4/V5 inicial:** O gráfico de distância era desenhado criando até 149 objetos `Line` individuais no canvas Tkinter, cada um com overhead de alocação no interpretador Tcl/Tk.

**V5:** Substituído por uma única chamada `create_line(*flat_pts)` que recebe todos os pontos como argumento, reduzindo o custo do redesenho de O(n) chamadas para O(1).

---

## 4. Refatoração Arquitetural

A V4 era um arquivo monolítico único de ~1200 linhas, misturando lógica de detecção, gerenciamento de configuração e interface gráfica na mesma classe.

A V5 foi reestruturada em 4 módulos com responsabilidades bem definidas:

| Módulo | Responsabilidade | Dependências |
|--------|-----------------|--------------|
| `verificar_caixaV5.py` | Entry point, argumentos CLI | `config_manager`, `gui_app` |
| `config_manager.py` | Carregamento, merge recursivo e persistência de configurações | — |
| `detector_cacamba.py` | Lógica pura de detecção (sem GUI, sem threads) | NumPy, OpenCV |
| `gui_app.py` | Interface gráfica, threading, visualização | Todos os anteriores |

O `DetectorCacamba` pode ser instanciado, testado e executado de forma completamente independente da interface gráfica, o que facilita testes unitários e reutilização em outros contextos (por exemplo, um servidor de API ou um script de linha de comando).

O `ConfigManager` implementa merge recursivo entre configurações padrão e arquivo JSON, garantindo **retrocompatibilidade** com arquivos de configuração de versões anteriores: campos novos são adicionados com valores padrão sem sobrescrever os existentes.

---

## 5. Novas Funcionalidades

### 5.1 Modo Simulação (`--simulate`)

Permite executar e testar todo o sistema sem câmera física. Um gerador de frames sintéticos produz um sinal de profundidade senoidal que percorre os três estados (VAZIA → PARCIAL → CHEIA → PARCIAL → VAZIA), permitindo validar a lógica de detecção, a interface e os alertas sem dependência de hardware.

### 5.2 Wizard de Calibração Guiado

Com a câmera ativa, um assistente modal em 3 passos guia o operador pela calibração:
1. Mede a distância câmera–chão com o campo livre.
2. Mede a profundidade com a caçamba vazia.
3. Mede a profundidade com a caçamba cheia.

O sistema calcula e preenche automaticamente `altura_camera_chao`, `limite_vazia`, `limite_cheia` e `altura_caixa` (calculada como `limite_vazia − limite_cheia`).

### 5.3 Perfis de Configuração Nomeados

O operador pode salvar conjuntos completos de parâmetros com nomes (por exemplo, `"turno_manha"`, `"inverno"`, `"caçamba_pequena"`), alternar entre eles com um clique e deletar perfis obsoletos. Os perfis são armazenados dentro do próprio `config_v5.json`.

### 5.4 Alertas Sonoros Diferenciados

Ao detectar mudança de status, o sistema emite um beep via `winsound.Beep` com frequência distinta por estado:

| Status | Frequência |
|--------|------------|
| VAZIA | 1000 Hz (base) |
| PARCIAL | 1250 Hz (+25%) |
| CHEIA | 800 Hz (−20%) |

### 5.5 Exportação de Histórico para CSV

Todo o histórico de medições (timestamp, status, distância, percentual, confiança, FPS) pode ser exportado para um arquivo CSV na pasta `historico/`, com nome gerado automaticamente por data e hora.

### 5.6 Visualização Multi-view Alternável

O operador pode alternar entre exibir apenas o frame colorido (modo single-view, menor uso de CPU) ou os dois painéis simultaneamente: frame colorido + depth colormap. No modo single-view, o processamento do depth colormap é completamente suprimido na thread da câmera.

---

## 6. Resumo Comparativo

| Aspecto | V4 | V5 |
|---------|----|----|
| Arquitetura | 1 arquivo monolítico | 4 módulos separados por responsabilidade |
| Thread safety | Acesso a widgets em threads erradas | Comunicação exclusiva via `queue.Queue` |
| Proteção contra pessoas | Documentada, não implementada | 4 filtros ativos em cascata |
| Cálculo de confiança | Valor instantâneo (bug) | Média de histórico real (`deque(maxlen=30)`) |
| Contaminação do histórico | Leituras de fallback distorciam confiança | Histórico só recebe leituras válidas |
| Atualização da GUI | 30 chamadas/s, sem controle | 15 FPS máx., 1 frame pesado por tick |
| Resize de imagem | LANCZOS (máxima qualidade, lento) | BILINEAR (~4× mais rápido) |
| Gráfico Canvas | N `create_line` individuais por frame | 1 `create_line` com todos os pontos |
| Frames descartados | Sempre processados antes do descarte | Descartados antes de qualquer processamento |
| Teste sem hardware | Não disponível | Modo simulação completo (`--simulate`) |
| Calibração | Manual (editar JSON) | Wizard guiado em 3 passos |
| Configurações | Único arquivo global | Perfis nomeados, carregamento com 1 clique |
| Exportação de dados | Não disponível | CSV com histórico completo |
