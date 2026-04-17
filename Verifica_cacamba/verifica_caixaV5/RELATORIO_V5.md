# Relatório do Projeto: Sistema de Monitoramento de Caçamba V5

Este documento consolida as informações técnicas, arquiteturais e funcionais da Versão 5 (V5) do sistema, desenvolvida para superar as limitações de estabilidade e confiabilidade das versões anteriores.

---

## 1. Visão Geral
A Versão 5 representa uma evolução crítica focada em **robustez industrial**, **estabilidade de software** e **facilidade de operação**. Enquanto as versões anteriores estabeleceram a prova de conceito e a interface básica, a V5 resolveu falhas estruturais de comunicação entre threads e introduziu mecanismos de segurança para evitar falsos positivos (como a detecção de pessoas como se fossem caçambas).

## 2. Arquitetura do Sistema
O sistema foi refatorado de um modelo monolítico para uma arquitetura modular baseada em responsabilidades:

| Módulo | Descrição |
| :--- | :--- |
| `verificar_caixaV5.py` | Ponto de entrada da aplicação. Gerencia argumentos de inicialização (como o modo `--simulate`). |
| `detector_cacamba.py` | Núcleo de processamento. Contém a lógica de visão computacional, cálculos 3D/volumétricos e filtros de validação. É independente de interface gráfica. |
| `gui_app.py` | Interface gráfica (Tkinter). Gerencia a visualização em tempo real, threads de captura de vídeo e interação com o usuário. |
| `config_manager.py` | Responsável pela persistência e gerenciamento de perfis de configuração em formato JSON. |

### 2.1 Comunicação Segura entre Threads
Uma das melhorias mais significativas foi a implementação de comunicação via `queue.Queue`.
- **Thread da Câmera:** Focada apenas em capturar e processar frames, enviando resultados para a GUI.
- **Thread da GUI:** Consome os resultados da fila e atualiza os widgets de forma síncrona, eliminando os travamentos e comportamentos indefinidos da V4.
- **Locks de Configuração:** O uso de `threading.Lock` garante que alterações de parâmetros na interface sejam propagadas para o detector de forma segura.

## 3. Funcionalidades de Detecção e Segurança
O sistema utiliza dados de profundidade da câmera Intel RealSense para determinar o nível de preenchimento.

### 3.1 Filtros de Proteção (Anti-Falsos Positivos)
Para evitar que operadores ou outros objetos sejam confundidos com a caçamba, foram implementados quatro filtros em cascata no método `_validar_deteccao`:
1.  **Aspect Ratio:** Rejeita objetos muito alongados (braços/pernas).
2.  **ROI (Região de Interesse):** Valida se o centro do objeto está na área esperada de carga.
3.  **Profundidade Mínima:** Ignora objetos muito próximos da câmera (geralmente pessoas passando).
4.  **Área Máxima:** Filtra objetos que excedem o tamanho físico esperado da caçamba.

### 3.2 Análise 3D e Volumetria
Diferente da V4, a V5 introduziu suporte inicial para processamento de **nuvens de pontos (Point Clouds)**:
- **Cálculo de Volume:** Utiliza as coordenadas Z reais para calcular a média das alturas dentro da caçamba, oferecendo uma leitura mais precisa do que a simples mediana da distância central.
- **Filtro SOR (Statistical Outlier Removal):** Remove ruídos pontuais e detritos voláteis no ar que poderiam causar picos de erro nas medições.

## 4. Melhorias na Experiência do Operador
- **Modo Simulação:** Permite testes completos de lógica e interface sem necessidade de hardware físico conectado.
- **Wizard de Calibração:** Guia o usuário em 3 passos para configurar a altura da câmera, o nível vazio e o nível cheio.
- **Alertas Sonoros:** Beeps diferenciados por frequência para cada status (VAZIA, PARCIAL, CHEIA).
- **Exportação de Dados:** Registro automático de histórico em CSV para auditoria e análise posterior.
- **Multi-view:** Alternância entre visão de cor (RGB) e mapa de profundidade colorido.

## 5. Próximos Passos (Roadmap V6)
Conforme planejado no arquivo `planning_v6.md`, os focos da próxima versão são:
- **Hardware Alignment (`rs.align`):** Eliminar o erro de paralaxe entre as lentes de profundidade e cor.
- **Análise Volumétrica Completa:** Melhorar o cálculo de volume para superfícies de material irregulares.
- **Otimização de Performance:** Melhorar o gerenciamento de memória do SDK RealSense em Python.
