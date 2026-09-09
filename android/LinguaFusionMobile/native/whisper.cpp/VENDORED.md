# Vendored whisper.cpp

Release **b4938**, from https://github.com/ggml-org/whisper.cpp

Only what a CPU-only Android build compiles is kept. These backends
are deliberately absent, each being off by default in GGML's CMake:

- `ggml-blas`
- `ggml-cann`
- `ggml-cpu-hbm`
- `ggml-cuda`
- `ggml-et`
- `ggml-hexagon`
- `ggml-metal`
- `ggml-musa`
- `ggml-opencl`
- `ggml-openvino`
- `ggml-rpc`
- `ggml-sycl`
- `ggml-virtgpu`
- `ggml-vulkan`
- `ggml-webgpu`
- `ggml-zdnn`
- `ggml-zendnn`

Regenerate with `scripts/vendor_whisper.py` after unpacking the
release tarball; do not hand-edit anything under this directory.
