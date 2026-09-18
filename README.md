# 3D-Printed PCB Toolchain (PCB3D)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Docker Ready](https://img.shields.io/badge/docker-ready-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

An open-source parametric toolchain that converts **KiCad DXF** and **SVG** exports into precision 3D-printable PCB substrates. The pipeline produces **OpenSCAD (`.scad`)** CSG source models and compiles them into **STL (`.stl`)** geometries:
- **Single-Layer PCBs**: Rectangular or polygonal dielectric substrate with subtractive recessed trace trenches (channels carved lower than the board surface) and cylindrical through-holes.
- **Multi-Layer Stacks**: Stacks 2 or more dielectric layers with parametric **corner alignment pegs** and **receptive sockets** for tight mechanical interlocking, plus synchronized exploded-view inspection.
- **Interactive Web Studio**: Built-in 2D circuit vector viewer and 3D WebGL (Three.js) visualizer with multi-material copper trace rendering, layer elevation ruler, and one-click ZIP bundle downloads.
- **Headless CLI & REST API**: Automate batch compilation of STL/SCAD files and integrate into manufacturing pipelines.

---

## Table of Contents

- [Key Features](#key-features)
- [Quickstart with Docker (Recommended)](#quickstart-with-docker-recommended)
- [Local Native Installation](#local-native-installation)
  - [Prerequisites](#prerequisites)
  - [Virtual Environment Setup](#virtual-environment-setup)
  - [Running Automated Tests](#running-automated-tests)
- [Web Studio Usage](#web-studio-usage)
  - [Starting the Server](#starting-the-server)
  - [UI Features & Capabilities](#ui-features--capabilities)
- [Command Line Interface (CLI)](#command-line-interface-cli)
- [KiCad Export Guide](#kicad-export-guide)
  - [Exporting DXF](#exporting-dxf)
  - [Exporting SVG](#exporting-svg)
- [Multi-Layer Stacking Architecture](#multi-layer-stacking-architecture)
- [Configuration Reference (`pcb3d.yml`)](#configuration-reference-pcb3dyml)
- [Production Deployment](#production-deployment)
  - [Docker Compose](#docker-compose)
  - [Nginx Reverse Proxy](#nginx-reverse-proxy)

---

## Key Features

- **Dual Vector Ingestion**: Ingests both AutoCAD DXF (`.dxf`) and Scalable Vector Graphics (`.svg`) files directly exported from KiCad.
- **Subtractive Trenching**: Generates recessed channels for conductive inks, copper tape, conductive paste, or electroplating.
- **Interlocking Multi-Layer Alignment**: Automatically positions matching alignment pegs and sockets on mating layer surfaces.
- **Composite 2D Circuit Visualizer**: Real-time canvas inspection with per-layer color-coded traces and aligned via overlays.
- **Interactive 3D WebGL Studio**:
  - Multi-material rendering separating substrate dielectric from conductive copper channels.
  - Interactive Vertical Discrete Stack Ruler displaying physical elevations.
  - Exploded view slider for inspecting sandwiched multi-layer boards.
  - 1-click single-file STL/SCAD downloads or batch `.ZIP` archives.
- **Dual Runtime**: Headless CLI tool for CI/scripts and Flask/Gunicorn web application with REST API endpoints.

---

## Quickstart with Docker (Recommended)

Docker provides an isolated, pre-configured environment containing Python 3.12, OpenSCAD, and Gunicorn.

### 1. Launch with Docker Compose

```bash
docker compose up --build
```

The Web Studio is now live at **[http://localhost:5000](http://localhost:5000)**.

- Generated STL and SCAD files are automatically mapped and persisted in `./pcb3d-output`.
- Stop the container at any time with:
  ```bash
  docker compose down
  ```

### 2. Standalone Docker Container

If you prefer building and running the container manually:

```bash
# Build the Docker image
docker build -t pcb3d .

# Run container in background with volume mapping
docker run -d \
  -p 5000:5000 \
  -v "$(pwd)/pcb3d-output:/app/pcb3d-output" \
  --name pcb3d-studio \
  pcb3d

# View application logs
docker logs -f pcb3d-studio
```

---

## Local Native Installation

### Prerequisites

1. **Python 3.10+**: Ensure Python and `pip` are installed.
2. **OpenSCAD**: Required by the pipeline to compile `.scad` scripts into `.stl` meshes.

Install OpenSCAD using your operating system's package manager:

- **Ubuntu / Debian**:
  ```bash
  sudo apt-get update && sudo apt-get install -y openscad
  ```
- **Fedora / RHEL**:
  ```bash
  sudo dnf install -y openscad
  ```
- **Arch Linux**:
  ```bash
  sudo pacman -S openscad
  ```
- **macOS** (via [Homebrew](https://brew.sh/)):
  ```bash
  brew install --cask openscad
  ```
- **Windows** (via [Chocolatey](https://chocolatey.org/) or [Winget](https://learn.microsoft.com/en-us/windows/package-manager/winget/)):
  ```powershell
  choco install openscad
  # or
  winget install OpenSCAD.OpenSCAD
  ```

### Virtual Environment Setup

Always use a Python virtual environment to manage dependencies:

```bash
# Clone repository and enter directory
git clone https://github.com/sixdenip/3d-printed-pcb.git
cd 3d-printed-pcb

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate       # On Windows: .venv\Scripts\activate

# Install package in editable mode with development & deployment extras
pip install --upgrade pip
pip install -e '.[deploy,test]'
```

### Running Automated Tests

Run the full automated test suite (including vector parsers, coordinate normalization, SCAD generation, and Web API endpoints):

```bash
pytest -v
```

---

## Web Studio Usage

### Starting the Server

#### Development Mode (Flask)
```bash
flask --app 'pcb3d.web:create_app()' run --debug --host 0.0.0.0 --port 5000
```

#### Production Mode (Gunicorn)
For high-concurrency production deployments with multi-worker support:
```bash
gunicorn -w 4 -b 0.0.0.0:5000 --timeout 120 'pcb3d.web:create_app()'
```
> [!NOTE]
> The `--timeout 120` setting prevents worker timeouts during complex OpenSCAD CSG boolean rendering operations.

### UI Features & Capabilities

Navigate to `http://localhost:5000` in your web browser:

1. **Single-Layer & Multi-Layer Modes**:
   - **Single Layer**: Upload a single DXF or SVG board file to generate a standalone PCB substrate.
   - **Multi-Layer Stack**: Upload 2 or more files (e.g. Layer 1 Base, Layer 2 Shield, Layer 3...) to automatically generate an interlocking physical stack.
2. **Interactive 2D Circuit Visualizer**:
   - Inspect loaded vector geometry before compiling 3D models.
   - Switch between individual layers or select **ALL** to view a composite overlay with per-layer color coding (Cyan, Amber, Emerald, Rose).
3. **Interactive 3D WebGL Studio**:
   - **Discrete Vertical Stack Ruler**: Located on the right side of the 3D viewport, showing layer elevations (e.g. `+1.6mm`, `0.0mm`) and providing instant layer isolation.
   - **Exploded View Slider**: Dynamically spread stacked layers apart in 3D to inspect internal traces and interlocking features.
   - **Multi-Material Copper Shading**: Accurately differentiates the dielectric substrate body from conductive copper trenches.
   - **View Presets**: One-click camera presets (Top, Bottom, Front, Perspective) and orbit controls.
4. **Downloads & Batch Bundling**:
   - Download individual `.stl` and `.scad` files for the active layer.
   - When **ALL** is selected in multi-layer mode, download all generated STLs or SCAD files bundled into a single `.ZIP` archive.

---

## Command Line Interface (CLI)

The `pcb3d` command allows batch operations and CI/CD automation:

```bash
# Generate STL from DXF
pcb3d generate --dxf examples/board.dxf --output output/board.stl

# Generate STL from SVG
pcb3d generate --svg examples/board.svg --output output/board.stl

# Custom dimensions and overrides
pcb3d generate \
  --dxf board.dxf \
  --output board.stl \
  --base-thickness 2.0 \
  --trace-depth 0.5 \
  --trace-width 0.6 \
  --outline-margin 0.5 \
  --m4-holes

# Specify custom OpenSCAD binary path (if not on standard system PATH)
pcb3d generate --dxf board.dxf --output board.stl --openscad /usr/bin/openscad
```

### CLI Options Reference

| Flag | Description | Default |
|------|-------------|---------|
| `--dxf <path>` | Input DXF file | None |
| `--svg <path>` | Input SVG file | None |
| `--output <path>` | Target output `.stl` path | `<input_basename>.stl` |
| `--config <path>` | Path to YAML configuration file | Optional |
| `--base-thickness <mm>` | Total substrate height in mm | `1.6` |
| `--trace-depth <mm>` | Depth of carved trace trenches in mm | `0.4` |
| `--trace-width <mm>` | Width of trace channels in mm | `0.4` |
| `--outline-margin <mm>` | Extra boundary margin around board in mm | `0.0` |
| `--m4-holes` | Include 4 corner M4 mounting holes | Disabled |
| `--openscad <path>` | Executable path for OpenSCAD binary | Auto-detected |

---

## KiCad Export Guide

### Exporting DXF
1. In KiCad PCB Editor, click **File > Export > DXF...**.
2. Select target layers:
   - `Edge.Cuts` (Board outline boundary)
   - `F.Cu` or `B.Cu` (Copper traces)
   - `NPTH` or `Drill` (Holes and vias)
3. Recommended settings:
   - **Plot format**: DXF
   - **Units**: Millimeters (mm)
   - **Plot drill marks**: None
   - **Plot background / titles**: Unchecked
4. Click **Export**.

### Exporting SVG
1. In KiCad PCB Editor, click **File > Export > SVG...**.
2. Select target layers: `Edge.Cuts`, `F.Cu`, `NPTH`.
3. Select **Black and White** or **Default colors**.
4. Set **Page size** to **Current page size** or **Board area only**.
5. Click **Export**. The toolchain automatically resolves coordinate origins and scales units (`mm`, `in`, `cm`, `pt`, `px`) to millimeters.

---

## Multi-Layer Stacking Architecture

When stacking multiple substrates:
- **Alignment Pegs & Sockets**: The toolchain automatically places corner alignment pins (default $r = 1.0\,\text{mm}$, height $1.2\,\text{mm}$) on the top face of lower layers, and complementary receptive sockets ($r = 1.15\,\text{mm}$) on the bottom face of upper layers.
- **Inter-layer Clearance**: A $0.15\,\text{mm}$ radial tolerance ensures smooth assembly on FDM and SLA 3D printers without binding.
- **Coordinate Unification**: All layers in a stack are translated to a shared global coordinate frame, ensuring perfect through-hole and trace registration.

---

## Configuration Reference (`pcb3d.yml`)

You can define custom layer mappings and default manufacturing dimensions via a `pcb3d.yml` file:

```yaml
layers:
  outline: ["Edge.Cuts", "Board"]      # Recognized outline layers
  traces: ["F.Cu", "B.Cu", "CopperTop"] # Recognized copper layers
  holes: ["NPTH", "Drill", "Holes"]    # Recognized hole layers

parameters:
  base_thickness: 1.6                  # Base plate height (mm)
  trace_height: 0.4                    # Trench carving depth (mm)
  trace_width: 0.4                     # Trace stroke width (mm)
  outline_margin: 0.0                  # Board boundary padding (mm)
  stacking_pins: true                  # Enable multi-layer alignment pegs
  pin_radius: 1.0                      # Pin radius (mm)
  socket_tolerance: 0.15               # Socket radial clearance (mm)
```

---

## Production Deployment

### Docker Compose
For production environments, run detached with automatic restart policies:

```bash
docker compose up -d
```

### Nginx Reverse Proxy
To expose PCB3D securely behind Nginx with SSL and appropriate timeout settings:

```nginx
server {
    listen 80;
    server_name pcb3d.yourdomain.com;
    client_max_body_size 64M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Generous timeouts for OpenSCAD 3D mesh rendering
        proxy_connect_timeout 120s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
    }
}
```

---

## License

This project is licensed under the [MIT License](LICENSE).