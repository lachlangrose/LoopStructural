# Loop 2.0 Visualization

A Loop 2.0 interface for pyvista's Plotter class.

## Installation

Install via pip:

```bash
pip install loop-visualization
```

For Jupyter notebook support with all visualization features:

```bash
pip install loop-visualization[jupyter]
```

For the standalone trame app:

```bash
pip install loop-visualization[trame]
```

## Features

- 3D visualization of geological models
- Integration with pyvista for interactive rendering
- Support for Jupyter notebooks
- Stratigraphic column visualization
- Rotation angle controls
- 2D and 3D viewer interfaces

## Standalone Trame App

Run the built-in standalone app from the command line:

```bash
loop-trame-app
```

Common options:

```bash
loop-trame-app --host 0.0.0.0 --port 8080 --scene wavelet
loop-trame-app --scene sphere --mode client
loop-trame-app --no-browser
loop-trame-app --mesh ./mesh_1.vtk --mesh ./mesh_2.vtp
```

## Documentation

For more information, visit the [Loop 2.0 documentation](https://Loop3d.org/LoopStructural/)

## License

MIT License - See LICENSE file for details
