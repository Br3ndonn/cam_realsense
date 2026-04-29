# AGENTS.md

## Project focus
- This repo is a RealSense-first industrial monitoring workspace for truck caçamba level/volumetry.
- Prioritize depth/IR logic over RGB; the environment is dusty/low-light and `GEMINI.md` + `realsense-master.md` both reinforce that.
- `README.md` at the repo root is empty, so this file is the practical agent guide.

## Main entry points
- Preferred app: `Verifica_cacamba/verifica_caixav6/verifica_caixav6.py`.
- Legacy-but-useful reference: `Verifica_cacamba/verifica_caixaV5/verificar_caixaV5.py`.
- Other standalone demos: `bodyTrack/postura_analyzer.py`, `bodyTrack/body_track.py`, `medirProfundidade/medir_profundidade.py`, `virtualizacao/virtualizacao.py`.

## V6 architecture to preserve
- `verifica_caixav6.py` only parses CLI args, creates `ConfigManager`, then launches `DetectorCacambaGUIV6`.
- `gui_app.py` owns Tkinter, threads, queues, logging, CSV export, the calibration wizard, and the UI refresh loop.
- `detector_cacamba.py` is pure detection logic; `processar_frame_3d()` is the preferred path and `processar_frame()` is the fallback.
- `config_manager.py` loads/merges JSON config, persists `config_v6.json`, and stores named profiles inside the same config file.

## Data flow and threading patterns
- The camera thread never touches Tk widgets; GUI ↔ camera communication goes through `data_queue`, `infer_queue`, and `cmd_queue`.
- Configuration changes are taken from `self.cm.cfg`, copied with `deepcopy`, and pushed back to the running detector with `update_config` commands.
- The GUI updates on a timed poll (`root.after(66ms, _poll_queue)`), not on every frame callback.

## RealSense / vision conventions
- Open the pipeline with aligned depth + color, then use depth filters before detection (`decimation`, `spatial`, `temporal`, `hole_filling`).
- Generate point clouds in V6 (`rs.pointcloud()`) and keep `verts` shaped as `(h*w, 3)` for `DetectorCacamba.processar_frame_3d()`.
- If `pyrealsense2` is missing, the GUI is expected to run in `--simulate` mode instead of failing immediately.

## Config and calibration patterns
- The default config schema lives in `Verifica_cacamba/verifica_caixav6/config_manager.py` (`camera`, `medicoes`, `thresholds`, `protecao_pessoa`, `filtros`, `visualizacao`, `sons`).
- Add new tunables in both `CONFIG_PADRAO` and the Tk config form in `gui_app.py`.
- The 3-step `WizardCalibracao` writes back `altura_camera_chao`, `limite_vazia`, `limite_cheia`, and derived `altura_caixa`.

## UI / runtime conventions
- Use Portuguese UI labels and symbol names where the existing code does (`DetectorCacambaGUIV6`, `ResultadoDeteccao`, `WizardCalibracao`).
- Keep `try/finally` cleanup for camera stop and window shutdown (`fechar_aplicacao`, `pipeline.stop()`, `cv2.destroyAllWindows()`).
- Windows-only beep support is optional via `winsound`; the code already guards import failure.

## Legacy and supporting modules
- `bodyTrack/` is a separate MediaPipe posture/tracking sandbox; do not entangle it with the caçamba app.
- `medirProfundidade/medir_profundidade.py` is a small calibration helper for measuring camera-to-floor height.
- `virtualizacao/virtualizacao.py` is an independent YOLO + Open3D object-scanning demo.

## Practical agent workflow
- When changing V6 behavior, inspect `verifica_caixav6.py`, `gui_app.py`, `detector_cacamba.py`, and `config_manager.py` together.
- Keep changes local and modular; this repo has evolved through versioned scripts, so avoid widening V6 changes into the older demos unless necessary.
- Prefer updating the existing config/profile flow over introducing a second settings system.

