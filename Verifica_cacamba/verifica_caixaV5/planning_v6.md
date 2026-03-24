🚀 Roadmap: Maximizing Intel RealSense Potential (V6)

  Phase 1: Spatial Accuracy (Critical Fix)
  Currently, your depth data and color/IR data are captured from different physical lenses. This causes a "parallax
  shift" where your ROI detections don't perfectly line up with the depth pixels.

  1.1 Implementation of Hardware Alignment
   * Goal: Ensure every pixel in the Color/IR frame corresponds exactly to the same pixel in the Depth frame.
   * Action: Replace simple cv2.resize with rs.align.
   * Code Strategy:

   1     self.align = rs.align(rs.stream.color) # or rs.stream.infrared
   2     # ... inside loop ...
   3     aligned_frames = self.align.process(frames)
   4     depth_frame = aligned_frames.get_depth_frame()
   5     color_frame = aligned_frames.get_color_frame()

  1.2 Metric Scale Validation
   * Goal: Confirm the depth_scale is correctly applied across different firmware versions.
   * Action: Explicitly log the depth_sensor.get_depth_scale() at startup. Ensure all math in detector_cacamba.py uses
     this dynamic scale instead of assuming $0.001$.

  ---

  Phase 2: 3D Volumetric Analysis (Advanced Mastery)
  Moving from "distance measurement" to "volume measurement." This is the true potential of the RealSense in industrial
  loading.

  2.1 Point Cloud Integration
   * Goal: Convert the 2D depth map into a 3D point cloud (XYZ coordinates).
   * Action: Utilize rs.pointcloud() and rs.points.
   * Benefit: Allows you to calculate the volume of the material inside the cacamba, even if the surface is uneven
     (piles of ore/debris).

  2.2 Plane Clipping & Noise Removal
   * Goal: Filter out "floating" dust and debris using 3D statistics.
   * Action: Implement a Statistical Outlier Removal (SOR) filter.
   * Algorithm: If a point has fewer than $N$ neighbors within radius $R$, it's likely dust—discard it.

  ---

  Phase 3: Robustness for Harsh Environments
  Optimizing the sensor for the specific constraints of truck loading (dust, vibration, low-light).

  3.1 Dynamic IR Emitter Control
   * Goal: Prevent "over-exposure" on reflective metal surfaces (wet ore/shiny truck beds).
   * Action: Implement an auto-exposure logic for the Laser Power.
       - If pixels are saturated (value 0 or 65535), reduce rs.option.laser_power.
       - If the image is too noisy, increase it.

  3.2 Advanced Temporal Logic (Persistence)
   * Goal: Stop "flickering" status changes during heavy dust clouds.
   * Action: Configure the temporal_filter with a "Persistence Control" (Option: RS2_OPTION_HOLES_FILL).
   * Setting: Set persistence to "Valid in 8/8 frames" for mission-critical stability.

  ---

  Phase 4: Performance & Memory Optimization
  Ensuring the system can run for weeks without crashing or lagging.

  4.1 Frame Lifecycle Management
   * Goal: Prevent Python's garbage collector from lagging behind the C++ SDK.
   * Action: Use context managers or explicit del for frames, depth_frame, and color_frame at the very end of the while
     loop.

  4.2 Multi-Processing (Inference Split)
   * Goal: Keep the camera acquisition at a steady 30 FPS regardless of how heavy the UI/Log processing is.
   * Action: Move the DetectorCacamba.processar_frame logic into a separate multiprocessing.Process if volume
     calculations become CPU-intensive.

  ---

  🛠️ Proposed Tech Stack Update

  ┌───────────┬─────────────────┬────────────────────────────────┐
  │ Component │ Current (V5)    │ Next (V6)                      │
  ├───────────┼─────────────────┼────────────────────────────────┤
  │ Logic     │ 2D Median Grid  │ 3D Point Cloud / Volumetrics   │
  │ Alignment │ Software Resize │ Hardware rs.align              │
  │ Libraries │ numpy, opencv   │ numpy, opencv, open3d (for 3D) │
  │ Modality  │ RGB + Depth     │ IR + Depth (Priority)          │
  └───────────┴─────────────────┴────────────────────────────────┘