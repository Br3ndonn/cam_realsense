# Project Context: Intelligent Truck Loading Monitoring System

## 1. Project Overview
The goal of this project is to develop an automated system to analyze and monitor the loading of trucks with ore and other bulk materials. The system is designed to overcome limitations of human operators and conventional cameras, specifically regarding visual obstruction caused by debris and operation in low-light or night conditions.

## 2. Core Objectives
- **Debris Resistance:** Maintain accurate monitoring even when dust, ore debris, or other materials obscure standard visual lines of sight.
- **Low-Light Operation:** Function effectively at night or in poorly lit industrial environments without relying on visible light.
- **Volume/Material Analysis:** Utilize depth data to analyze load distribution and material presence.
- **Automation:** Reduce reliance on human visual verification.

## 3. Technology Stack
- **Primary Language:** Python
- **Hardware Interface:** Intel RealSense SDK (likely `pyrealsense2`)
- **Image Processing:** OpenCV (`cv2`), NumPy
- **Data Types:** 
  - Depth Frames
  - Infrared (IR) Streams
  - 3D Point Clouds

## 4. Hardware Specifications
- **Camera:** Intel RealSense Depth Camera
- **Sensors:** 
  - Depth Sensor (for distance and volume calculation)
  - Infrared Sensor (for visibility in low-light/dust)
- **Output:** Point Cloud data for spatial analysis.

## 5. Environmental Challenges & Constraints
- **Visual Obstruction:** High levels of dust and debris generated during ore loading.
- **Lighting:** Variable lighting conditions, including complete darkness (night shifts).
- **Real-Time Requirements:** Processing must be efficient enough to monitor loading operations as they happen.
- **Industrial Setting:** Code must be robust against sensor noise and environmental interference.

## 6. AI Assistant Guidelines
When assisting with this project, please adhere to the following:
- **Prioritize Performance:** Suggest optimizations for real-time point cloud processing and depth frame analysis.
- **Focus on Robustness:** Recommend error handling for sensor disconnections or noisy depth data.
- **Library Usage:** Prefer standard libraries compatible with Intel RealSense in Python (e.g., `pyrealsense2`, `open3d` for point clouds if needed).
- **Lighting Agnostic:** Ensure solutions rely on Depth and IR data rather than RGB color data, given the low-light constraints.
- **Code Style:** Write clean, modular Python code with type hinting where possible.