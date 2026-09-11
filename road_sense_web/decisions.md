# RoadSense AI - Architectural Decisions Log

| Date | Decision | Reason |
| :--- | :--- | :--- |
| **2026-09-10** | **Project Directory Setup**<br>Created `road_sense_web` folder inside `New folder`. | Encapsulates the web application codebase separately from the training scripts, models, and datasets. |
| **2026-09-10** | **Backend Requirement: YES**<br>Use a Python Backend (e.g., FastAPI). | We already have well-functioning YOLOv8 models (`best.pt`) in Python using the `ultralytics` package. Serving these via a Python REST API is the most efficient, reliable, and standard way to run inference, rather than exporting and running them directly in the browser. |
| **2026-09-10** | **Frontend Stack**<br>Vanilla HTML, CSS, and JavaScript. | Adheres to core web technologies, keeping the application fast and lightweight without the overhead of heavy frameworks unless explicitly required later. Allows for complete control over styling. |
